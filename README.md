# UAP Relationship Graph

A static, browser-based relationship graph for exploring entities and connections extracted from a corpus of UAP-related transcripts.

Live site: https://ufo-files.github.io/uap-relationship-graph/

## What It Does

The app turns transcript-derived entities into an interactive graph. Categories form the outer structure, entities live inside those categories, and relationships are drawn from co-occurrence and corpus evidence.

The current export includes:

- 36 transcripts
- 162,082 transcript segments
- 10,667 entity mentions
- 3,858 entities
- 3,500 relationships
- 46 categories

## Interface

- Pan and zoom the graph directly.
- Click a category to drill into that portion of the graph.
- Zoom back out to return to the parent graph.
- Click an entity to inspect transcript evidence, relationships, category, count, confidence, and significance.
- Reclassify an entity when the detected category is wrong.
- Mark false positives when an extracted entity should not be tracked.
- Merge duplicates when multiple names refer to the same entity.
- Export reclassification data so it can be applied during a future rebuild.

## Data Files

The app is fully static. All data needed by the browser is committed in this repository.

| File | Purpose |
| --- | --- |
| `index.html` | Graph interface and application shell |
| `app-data.js` | Loader for the exported JSON data |
| `build_graph.py` | Rebuilds the graph from transcripts and reclassification data |
| `data/transcripts/` | Source transcript files and `entity-registry.json` |
| `data/entities.json` | Extracted entities, categories, confidence, counts, and evidence references |
| `data/relationships.json` | Entity-to-entity relationship records |
| `data/mentions.json` | Mention-level extraction records |
| `data/segments.json` | Transcript segment evidence used by the inspector |
| `data/graph.json` | Precomputed graph layout and grouping data |
| `data/manifest.json` | Build metadata, input hashes, pipeline hash, counts, and reproducibility notes |
| `data/reclass.json` | Durable reclassification, false-positive, and merge rules |
| `data/reclass-template.json` | Empty reclassification template |

## Reproducibility

This repository contains both the source transcript files and the generated static graph. Rebuilds overwrite the generated app files in place while preserving `data/transcripts/` and `data/reclass.json`.

To rebuild:

```bash
python3 build_graph.py
```

The manifest records:

- pipeline name
- generation timestamp
- source file hashes
- pipeline hash
- registry hash
- reclassification counts
- whether review input was applied

No OpenAI API key is required to view this site.

## Reclassification Workflow

The graph includes controls for correcting extraction mistakes:

- **Reclassify** moves an entity to a different category.
- **False positive** removes an entity from future tracking.
- **Merge** combines duplicate entities.

The long-term correction file is `data/reclass.json`. It stores category changes, false positives, duplicate merges, name-based merges, aliases, omissions, and notes. The rebuild process reads this file and writes the applied copy back into the generated app data.

After reclassifying in the app, download the reclassified data and use it to replace `data/reclass.json` before rebuilding. The next generated graph applies those decisions.

### Contributor Rebuild Flow

Contributors can submit reclassification updates without rebuilding the app locally:

1. Edit `data/reclass.json`.
2. Open a pull request with that data-only change.
3. After the pull request is merged into `main`, GitHub Actions validates `data/reclass.json`, runs `python build_graph.py`, and commits the regenerated static graph files back to `main`.

The same rebuild workflow also runs when transcript source files in `data/transcripts/` or `build_graph.py` change. It can be started manually from the **Actions** tab with the **Rebuild Report** workflow.

## Extraction Limits

This is an exploratory transcript intelligence tool, not an authority file. The graph is useful for navigation, discovery, and evidence review, but automated extraction can misclassify entities, miss relationships, duplicate names, or preserve claims exactly as they appear in source transcripts.

Treat graph findings as leads. Click into nodes and read the transcript evidence before drawing conclusions.

## Deployment

The site is hosted with GitHub Pages from the `main` branch root.

Repository: https://github.com/ufo-files/uap-relationship-graph
