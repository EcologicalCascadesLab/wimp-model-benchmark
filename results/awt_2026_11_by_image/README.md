# AWT benchmark, by image (one image per sequence), 3 November 2026: findings

The same 2,905 validated sequences as the by-sequence test set (`results/awt_2026_11/`),
with **one image per sequence**, run through five new WIMP projects with the same
models and detector thresholds. Open `dashboard.html` for all numbers. Colin's full
reports are in `colin_reports/`. How the images were picked:
`docs/02b_select_by_image.Rmd`, with counts in `selection_summary.csv`.

## Important: this is mostly a middle-image set, not a best-image set

The plan was to pick each sequence's image with the highest MegaDetector score. That
was not possible for almost all sequences:

- **PROD source (962 sequences, 881 non-blank):** no bounding-box export could be made.
  The account is Project coordinator, not Maintainer, on that project. These
  sequences use the middle image.
- **TEST source (1,943 sequences):** the bounding-box export does not contain
  MegaDetector's detections. It only has boxes saved with media-level observations,
  covering 3,901 of 255,227 images and almost all from the human validator, with
  scores of about 1.0. Only 23 sequences had a scored box of the right type. The
  other 1,757 use the middle image.
- Blank sequences use the middle image by design (244).

In total, **23 of 2,905 images (0.8%) were picked by score**. The rest are the middle
image of the sequence. The suggestion to WIMP to export detector boxes and scores is
in `docs/upstream_suggestions.md`.

## By image vs by sequence

| Run | Set | Animal recall | Animal precision | Blank recall | Blank precision† | Human recall | Human precision | Vehicle recall | Vehicle precision | No AI result | Median species F1* |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD, Wet Tropics, MD default | by sequence | 0.77 | 0.96 | 0.34 | 0.21 | 0.86 | 0.34 | 0.62 | 0.94 | 6.5% | 0.65 |
| | **by image** | **0.80** | 0.94 | 0.39 | 0.36 | 0.88 | 0.42 | 0.55 | 0.94 | 5.9% | **0.69** |
| TEST, Wet Tropics, MD 0.25 | by sequence | 0.92 | 0.92 | 0.09 | 0.07 | 0.79 | 0.80 | 0.64 | 0.95 | 0.0% | 0.54 |
| | **by image** | **0.94** | 0.88 | 0.08 | 0.11 | 0.85 | 0.79 | 0.56 | 0.95 | 0.0% | **0.59** |
| TEST, Wet Tropics, MD 0.50 | by sequence | 0.82 | 0.96 | 0.50 | 0.15 | 0.78 | 0.82 | 0.62 | 0.96 | 0.1% | 0.65 |
| | **by image** | **0.85** | 0.94 | 0.50 | 0.24 | 0.83 | 0.80 | 0.55 | 0.95 | 0.1% | **0.69** |
| TEST, Wet Tropics, MD 0.75 | by sequence | 0.68 | 0.99 | 0.79 | 0.13 | 0.76 | 0.83 | 0.60 | 0.96 | 0.0% | 0.64 |
| | **by image** | **0.73** | 0.99 | 0.77 | 0.20 | 0.79 | 0.81 | 0.53 | 0.95 | 0.0% | **0.67** |
| PROD, MegaDetector V6 only | by sequence | 0.00 | - | 0.34 | 0.21 | 0.52 | 0.84 | 0.44 | 0.95 | 84.6% | n/a |
| | **by image** | 0.00 | - | 0.39 | 0.36 | 0.54 | 0.80 | 0.41 | 0.96 | 82.9% | n/a |

*Median F1 at each run's best confidence threshold over the 14 animal classes the
model has (same definition as the main README). Source: `comparison.csv`
(`python -m wimpbench.compare results/awt_2026_11 results/awt_2026_11_by_image`).

†Blank precision depends on how many animal images there are for each blank image
(2,661 non-blank to 244 blank here, against 4,149 to 250 by sequence), so it is not
comparable between the sets.

## Findings

1. **Scoring one middle image per sequence gives slightly better numbers than scoring
   up to two random images.** Animal recall rose by 0.01 to 0.05 and median species F1
   by 0.03 to 0.05 on every Wet Tropics run. The likely reason: a random frame is
   more often one where the animal has left (or not yet entered) the view than the
   middle frame is, so some by-sequence "misses" were empty frames, not model errors.
2. **The conclusions do not change.** MD 0.50 is still the best balance: animal recall
   0.85, blank recall 0.50, species F1 0.69, the best of the TEST thresholds. 0.25 still
   misses almost every blank (0.08) and gives the lowest species F1. MegaDetector V6
   alone on PROD still returns no result for over 80% of images. TEST still has far
   fewer images with no AI result than PROD (0.1% vs 5.9%).
3. **Species problems are the same.** The model still labels northern chowchilla as
   *Orthonyx temminckii* (17 of 40 observations at MD 0.50) and dingoes as domestic
   dog (165 of 216 observations). Dog F1 fell (0.43 to 0.19 at MD 0.50) because there are only 40 dog images
   now against 212 dingo images, most labelled dog, so dog precision dropped. That is the
   class mix, not the model. Swamp wallaby (13 sequences) and grey-headed robin
   (54) are too small to read much into.
4. **Vehicle recall fell (about 0.62 to 0.55).** Likely because the middle image of a
   vehicle sequence is often after the vehicle has gone past, while the by-sequence set's two random
   frames had more chances to catch it. This is the one place where the middle image
   is a worse pick than a random one.

## How to read detector recall in the two sets

- **By sequence** is a **lower bound**. Images were drawn at random from validated
  sequences, so some are frames with nothing in them.
- **A true by-image set** (each sequence's image with the highest detector score) would
  be an **upper bound**, because images would be chosen by the detector itself.
- **This set** is neither: it is almost all middle images, chosen without the
  detector. Its detector recall sits between the two bounds and is the fairest
  single-image estimate we have.
- **Species-classifier comparisons are fair in both sets.** The classifier only sees
  what the detector found, and neither set was chosen using the classifier.

## Caveats

- 881 PROD-source non-blank sequences use the middle image for lack of an export
  (see above). Within this set, the PROD- and TEST-source picks use the same rule in
  practice, since only 23 TEST picks used a score.
- Small classes: Wallabia bicolor (13), Orthonyx spaldingii (40), Canis lupus
  familiaris (40), Heteromyias cinereifrons (54), Bos taurus (57).
- The same caveats as the by-sequence set apply (`results/awt_2026_11/README.md`).
