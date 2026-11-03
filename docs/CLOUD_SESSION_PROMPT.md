# Starting a cloud session on this repository

## One-time environment setup (claude.ai/code → environment settings)

- **Network access:** Custom, allowing `api.wimp.wildobs.org.au`,
  `api.wimp.test.wildobs.org.au`, `media.wimp.wildobs.org.au`,
  `media.wimp.test.wildobs.org.au` (plus the default package registries).
- **Environment variables:** `WIMP_PROD_KEY` and `WIMP_TEST_KEY` (WIMP > User
  settings > API keys). Never put them in the repository.
- **Setup script:** `pip install -r requirements.txt && git submodule update --init`

## Prompt to paste

> Continue (or rerun) the WIMP model benchmark for a config in `config/` following
> CLAUDE.md. Run `python -m wimpbench status`; if any deployment is not
> `AIAnnotationCompleted`, report the table and stop. Otherwise run `export` and
> `evaluate`, check the reports open and the numbers are sensible (images per run
> = 4,399, no run with more than 5% unclassified unless that is the finding),
> improve `wimpbench/dashboard.py` into a clear comparison dashboard (detector
> metrics by run, species F1 by run at the best threshold, recall vs threshold),
> write `docs/07_dashboard.Rmd` and a short findings summary in
> `results/awt_2026_11/README.md`, update the README results table, commit and
> push to main.
