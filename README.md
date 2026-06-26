# UAP Relationship Graph

A static, browser-based relationship graph for exploring entities and connections extracted from a corpus of UAP-related transcripts.

Live site: https://ufo-files.github.io/uap-relationship-graph/

## What It Does

The app turns transcript-derived entities into an interactive graph. Categories form the outer structure, entities live inside those categories, and relationships are drawn from co-occurrence and corpus evidence.

The current export includes:

- 34 transcripts
- 160,447 transcript segments
- 10,706 entity mentions
- 3,906 entities
- 3,500 relationships
- 42 categories

## Interface

- Pan and zoom the graph directly.
- Click a category to drill into that portion of the graph.
- Zoom back out to return to the parent graph.
- Click an entity to inspect transcript evidence, relationships, category, count, confidence, and significance.
- Reclassify an entity when the detected category is wrong.
- Mark false positives when an extracted entity should not be tracked.
- Merge duplicates when multiple names refer to the same entity.
- Export review decisions so they can be applied during a future rebuild.

## Data Files

The app is fully static. All data needed by the browser is committed in this repository.

| File | Purpose |
| --- | --- |
| `index.html` | Graph interface and application shell |
| `app-data.js` | Loader for the exported JSON data |
| `data/entities.json` | Extracted entities, categories, confidence, counts, and evidence references |
| `data/relationships.json` | Entity-to-entity relationship records |
| `data/mentions.json` | Mention-level extraction records |
| `data/segments.json` | Transcript segment evidence used by the inspector |
| `data/graph.json` | Precomputed graph layout and grouping data |
| `data/manifest.json` | Build metadata, input hashes, pipeline hash, counts, and reproducibility notes |
| `data/review-template.json` | Empty review-decision template for reclassification workflows |

## Reproducibility

This repository is the public static export. The generator deletes the previous report output and recreates it on each rebuild, so a second run is intended to replace the prior report instead of layering new data on top of old data.

The manifest records:

- pipeline name
- generation timestamp
- source file hashes
- pipeline hash
- registry hash
- review-decision counts
- whether review input was applied

No OpenAI API key is required to view this site.

## Review Workflow

The graph includes review controls for correcting extraction mistakes:

- **Reclassify** moves an entity to a different category.
- **False positive** removes an entity from future tracking.
- **Merge** combines duplicate entities.

After reviewing, download the review decisions from the app. In the private build workspace, place that file where the generator expects it before rebuilding. The next generated export will apply those decisions and replace the previous report output.

## Extraction Limits

This is an exploratory transcript intelligence tool, not an authority file. The graph is useful for navigation, discovery, and evidence review, but automated extraction can misclassify entities, miss relationships, duplicate names, or preserve claims exactly as they appear in source transcripts.

Treat graph findings as leads. Click into nodes and read the transcript evidence before drawing conclusions.

## Deployment

The site is hosted with GitHub Pages from the `main` branch root.

Repository: https://github.com/ufo-files/uap-relationship-graph
