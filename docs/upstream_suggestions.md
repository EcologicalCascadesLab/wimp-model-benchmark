# Suggestions for Colin's model-benchmark-testing-workflow

Found while automating the workflow. None of these are changed in `vendor/`; this
repository works around them in `wimpbench/`.

1. **Vehicle predictions scored as blank.** `data_loader.prepare_observations` fills
   `scientificName` for `blank` and `unclassified` observation types only. Vehicle
   observations have no scientific name, so `pred_species` becomes `blank` and a
   correct vehicle call counts as a miss (and a blank false positive). Suggest
   labelling `observationType == vehicle` as `Vehicle` (and matching a `vehicle`
   deployment tag). Workaround here: `wimpbench/detector_metrics.py` scores the
   detector classes from `observationType`.
2. **Runs of the same model share a name.** The model name comes from
   `observations.classifiedBy`, which is identical for runs that differ only in
   detector threshold or environment, so the comparison report cannot tell them
   apart. Suggest an optional model label per export (e.g. from the folder name).
   Workaround here: `export` appends the run label to `classifiedBy`.
3. **"Animal, unidentified" (`observationType = unknown`).** Since QCIF's October
   2026 pipeline change, detector-only animal results export as `unknown` with no
   scientific name; they currently count as `blank` predictions. Suggest a separate
   `Animal (unidentified)` prediction label so detector recall and classifier
   abstention can be told apart.
4. **(WIMP, not Colin's workflow) Export MegaDetector boxes and scores.** The Camtrap DP
   export with `includeBoundingBoxes` only has media-level rows for boxes stored with
   observations (3,901 of 255,227 images on the TEST AWT source, nearly all from the
   validator, scores mostly 1.0). MegaDetector's per-image detections and confidences
   are not exported, and no API endpoint returns them, so a test set cannot pick each
   sequence's best image by detector score (see `docs/02b_select_by_image.Rmd`). Suggest
   exporting machine detections as media-level observations (`classificationMethod =
   machine`, `classifiedBy = MegaDetector ...`, `classificationProbability` = score).
   Creating an export also needs the Maintainer role, and a lower role gets 401 rather
   than 403.
