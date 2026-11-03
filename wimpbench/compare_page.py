"""Build a web page comparing two test sets run on the same models (by sequence vs by image).

python -m wimpbench.compare_page results/awt_2026_11 results/awt_2026_11_by_image \
    results/comparison_awt_2026_11.html

Reads each set's detector_metrics.csv, species_metrics_best_threshold.csv and public
manifest.csv, plus the second set's selection_summary.csv (how each image was picked).
Writes one self-contained HTML page: dumbbell charts (set A vs set B per run) for the
detector and the species classifier, the selection summary, and a full table.
Nothing private is read or written: only the committed public result files.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from .compare import RUN_ORDER, NOT_SPECIES, summarise, _species_run_id

RUN_LABELS = {
    "prod_awt_default": "PROD · Wet Tropics · MD default",
    "test_awt_md025": "TEST · Wet Tropics · MD 0.25",
    "test_awt_md050": "TEST · Wet Tropics · MD 0.50",
    "test_awt_md075": "TEST · Wet Tropics · MD 0.75",
    "prod_md_v6": "PROD · MegaDetector V6 only",
}
METRICS = [  # (column, title, note)
    ("animal_recall", "Animal recall", "Share of animal images the detector called animal"),
    ("blank_recall", "Blank recall", "Share of empty images called blank"),
    ("human_recall", "Human recall", "Share of people images called human"),
    ("human_precision", "Human precision", "Share of 'human' calls that really were people"),
    ("vehicle_recall", "Vehicle recall", "Share of vehicle images called vehicle"),
    ("animal_precision", "Animal precision", "Share of 'animal' calls that really were animals"),
    ("median_species_f1", "Median species F1", "Median over the 14 model species, each at its best confidence threshold"),
    ("unclassified_share", "No AI result", "Share of images left with no AI label (lower is better)"),
]
MANIFEST_TO_SPECIES = {"blank": "Blank", "vehicle": "Vehicle", "Human": "Homo sapiens", "human": "Homo sapiens"}


def _num(x):
    return None if pd.isna(x) else round(float(x), 4)


def _species(folder):
    sp = pd.read_csv(Path(folder) / "species_metrics_best_threshold.csv")
    sp["run_id"] = sp["run"].map(_species_run_id)
    keep = ~sp["species"].isin(NOT_SPECIES - {"Homo sapiens"})
    sp = sp[keep & sp["run_id"].ne("prod_md_v6")]
    return {(r.run_id, r.species): {"f1": _num(r.f1_score), "recall": _num(r.recall),
                                     "precision": _num(r.precision), "conf": r.model_confidence}
            for r in sp.itertuples()}


def _counts(folder):
    m = pd.read_csv(Path(folder) / "manifest.csv")
    return {MANIFEST_TO_SPECIES.get(k, k): int(v) for k, v in m["class"].value_counts().items()}


def build(a, b, out):
    a, b = Path(a), Path(b)
    sa, sb = summarise(a), summarise(b)
    detector = []
    for rid in RUN_ORDER:
        ra, rb = sa[sa.run.eq(rid)], sb[sb.run.eq(rid)]
        row = {"run": rid, "label": RUN_LABELS[rid]}
        for col, *_ in METRICS:
            row[col] = [_num(ra[col].iloc[0]) if len(ra) else None,
                        _num(rb[col].iloc[0]) if len(rb) else None]
        detector.append(row)

    spa, spb = _species(a), _species(b)
    na, nb = _counts(a), _counts(b)
    species = sorted({s for _, s in spa} | {s for _, s in spb})
    sp_rows = {rid: [{"species": s, "a": spa.get((rid, s)), "b": spb.get((rid, s)),
                      "na": na.get(s), "nb": nb.get(s)} for s in species]
               for rid in RUN_ORDER if rid != "prod_md_v6"}

    sel = pd.read_csv(b / "selection_summary.csv")
    sel_rows = [{"cls": r["class"], "n": int(r.sequences), "score": int(r.picked_by_score),
                 "blank": int(r.middle_blank),
                 "middle": int(r.fallback_no_scored_box + r.fallback_no_source_scores)}
                for _, r in sel.iterrows()]

    data = {"setA": a.name, "setB": b.name, "metrics": METRICS, "detector": detector,
            "species": sp_rows, "runLabels": RUN_LABELS, "selection": sel_rows,
            "nA": int(sum(na.values())), "nB": int(sum(nb.values()))}
    html = TEMPLATE.replace("/*DATA*/null", json.dumps(data))
    Path(out).write_text(html, encoding="utf-8")
    return out


TEMPLATE = (Path(__file__).with_name("compare_page_template.html")).read_text(encoding="utf-8")

if __name__ == "__main__":
    print(build(*sys.argv[1:4]))
