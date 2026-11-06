"""Class-wise F1 under four scoring rules, from the committed public result files only.

python -m wimpbench.classifier_only results/awt_2026_11 results/awt_2026_11_by_image

Why: the published SpeciesNet fine-tuning result (Rajmohan et al. 2026, Sci Tot Env)
scores the classifier on MegaDetector crops of animal images only. The WIMP benchmark
scores the whole pipeline on every image. These four views move step by step from the
second towards the first, so the gap can be split into its parts.

Universe for every view: images whose true class is one of the 14 animal species the
Wet Tropics model has (no blanks, people, vehicles, dingoes or murids). One prediction
per image: the highest-confidence observation, as the paper classified the
highest-confidence snip.

  end_to_end   every image counts; a detector miss (blank / unclassified / human /
               vehicle) is a wrong answer. Closest to what a WIMP user sees.
  detected     images where the pipeline returned no animal are dropped, so the score
               covers only what MegaDetector found (closest to "classifier on crops").
  rollup_ok    as detected, and a coarser label that contains the true species
               (e.g. Thylogale or Mammalia for Thylogale stigmatica) counts as correct.
  map_fixed    as detected, with the Orthonyx label-mapping fix QCIF made on DEV
               (Orthonyx temminckii read as O. spaldingii) and the dog synonym merged.

Inputs: results/<set>/manifest.csv (true class counts) and
results/<set>/colin_reports/<set>/Misclassified_Images_*.csv (every image whose
prediction differed from the truth, with the prediction). Images not in the
misclassified file were predicted correctly. Writes results/<set>/classwise_f1.csv
and prints macro F1 per run and view.
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd

SPECIES = ["alectura lathami", "bos taurus", "canis lupus familiaris", "casuarius casuarius",
           "felis catus", "heteromyias cinereifrons", "hypsiprymnodon moschatus",
           "megapodius reinwardt", "orthonyx spaldingii", "perameles nasuta", "sus scrofa",
           "thylogale stigmatica", "uromys caudimaculatus", "wallabia bicolor"]
NO_ANIMAL = {"blank", "unclassified", "homo sapiens", "vehicle", None}
SYNONYM = {"canis familiaris": "canis lupus familiaris"}
MAP_FIX = {"orthonyx temminckii": "orthonyx spaldingii"}
MAMMALS = {"bos taurus", "canis lupus familiaris", "felis catus", "hypsiprymnodon moschatus",
           "perameles nasuta", "sus scrofa", "thylogale stigmatica", "uromys caudimaculatus",
           "wallabia bicolor"}
COARSER = {  # coarser label -> species of the 14 it contains
    "thylogale": {"thylogale stigmatica"}, "wallabia": {"wallabia bicolor"},
    "felis": {"felis catus"}, "canis": {"canis lupus familiaris"},
    "macropodidae": {"thylogale stigmatica", "wallabia bicolor"},
    "carnivora": {"felis catus", "canis lupus familiaris"},
    "mammalia": MAMMALS, "aves": set(SPECIES) - MAMMALS,
}
VIEWS = ["end_to_end", "detected", "rollup_ok", "map_fixed"]
MANIFEST_NAME = {"Human": "homo sapiens", "Blank": "blank", "Vehicle": "vehicle"}


def _run_label(path):
    m = re.search(r"Misclassified_Images_(.+?)_\d{8}_\d{6}\.csv$", Path(path).name)
    return m.group(1) if m else Path(path).stem


def _predictions(mis):
    mis = mis.copy()
    mis["pred"] = mis["pred_species"].where(mis["pred_species"].notna(), "unclassified").str.lower()
    mis["true"] = mis["true_species"].str.lower()
    mis = mis.sort_values("confidence", ascending=False).drop_duplicates("mediaID")
    return mis[mis["true"].isin(SPECIES)][["mediaID", "true", "pred"]]


def score(counts, wrong, view):
    """counts: true species -> images; wrong: rows (true, pred) of misclassified images."""
    rows = []
    w = wrong.copy()
    w["pred"] = w["pred"].replace(SYNONYM)
    if view == "map_fixed":
        w["pred"] = w["pred"].replace(MAP_FIX)
    if view != "end_to_end":
        w = w[~w["pred"].isin(NO_ANIMAL)]
    if view == "rollup_ok":
        ok = w.apply(lambda r: r["true"] in COARSER.get(r["pred"], ()), axis=1)
        w = w[~ok]
    w = w[w["pred"] != w["true"]]
    for sp in SPECIES:
        n_wrong_all = int((wrong["true"] == sp).sum())
        dropped = n_wrong_all - int((w["true"] == sp).sum()) if view != "end_to_end" else 0
        n = counts.get(sp, 0)
        # dropped rows are either removed (no animal) or turned correct (rollup / map fix)
        removed = 0
        if view != "end_to_end":
            ww = wrong[wrong["true"] == sp].copy()
            ww["pred"] = ww["pred"].replace(SYNONYM)
            removed = int(ww["pred"].isin(NO_ANIMAL).sum())
        n_eval = n - removed
        fn = int((w["true"] == sp).sum())
        tp = n_eval - fn
        fp = int((w["pred"] == sp).sum())
        rec = tp / n_eval if n_eval else None
        prec = tp / (tp + fp) if (tp + fp) else None
        f1 = 2 * rec * prec / (rec + prec) if rec and prec else 0.0
        rows.append({"view": view, "species": sp, "n_images": n, "n_scored": n_eval,
                     "tp": tp, "fp": fp, "fn": fn, "recall": rec, "precision": prec, "f1": f1})
    return rows


def run(folder):
    folder = Path(folder)
    man = pd.read_csv(folder / "manifest.csv")
    counts = man["class"].map(lambda c: MANIFEST_NAME.get(c, c)).str.lower().value_counts().to_dict()
    out = []
    for f in sorted(glob.glob(str(folder / "colin_reports" / folder.name / "Misclassified_Images_*.csv"))):
        label = _run_label(f)
        if "Megadetector" in label:
            continue
        wrong = _predictions(pd.read_csv(f))
        for v in VIEWS:
            for r in score(counts, wrong, v):
                out.append({"set": folder.name, "run": label, **r})
    df = pd.DataFrame(out)
    df.to_csv(folder / "classwise_f1.csv", index=False)
    return df


if __name__ == "__main__":
    for folder in sys.argv[1:]:
        df = run(folder)
        macro = df.groupby(["run", "view"])["f1"].mean().unstack()[VIEWS]
        print(Path(folder).name)
        print(macro.round(3).to_string())
