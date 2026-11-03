---
name: wimp-model-benchmark
description: "Benchmark WildObs WIMP computer-vision models (MegaDetector thresholds, species classifiers) on human-validated camera-trap images and report recall, precision and F1 per class and per model, with a comparison dashboard. Use for 'how well is the classifier doing', 'test these models on my images', 'compare MegaDetector thresholds', 'run Colin's benchmark', or running it for a WildObs user."
---

# WIMP model benchmark

Runs Colin Broughton's WildObs benchmark end to end with no programming by the user.
Code, docs and results live in the public repo
**github.com/EcologicalCascadesLab/wimp-model-benchmark** (to move to the WildObs
GitHub once approved). This skill says how to drive it; the repo's `CLAUDE.md`
holds the hard rules and `docs/` the method. Do not restate them here.

## The four inputs

1. Validated images: either source WIMP project(s) already sorted by people
   (preferred: `select` finds and samples them) or a folder with one subfolder per class.
2. Benchmark project metadata (names, environment, organisation).
3. The image spreadsheet: written by `select` (full, private: `state/<set>/manifest_full.csv`;
   public: `results/<set>/manifest.csv`, file name and class only), or
   supplied by the user (`config/inputs_template/validated_images.csv`).
4. Models to test: classifier + detector threshold + environment per run.

Turn them into `config/<set>.yaml` (copy `config/awt_2026_11.yaml`). Target about
250 images per class, 1,000+ in total; include blank, human, vehicle and common
non-target species. Ask whether any images were used to train the models; exclude
them if so.

## Procedure

1. **Clone and check.** Clone the repo with submodules; keys go in env vars only
   (`WIMP_PROD_KEY`, `WIMP_TEST_KEY`; WIMP > User settings > API keys). In a claude.ai
   cloud session the environment must allow api.wimp[.test].wildobs.org.au and
   media.wimp[.test].wildobs.org.au (`docs/CLOUD_SESSION_PROMPT.md`).
   `python -m wimpbench check --config config/<set>.yaml`.
2. **Select.** `python -m wimpbench select --config ...`. Read the per-class counts;
   report classes under 100 images to the user.
3. **Create the benchmark projects (WIMP web UI; the API cannot).** One project per
   run, in the Claude built-in browser (ask the user to sign in to WIMP there and tick
   Remember me). Projects page > *Add new project* creates the project and opens its
   settings. Fill everything in one `javascript_tool` call: set `#name-input`, the
   description `textarea`, the number input with placeholder `Sequence cut-off` = 0,
   `#detector-confidence-threshold` (TEST only), using the native value setter plus
   input/change events; choose the model in the `Select a model` power-select and
   organisation in the `Organisation` power-select (dispatch `mousedown` on the
   trigger, then `mouseup` on the `.ember-power-select-option`); set *AI sharing* to
   **Private** so test images never enter model training. Then click *Save changes*
   in a separate call (it navigates). Settings load late: wait about 6 s before
   reading them back to verify. Paste each project ID (from the URL) into the config.
4. **Upload.** `python -m wimpbench upload --config ... --max-seconds 900` in a loop
   until exit code 0 (75 = run again). It streams images from the source projects to
   every run and starts the AI. About 70 source images a minute to five projects.
5. **Wait for the AI.** `python -m wimpbench status --config ...` until every
   deployment is `AIAnnotationCompleted`. If long, schedule a check rather than polling.
6. **Export and evaluate.** `export`, then `evaluate`. Outputs in `results/<set>/`:
   Colin's HTML reports and comparison report, detector metrics, species metrics,
   `dashboard.html`.
7. **Report.** Commit results (never images, exports, keys, personal names, camera names,
   timestamps or media links) and push. Check *Restricted images* is ticked on every benchmark project (WIMP default). Tell the user
   the headline per model in plain words, link the dashboard, and list caveats (small
   classes, classes outside the model).

## Running it for another WildObs user

Ask them for the four inputs (or WIMP access to their sorted project), create a new
`config/<their_set>.yaml`, run as above under Matthew's WIMP account, and share the
dashboard. Their images stay on WIMP; nothing is committed but file names and labels.

## Known traps

- PROD's pipeline (before QCIF's October 2026 changes) leaves many detections
  "Unclassified"; this is a finding, not a bug in the benchmark.
- Colin's loader scores vehicle predictions as blank and cannot tell apart runs of
  the same model; the repo works around both (`docs/upstream_suggestions.md`).
- The API cannot delete deployments or projects; list leftovers for the user.
