# University registry

Each subfolder is a self-contained university dataset. Add public datasets to `index.json` so they appear in the application picker. An empty `universities` array and a `null` `default_university` are valid; the application then displays contributor onboarding instead of a catalog.

Registry entries use this shape:

```json
{
  "slug": "institution-slug",
  "name": "Institution Display Name",
  "short_name": "SHORT",
  "path": "universities/institution-slug/catalog.json"
}
```

The slug must be unique and should match the university folder and `university.json`. The path points to the generated browser catalog. Set `default_university` to one of the registered slugs.

Use the explicitly fictional fixture at `../template/university-template` to create a new dataset. Replace every placeholder before registering it; template data must never be presented as a real institution.
