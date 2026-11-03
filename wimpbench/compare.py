"""Compare two test sets run on the same models (e.g. by-sequence vs by-image).

python -m wimpbench.compare results/awt_2026_11 results/awt_2026_11_by_image

Writes <second>/comparison.csv: one row per run and set with animal/blank/human/vehicle
recall and precision (detector_metrics.csv), the unclassified share, and the median
species F1 at each run's best threshold over the animal classes the model has.
"""
import sys
from pathlib import Path

import pandas as pd

RUN_ORDER = ["prod_awt_default", "test_awt_md025", "test_awt_md050", "test_awt_md075", "prod_md_v6"]
NOT_SPECIES = {"Blank", "Human", "Homo sapiens", "Vehicle", "vehicle", "blank",
               "Canis lupus dingo", "Muridae"}


def _species_run_id(label):
    if "MegaDetector V6" in label or "Megadetector" in label:
        return "prod_md_v6"
    if "(PROD)" in label:
        return "prod_awt_default"
    for thr, rid in (("0.25", "test_awt_md025"), ("0.50", "test_awt_md050"), ("0.75", "test_awt_md075")):
        if f"MD {thr}" in label:
            return rid
    return None


def summarise(folder):
    folder = Path(folder)
    det = pd.read_csv(folder / "detector_metrics.csv")
    rows = []
    for rid, g in det.groupby("run"):
        row = {"run": rid, "unclassified_share": g["unclassified_share"].iloc[0]}
        for c in ("animal", "blank", "human", "vehicle"):
            x = g[g["class"].eq(c)]
            row[f"{c}_recall"] = x["recall"].iloc[0] if len(x) else None
            row[f"{c}_precision"] = x["precision"].iloc[0] if len(x) else None
        rows.append(row)
    out = pd.DataFrame(rows)
    sp = pd.read_csv(folder / "species_metrics_best_threshold.csv")
    sp["run_id"] = sp["run"].map(_species_run_id)
    sp = sp[~sp["species"].isin(NOT_SPECIES)]
    med = sp.groupby("run_id")["f1_score"].median().rename("median_species_f1")
    nsp = sp.groupby("run_id")["species"].nunique().rename("n_species")
    out = out.merge(med, left_on="run", right_index=True, how="left").merge(
        nsp, left_on="run", right_index=True, how="left")
    out.loc[out["run"].eq("prod_md_v6"), "median_species_f1"] = None
    out["order"] = out["run"].map({r: i for i, r in enumerate(RUN_ORDER)})
    return out.sort_values("order").drop(columns="order")


def compare(a, b):
    sa, sb = summarise(a), summarise(b)
    sa.insert(0, "set", Path(a).name)
    sb.insert(0, "set", Path(b).name)
    both = pd.concat([sa, sb], ignore_index=True)
    both.to_csv(Path(b) / "comparison.csv", index=False)
    return both


if __name__ == "__main__":
    a, b = sys.argv[1:3]
    print(compare(a, b).round(3).to_string(index=False))
