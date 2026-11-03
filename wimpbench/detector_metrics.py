"""Detector-level (MegaDetector) scoring of a Camtrap DP export.

Colin's workflow scores species labels. This module collapses both the true
label and the prediction to the four detector classes, so the detector stage
can be judged on its own:

    animal | human | vehicle | blank      (+ 'unclassified' for no AI result)

True class: from the deployment tag (one deployment per class in a benchmark
project). Tags 'blank', 'homo sapiens'/'human', 'vehicle' map to themselves;
any other tag is an animal.

Predicted class: from observationType (not scientificName, because vehicle and
blank observations carry no scientific name and Colin's loader would count a
vehicle prediction as 'blank'). 'unknown' ("Animal, unidentified") counts as
animal. A Homo sapiens animal row counts as human.

An image can have several observations (event-level: all observations of its
sequence). It is scored correct if any of them matches the true class;
otherwise its prediction is the first of human > vehicle > animal > blank >
unclassified present.
"""
from pathlib import Path

import pandas as pd

CLASSES = ["animal", "human", "vehicle", "blank"]
PRIORITY = ["human", "vehicle", "animal", "blank", "unclassified"]
HUMAN = {"homo sapiens", "human", "humans", "person"}
VEHICLE = {"vehicle", "vehicles"}
BLANK = {"blank", "empty", ""}


def true_class(tag):
    t = str(tag or "").strip().lower()
    if t in BLANK:
        return "blank"
    if t in HUMAN:
        return "human"
    if t in VEHICLE:
        return "vehicle"
    return "animal"


def pred_class(observation_type, scientific_name):
    ot = str(observation_type or "").strip().lower()
    sn = str(scientific_name or "").strip().lower()
    if ot in ("", "nan"):
        return "unclassified"  # no observation joined to this image
    if ot == "unclassified":
        return "unclassified"
    if ot == "blank":
        return "blank"
    if ot == "vehicle":
        return "vehicle"
    if ot == "human" or sn in HUMAN:
        return "human"
    if ot in ("animal", "unknown"):
        return "animal"
    return ot  # unexpected type is reported as itself


def load(export_folder, observation_level="event"):
    """Per-image table: mediaID, true, pred (one row per image)."""
    folder = Path(export_folder)
    obs = pd.read_csv(folder / "observations.csv", dtype=str)
    media = pd.read_csv(folder / "media.csv", dtype=str)
    deps = pd.read_csv(folder / "deployments.csv", dtype=str)[["deploymentID", "deploymentTags"]]

    if "observationLevel" in obs.columns:
        lvl = obs["observationLevel"].fillna("").str.strip().str.lower()
        obs = obs[lvl.isin(["event", ""])] if observation_level == "event" else obs[lvl == "media"]

    media = media[["mediaID", "deploymentID", "mediaComments"]].copy()
    media["sequenceID"] = media["mediaComments"].str.extract(r"sequenceID:(\S+)", expand=False)
    if observation_level == "event":
        m = media.merge(obs[["eventID", "observationType", "scientificName"]],
                        left_on="sequenceID", right_on="eventID", how="left")
    else:
        m = media.merge(obs[["mediaID", "observationType", "scientificName"]], on="mediaID", how="left")
    m = m.merge(deps, on="deploymentID", how="left")
    m["true"] = m["deploymentTags"].map(true_class)
    m["pred_one"] = [pred_class(a, b) for a, b in zip(m["observationType"], m["scientificName"])]

    rows = []
    for media_id, g in m.groupby("mediaID", sort=False):
        t = g["true"].iloc[0]
        preds = set(g["pred_one"])
        p = t if t in preds else next((c for c in PRIORITY if c in preds), sorted(preds)[0])
        rows.append((media_id, g["deploymentID"].iloc[0], t, p))
    return pd.DataFrame(rows, columns=["mediaID", "deploymentID", "true", "pred"])


def metrics(per_image):
    """Recall / precision / F1 for each detector class, plus the confusion matrix."""
    cm = pd.crosstab(per_image["true"], per_image["pred"])
    out = []
    for c in CLASSES:
        tp = int(((per_image["true"] == c) & (per_image["pred"] == c)).sum())
        n_true = int((per_image["true"] == c).sum())
        n_pred = int((per_image["pred"] == c).sum())
        recall = tp / n_true if n_true else float("nan")
        precision = tp / n_pred if n_pred else float("nan")
        f1 = 2 * recall * precision / (recall + precision) if recall and precision and recall + precision else float("nan")
        out.append({"class": c, "n_images": n_true, "tp": tp, "recall": recall, "precision": precision, "f1": f1})
    summary = pd.DataFrame(out)
    summary.attrs["unclassified_share"] = float((per_image["pred"] == "unclassified").mean())
    return summary, cm
