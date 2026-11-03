# Task for the cloud session: image-level ("by image") benchmark

Follow `CLAUDE.md` (hard rules: no keys, names, camera names, timestamps or media URLs in
commits; source projects are read-only except for the two exports below; write only to
projects in the active config).

Config: `config/awt_2026_11_by_image.yaml` (test set `awt_2026_11_by_image`). The five
benchmark projects already exist on WIMP and are configured (IDs in the config).

## 0. Check first; stop if anything fails

Run `python -m wimpbench check --config config/awt_2026_11_by_image.yaml`. It must print
both environments signed in and all five projects `[ok]`. Also fetch one media file from
each media host with the key (`media.wimp.wildobs.org.au`, `media.wimp.test.wildobs.org.au`).
If a key is missing, a host is blocked by the proxy, or a name does not match: **stop and
tell Matthew exactly which setting to change** (environment variable or allowed domain in
the claude.ai/code environment). Do not work around it.

## 1. Per-image detection scores from the source projects

Matthew approved creating ONE Camtrap DP export with bounding boxes on each source project
(the two `sources` in the config; this is the only write allowed to them):
`POST /projects/{id}/exports` with `{"includeBoundingBoxes": true}`, poll
`GET /projects/{id}/exports/{exportId}` until `Completed`, download
`GET /projects/{id}/exports/{exportId}/archive` (zip) into `state/` and unzip. Its
`observations.csv` has media-level rows (`observationLevel = media`) with `mediaID`,
`observationType`, bounding box and `classificationProbability`. Check whether those
media-level rows carry the detector score; if the score for MegaDetector boxes is stored
elsewhere (another column, or `classifiedBy` = MegaDetector rows), use that, and document
what was used in `docs/02b_select_by_image.Rmd`.

## 2. Select one image per sequence

Sequences: `config/awt_2026_11_by_image_sequences.csv` (2,905 sequences: the same ones as
the by-sequence test set; class, tag, source env and sequence ID). For each sequence take
all its images (source `media.csv`, `mediaComments` holds `sequenceID:`), then:

- animal classes: the image with the highest detector score for an animal box;
- Human: highest score for a person box; Vehicle: highest score for a vehicle box;
- Blank: the middle image of the sequence (by timestamp);
- no scored box of the right type: fall back to the middle image and count these per class.

Add a `select-by-image` step to `wimpbench` (new module, reuse `select_images.py`
helpers). Write the full manifest to `state/awt_2026_11_by_image/manifest_full.csv`
(same columns as the by-sequence one, plus `pick_score` and `pick_rule`) and the public
`results/awt_2026_11_by_image/manifest.csv` (class, tag, in_model, file_name only) plus
`selection_summary.csv` (per class: sequences, images picked by score, fallbacks).

## 3. Upload, AI, export, evaluate

`upload` in a loop until exit 0 (`--max-seconds 900`; exit 75 = run again; it reads the
full manifest from `state/`), then `status` until all 95 deployments are
`AIAnnotationCompleted` (poll every 10 minutes; this can take a few hours, so keep going),
then `export` and `evaluate`. Check each export has exactly the manifest's image count.

## 4. Compare with the by-sequence results and publish

- Dashboard `results/awt_2026_11_by_image/dashboard.html` (same builder).
- `results/awt_2026_11_by_image/README.md`: findings in plain words, and a table comparing
  by-image with by-sequence (`results/awt_2026_11/`) per run: animal / blank / human /
  vehicle recall and precision, unclassified share, median species F1. Explain that
  by-image detector recall is an upper bound (images chosen by detector score) and
  by-sequence a lower bound; species-classifier comparisons are fair in both.
- `index.html` (GitHub Pages landing page): two entries, "By sequence" and "By image".
- README results table: add the by-image rows.
- Commit and push to `main` after each finished step (not to a side branch: Matthew does
  not merge pull requests). GitHub Pages serves `main`.

## 5. Report

Final message: the comparison table, three or four plain-language findings, and the
dashboard link `https://ecologicalcascadeslab.github.io/wimp-model-benchmark/`.
