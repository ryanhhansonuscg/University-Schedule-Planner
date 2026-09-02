# University registry

Each subfolder is a self-contained university dataset. Add public datasets to `index.json` so they appear in the application picker.

Registry entries use this shape:

```json
{
  "slug": "example-university",
  "name": "Example University",
  "short_name": "EXU",
  "path": "universities/example-university/catalog.json"
}
```

The slug must be unique and should match the university folder and `university.json`. The path points to the generated browser catalog. Set `default_university` to one of the registered slugs.

Use `../template/university-template` to create a new dataset.
