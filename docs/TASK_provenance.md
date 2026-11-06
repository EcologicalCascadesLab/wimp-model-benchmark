# Task: publish the provenance tables for both AWT test sets

For the QCIF CV team to reproduce the benchmark (see `docs/REPRODUCE.md`). Matthew cleared
the AWT 2025 Skye source projects as public on 6 Nov 2026 (see CLAUDE.md hard rules).
Read-only: GET requests only. Do not upload, create, edit or delete anything on WIMP.

0. `git pull`. Check `WIMP_PROD_KEY` and `WIMP_TEST_KEY` are set (do not print them) and
   `python -m wimpbench check --config config/awt_2026_11.yaml` passes. Stop and report if not.
1. `python -m wimpbench.provenance --config config/awt_2026_11.yaml`
2. `python -m wimpbench.provenance --config config/awt_2026_11_by_image.yaml`
3. Check each `results/<set>/provenance/README.md`: images.csv row count must equal the
   manifest (4,399 and 2,905), 0 not found; benchmark_media.csv must have 5 runs and
   5 x the image count (report any shortfall, do not guess). If `state/<set>/manifest_full.csv`
   exists, also confirm its `source_media_id` values match images.csv.
4. Scan the new files before committing: no column or value containing `http`, `latitude`,
   `longitude`, `classifiedBy` or a person's name. Then commit only
   `results/*/provenance/` with the message "Add provenance tables (cameras, sequences,
   images, benchmark IDs) for both AWT test sets" and push to main.
5. Reply with the counts from both README files and the commit hash.
