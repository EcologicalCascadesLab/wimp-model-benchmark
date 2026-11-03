# AWT benchmark, 3 November 2026: findings

4,399 human-validated images from Skye Anderson's Wet Tropics 2025 projects (19 classes,
up to 250 images each), run through five WIMP projects. Open `dashboard.html` for all
numbers; Colin's full reports are in `colin_reports/`.

## Headlines

1. **TEST's October pipeline fixes work.** At the same detector threshold (0.50), TEST
   cut false "human" labels sharply: human precision rose from 0.34 on PROD to 0.82 on
   TEST, and Homo sapiens F1 from 0.45 to 0.75. Images left with no AI result fell from
   6.5% (PROD) to 0.1% (TEST). Species F1 for animals is otherwise about the same on
   PROD and TEST at 0.50.
2. **The MegaDetector threshold is a straight trade-off.** Raising it from 0.25 to 0.50
   to 0.75 lowered animal recall (0.92, 0.82, 0.68) and raised blank recall (0.09, 0.50,
   0.79). Species F1 was best at 0.50 or 0.75 for almost every class and worst at 0.25.
   Across both, **0.50 is the best default**; 0.75 suits projects where wading through
   empty images costs more than missing some animals.
3. **MegaDetector V6 on its own in PROD is not usable as configured.** 85% of images
   came back Unclassified, including almost every animal image (animal recall 0). This
   looks like the PROD pipeline gap QCIF fixed on TEST ("detections with no species
   written as nothing"), and should be checked with QCIF before anyone uses that model.
4. **Species with problems in the Wet Tropics model:**
   - Northern chowchilla (*Orthonyx spaldingii*) scores 0: the model labels it as
     *Orthonyx temminckii* (logrunner, a southern species), 58 of 190 images at 0.50.
     This looks like a label-mapping error in the model.
   - Dingo images are labelled domestic dog (197 of 250). Expected, since the model has
     one dog label; dingo/dog should be treated as one class or the model given a dingo class.
   - Domestic dog itself is weak (F1 about 0.43), as are giant white-tailed rat (0.53),
     musky rat-kangaroo (0.50), swamp wallaby (0.44, only 60 images) and grey-headed
     robin (0.61).
   - Murids (not a model class) are called giant white-tailed rat or bandicoot.
   - Best classes: cassowary (0.84), brush-turkey and cattle (0.80+), scrubfowl and pig (0.71-0.72).
5. **Vehicles:** detector recall about 0.62 at every threshold; the rest are called
   blank or human. (Colin's species table scores vehicle as 0 because of a known
   loader issue; use the detector table.)

## Caveats

- **Sequence labels applied to single images.** Validation on WIMP is per sequence, so
  an image from a validated "Sus scrofa" sequence may be a frame after the pig left.
  Such frames count as missed detections, so animal recall and blank precision here are
  conservative (biased low). Future test sets should use image-level (bounding-box)
  validations where they exist, or sample the frame with the highest source detection.
- "Validated" = sequence in a fully reviewed deployment or classified by a person; the
  export has no per-sequence validation flag.
- Small classes: Wallabia bicolor (60), Heteromyias (189), Orthonyx (190), dog (212).
- One test set from one region; results apply to the Wet Tropics model on similar cameras.

## Next steps suggested

- Send QCIF: finding 3 (MD V6 PROD), the Orthonyx label, and whether to make 0.50 the default.
- Rerun after QCIF's next pipeline change with `python -m wimpbench upload/export/evaluate`
  on new projects (the test set and manifest are reusable).
