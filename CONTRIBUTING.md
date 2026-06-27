# Contributing

This repository accepts source data changes and lets automation rebuild the static app.

## Reclassification Updates

1. Edit `data/reclass.json`.
2. Run:

   ```bash
   python scripts/validate_repo.py
   ```

3. Open a pull request.

After the pull request is merged into `main`, the **Rebuild Report** workflow applies the reclassifications and commits regenerated app files.

## Transcript Updates

Add transcript files to `data/transcripts/`. Supported source formats are:

- `.tsv`
- `.srt`
- `.vtt`
- `.json`
- `.txt`

Do not add raw audio or video files to this repository. Transcribe media first, then commit the transcript.

If multiple files share the same base name, the builder picks one source in this order: `.tsv`, `.srt`, `.vtt`, `.json`, `.txt`.

## Generated Files

Do not edit generated app files by hand:

- `index.html`
- `app-data.js`
- `data/entities.json`
- `data/graph.json`
- `data/manifest.json`
- `data/mentions.json`
- `data/relationships.json`
- `data/segments.json`
- `data/reclass-template.json`

Change source inputs instead. The rebuild workflow regenerates these files after merge.

## Local Validation

Run the same checks used by CI:

```bash
python -m py_compile build_graph.py scripts/validate_repo.py
python -m unittest discover -s tests -v
python scripts/validate_repo.py
python scripts/audit_accessibility.py
python build_graph.py
npm run test:a11y
```
