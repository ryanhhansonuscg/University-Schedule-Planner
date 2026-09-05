"""PyInstaller recipe for the optional Windows launcher distribution."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).parent

# Import the canonical release contract rather than maintaining a second list.
namespace = {}
exec((ROOT / "tools" / "build_release.py").read_text(encoding="utf-8"), namespace)
release_files = namespace["RELEASE_FILES"]
datas = [(str(ROOT / name), str(Path(name).parent)) for name in release_files]

a = Analysis(
    [str(ROOT / "tools" / "launcher.py")],
    pathex=[str(ROOT), str(ROOT / "tools")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("tools"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UniversitySchedulePlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    contents_directory=".",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="UniversitySchedulePlanner",
)
