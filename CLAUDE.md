# Instructions for Claude working in this repository

Purpose: benchmark the WildObs WIMP computer-vision models (MegaDetector + species classifiers) against human-validated images, by automating Colin Broughton's evaluation workflow end to end. Read `README.md` first, then the run spec in `config/`.

## Hard rules

- Never commit API keys, tokens, images or Camtrap DP exports. Keys come only from the environment variables `WIMP_PROD_KEY` and `WIMP_TEST_KEY`. Images live in `data/` and exports in `Input_Data/`, both git-ignored.
- Never edit `vendor/model-benchmark-testing-workflow` (Colin's repo, a pinned submodule). Extend it from `wimpbench/`; propose upstream changes as notes in `docs/upstream_suggestions.md`.
- Never write to the source projects the validated images come from (e.g. Skye's AWT projects). They are read-only: GET requests only.
- Only write to projects listed under `runs:` in the active config. Check the project ID before every write.
- Never delete a WIMP deployment, location or project. If something needs deleting, list it for Matthew.

## What needs the WIMP web UI (not possible via API)

Creating a project, and setting its AI model, its detector confidence threshold and its sequence cutoff. The cloud session cannot do these. If a run's `project_id` is empty in the config, stop and ask Matthew to create the project (`docs/03_wimp_projects.Rmd` has the checklist), then fill in the ID.

## Network

The cloud environment must allow `api.wimp.wildobs.org.au`, `api.wimp.test.wildobs.org.au` and the media host returned in `media.csv` file paths. If a request is refused by the proxy, say which host and stop.

## Steps (each is resumable; state is kept in `state/`, git-ignored)

`python -m wimpbench <step> --config <yaml>` with step one of: check, select, fetch, upload, status, export, evaluate. Run them in order. `upload` takes about 1 minute per 200 images per project; `status` until every deployment reports AI done; then `export` and `evaluate`.

## Outputs to commit

`results/<set>/`: Colin's HTML reports, `detector_metrics.csv`, `summary.csv`, `dashboard.html`, and the image manifest `manifest.csv` (file names and labels only). Update `docs/` and the results table in `README.md` in the same commit. Commit after each finished step with a message saying what was run.

## Documentation style

`docs/NN_<step>.Rmd`: R Markdown with `python` chunks (reticulate), one file per step, written so it converts to a Jupyter notebook later. Each file: purpose, inputs, the code chunk(s), what the output looks like, known issues.
