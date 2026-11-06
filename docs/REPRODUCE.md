# Reproducing the AWT benchmark yourself

Written for the WIMP computer-vision team (QCIF). Everything below runs from a laptop with
Python and a WIMP API key. You do not need the original image files or anyone's hard drive:
the test images still sit in Skye Anderson's two WIMP projects, and the scripts pull them
from there. Every step except 5 is read-only (GET requests only).

## What was tested

| Test set | Images | Sequences | How images were chosen | Results |
|---|---:|---:|---|---|
| `awt_2026_11` (by sequence) | 4,399 | 2,905 | up to 2 random frames per validated sequence, spread across cameras | `results/awt_2026_11/` |
| `awt_2026_11_by_image` | 2,905 | the same 2,905 | 1 frame per sequence: highest MegaDetector score where an export had one (23), else the middle frame | `results/awt_2026_11_by_image/` |

Source projects (read-only), set in `config/awt_2026_11.yaml`:

| env | Project | ID |
|---|---|---|
| PROD | Wet Tropics Camera Trapping 2025 Skye Cassowary Production Environment | `b8b6ef55-ebe7-47f7-9034-b977399b77a2` |
| TEST | Wet Tropics Camera Trapping 2025 Skye Cassowary | `c31c2bf4-d660-44f8-bf4c-991a94e8f191` |

None of these cameras were in the AWT training data. Each test set went through five
benchmark projects (one per model run; project IDs under `runs:` in each config), all with
sequence cut-off 0 s (every image is its own sequence), AI sharing Private, and one
deployment per true class tagged with that class.

## The tables (which cameras, sequences and images)

`results/<set>/provenance/`:

| File | One row per | Use it to |
|---|---|---|
| `images.csv` | test image | find each image in the source project (`source_env`, `source_project_id`, `source_deployment_id`, `camera`, `source_sequence_id`, `source_media_id`, `timestamp`), its frame position in the sequence, and why the sequence counts as validated |
| `sequences.csv` | source sequence | see how many frames each sequence had and how many were used |
| `deployments.csv` | source camera deployment | camera, dates, review status (`percentInspected`), images used per class |
| `benchmark_media.csv` | image x model run | trace any prediction in a benchmark export (`bench_media_id`) back to `images.csv` via `file_name` |
| `../manifest.csv` | test image | the class and file name only (the original public manifest) |
| `../classwise_f1.csv` | species x run x scoring rule | class-wise F1 under the four rules below |

Coordinates, media URLs and the names of people who classified images are left out.

To trace one wrong prediction: take its `mediaID` from a run's export (or from
`colin_reports/<set>/Misclassified_Images_*.csv`), find it as `bench_media_id` in
`benchmark_media.csv`, take the `file_name`, and look it up in `images.csv`.

## 1. Set up (5 minutes)

```bash
git clone --recurse-submodules https://github.com/EcologicalCascadesLab/wimp-model-benchmark
cd wimp-model-benchmark
pip install -r requirements.txt
export WIMP_PROD_KEY=pk_...   # WIMP > User settings > API keys
export WIMP_TEST_KEY=pk_...
python -m wimpbench check --config config/awt_2026_11.yaml
```

`check` confirms the keys work and that you can read the source and benchmark projects.
If a project is not visible to your account, ask Matthew to add you to it.

## 2. Rebuild the tables (read-only)

```bash
python -m wimpbench.provenance --config config/awt_2026_11.yaml
python -m wimpbench.provenance --config config/awt_2026_11_by_image.yaml
```

This downloads the source projects' Camtrap DP tables (into `state/`, git-ignored),
matches them to the public manifests and writes the `provenance/` tables above.

## 3. Download the exact test images (read-only)

```bash
python -m wimpbench.provenance --config config/awt_2026_11.yaml --fetch
python -m wimpbench.provenance --config config/awt_2026_11.yaml --fetch --classes "Orthonyx spaldingii"
```

Images land in `data/<set>/images/<class>/<camera>__<file>` (the file names they were
uploaded with). The full by-sequence set is about 4,400 images.

## 4. Re-score the existing runs (read-only)

```bash
python -m wimpbench export   --config config/awt_2026_11.yaml   # Camtrap DP tables of the 5 runs
python -m wimpbench evaluate --config config/awt_2026_11.yaml   # Colin's reports, detector metrics, dashboard
python -m wimpbench.compare results/awt_2026_11 results/awt_2026_11_by_image
python -m wimpbench.classifier_only results/awt_2026_11 results/awt_2026_11_by_image
python -m wimpbench.compare_page results/awt_2026_11 results/awt_2026_11_by_image results/comparison_awt_2026_11.html
```

The scoring code is short and readable: `wimpbench/detector_metrics.py` (animal / human /
vehicle / blank), `wimpbench/evaluate.py` (calls Colin's workflow in `vendor/` unchanged),
`wimpbench/classifier_only.py` (the four views below).

## 5. Run a model again (writes to new projects only)

To test a changed model (e.g. after the Orthonyx label fix or the detection-score release),
create new benchmark projects in the WIMP web UI (`docs/03_wimp_projects.Rmd`: model,
detector threshold, cut-off 0 s, AI sharing Private), put their IDs in a copy of the config
under a new `test_set` name, then run `upload` (loop until exit code 0), `status`,
`export`, `evaluate`. The manifest and tables are reused unchanged.

## How the score differs from Rajmohan et al. 2026 (Sci Tot Env 1042, 181926)

The paper reports macro F1 0.909 for the fully fine-tuned SpeciesNet on held-out camera
deployments (0.964 on a random split). The benchmark's median species F1 is about 0.65-0.69.
They are not the same measurement:

| | Paper | This benchmark |
|---|---|---|
| Ground truth | per image (each image annotated in Wildlife Insights) | per sequence (WIMP validation); every frame of the sequence inherits the label |
| Input to the classifier | MegaDetector crop (MEWC snip, highest-confidence detection; MEWC default threshold, 0.05 in the Dec 2023 mewc-snip release) | full frame through the WIMP pipeline (detector at the project's threshold, then classifier) |
| Images with no animal found | not in the test set (it is built from snips) | counted as misses |
| Blanks, vehicles, people | excluded | included (scored separately in the detector table) |
| Species | 15 most common, each with >= 2,200 images, balanced | 14 model species plus dingo and murids, 13-250 images each |
| Coarser labels (genus, family) | not possible (15-class output) | stored by WIMP when the species call is weak; Colin's scoring counts them as wrong |

**Why the paper's test cannot be repeated exactly on this data.** Skye's PROD and TEST
projects were validated by sequence, so there is no per-image label saying which frames
actually show the animal, and no human-drawn box to crop. The paper's test crops cannot be
pushed through WIMP either, because the pipeline runs MegaDetector on full frames. The
closest we can get is to strip away, step by step, the parts of the benchmark that the paper
did not measure. `wimpbench/classifier_only.py` does this on the 14 model species only (no
blanks, people, vehicles, dingoes or murids), one prediction per image (highest
confidence):

| View | What it adds | Macro F1, TEST MD 0.50, by sequence | by image |
|---|---|---:|---:|
| `end_to_end` | every image; detector misses count as wrong | 0.63 | 0.61 |
| `detected` | drops images where no animal was returned (closest to "classifier on crops") | 0.72 | 0.69 |
| `rollup_ok` | as detected, coarser label containing the true species counts as correct | 0.75 | 0.72 |
| `map_fixed` | as detected, with the Orthonyx label fix (now on DEV) applied | 0.76 | 0.73 |

So about 0.09 of the gap is detector misses on frames that may be empty, about 0.03-0.04
is the Orthonyx mapping error, and about 0.03 is genus/family roll-up. Even then the
classifier-on-detections score is about 0.15 below 0.909. Likely reasons, still to be tested:
sequence labels on frames where the animal is partly in view; WIMP's crop and
preprocessing differing from MEWC's; class imbalance and rare classes (wallaby 60 images,
chowchilla 190) that the balanced paper test set did not have; and the dog label acting as
a catch-all (137 false "dog" calls on other species at MD 0.50).

**A test that would match the paper.** Validate a subset of these sequences per image (or
draw boxes) in WIMP, so each test image has its own label, then score animal images only,
one species per image, cut-off 0 s (already the benchmark setting). Once detection scores
are in the Camtrap export (next PROD release), the by-image set can also be rebuilt from the
highest-scoring frame of each sequence. Because the benchmark projects hold at most two
frames per sequence, this means uploading every frame of the 2,905 sequences to one new
benchmark project, letting the AI score them, and picking from that export (the source
projects stay untouched). Note that a frame picked by the detector's own score flatters
detector recall; species-classifier scores stay fair.
