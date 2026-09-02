(() => {
  const FALLBACK_COLORS = {
    primary: '#1d6d45',
    secondary: '#f0c94a',
    accent: '#101512'
  };

  function validColor(value, fallback) {
    return /^#[0-9a-f]{6}$/i.test(value || '') ? value : fallback;
  }

  function readableText(hex) {
    const weights = [0.2126, 0.7152, 0.0722];
    const luminance = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255)
      .map(value => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
      .reduce((sum, value, index) => sum + value * weights[index], 0);
    return luminance > 0.48 ? '#111111' : '#ffffff';
  }

  function applyUniversityTheme(university) {
    const primary = validColor(university.primary_color, FALLBACK_COLORS.primary);
    const secondary = validColor(university.secondary_color, FALLBACK_COLORS.secondary);
    const accent = validColor(university.accent_color, FALLBACK_COLORS.accent);
    document.documentElement.style.setProperty('--brand-primary', primary);
    document.documentElement.style.setProperty('--brand-secondary', secondary);
    document.documentElement.style.setProperty('--brand-accent', accent);
    document.documentElement.style.setProperty('--brand-on-primary', readableText(primary));
    document.documentElement.style.setProperty('--brand-on-secondary', readableText(secondary));
  }

  function urlFor(page, slug) {
    const url = new URL(page, window.location.href);
    url.searchParams.set('university', slug);
    return `${url.pathname.split('/').at(-1)}${url.search}`;
  }

  async function loadCatalog() {
    const status = document.getElementById('load-status');
    try {
      const manifestResponse = await fetch('universities/index.json', { cache: 'no-cache' });
      if (!manifestResponse.ok) throw new Error(`University index returned ${manifestResponse.status}.`);
      const manifest = await manifestResponse.json();
      const available = manifest.universities || [];
      if (!available.length) {
        status.classList.add('load-error');
        status.textContent = 'No university catalogs are published yet. To add one, copy the fictional template in template/university-template, build its catalog, and register it in universities/index.json.';
        document.getElementById('university-select').disabled = true;
        document.getElementById('app').setAttribute('aria-busy', 'false');
        return null;
      }

      const requested = new URLSearchParams(window.location.search).get('university');
      const selected = available.find(item => item.slug === requested)
        || available.find(item => item.slug === manifest.default_university)
        || available[0];

      const selector = document.getElementById('university-select');
      selector.replaceChildren(...available.map(item => new Option(item.name, item.slug)));
      selector.value = selected.slug;
      selector.addEventListener('change', () => {
        const next = new URL(window.location.href);
        next.searchParams.set('university', selector.value);
        window.location.assign(next);
      });

      const catalogResponse = await fetch(selected.path, { cache: 'no-cache' });
      if (!catalogResponse.ok) throw new Error(`${selected.name} catalog returned ${catalogResponse.status}.`);
      const catalog = await catalogResponse.json();
      applyUniversityTheme(catalog.university || {});

      document.getElementById('university-name').textContent = catalog.university?.name || selected.name;
      const explorerLink = document.getElementById('explorer-link');
      const plannerLink = document.getElementById('planner-link');
      if (explorerLink) explorerLink.href = urlFor('index.html', selected.slug);
      if (plannerLink) plannerLink.href = urlFor('planner.html', selected.slug);
      return { catalog, manifest, selected };
    } catch (error) {
      status.classList.add('load-error');
      status.textContent = `Could not load the catalog. ${error.message} Serve this folder through a web server; opening index.html directly does not allow JSON loading.`;
      document.getElementById('app').setAttribute('aria-busy', 'false');
      throw error;
    }
  }

  window.COLLEGE_PLANNER = { loadCatalog, urlFor };
})();
