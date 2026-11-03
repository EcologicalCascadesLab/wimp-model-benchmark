"""Build the validated-image test set from existing WIMP projects (read-only).

select: download the source projects' Camtrap DP tables and deployment review status,
        keep sequences a person has validated, and sample images per class.
        Writes results/<set>/manifest.csv and results/<set>/class_availability.csv.

A sequence counts as validated when its deployment is fully inspected
(percentInspected >= 99.9 in the deployment status) or its observation was made
by a person (classificationMethod = human). The Camtrap DP export has no
per-sequence validation flag, so this is the strictest rule the API allows.
Sequences with more than one label (two species, or animal + human) are left out
so every image has exactly one true class.

Sampling per class (deterministic, seeded):
  - round-robin across cameras, then across sequences within a camera, one image
    at a time, so the sample spreads over as many cameras and sequences as possible;
  - at most `max_per_sequence` images per sequence while other sequences remain;
  - at most `max_share_per_camera` of the class from one camera, relaxed only when
    the class has too few cameras to reach `per_class`.
Images that appear in more than one source project (same location + file name)
are kept once.
"""
import math
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .api import Api


def _download_sources(cfg, root):
    out = Path(root) / "state" / cfg["test_set"] / "sources"
    out.mkdir(parents=True, exist_ok=True)
    for src in cfg["sources"]:
        env, pid = src["env"], src["project_id"]
        api = Api(env)
        for t in ("deployments", "observations", "media"):
            f = out / f"{env}_{pid[:8]}_{t}.csv"
            if not f.exists():
                r = api.call("GET", f"/projects/{pid}/{t}.csv", timeout=1200)
                if r.status_code != 200:
                    raise RuntimeError(f"{env} {t}.csv: {r.status_code}")
                f.write_text(r.text, encoding="utf-8")
        f = out / f"{env}_{pid[:8]}_status.csv"
        if not f.exists():
            rows = []
            for d in api.get(f"/projects/{pid}/deployments"):
                st = api.get(f"/projects/{pid}/deployments/{d['id']}/status")
                rows.append({"deploymentID": d["id"], **st})
            pd.DataFrame(rows).to_csv(f, index=False)
    return out


def _pool(cfg, folder):
    parts = []
    for src in cfg["sources"]:
        env, pid = src["env"], src["project_id"]
        p = f"{env}_{pid[:8]}_"
        o = pd.read_csv(folder / f"{p}observations.csv", dtype=str)
        m = pd.read_csv(folder / f"{p}media.csv", dtype=str,
                        usecols=["mediaID", "deploymentID", "fileName", "filePath", "mediaComments", "timestamp"])
        d = pd.read_csv(folder / f"{p}deployments.csv", dtype=str)[["deploymentID", "locationName"]]
        s = pd.read_csv(folder / f"{p}status.csv")
        full = set(s.loc[s["percentInspected"] >= 99.9, "deploymentID"])
        o["validated"] = o["deploymentID"].isin(full) | o["classificationMethod"].eq("human")
        o["label"] = o["scientificName"].where(o["observationType"].isin(["animal", "human"]), o["observationType"])
        g = o.groupby("eventID").agg(n=("label", "nunique"), label=("label", "first"),
                                     otype=("observationType", "first"), val=("validated", "all"),
                                     classified_by=("classifiedBy", "first"))
        g = g[(g["n"] == 1) & g["val"] & ~g["otype"].isin(["unclassified", "unknown"])].reset_index()
        m["eventID"] = m["mediaComments"].str.extract(r"sequenceID:(\S+)", expand=False)
        mm = m.merge(g, on="eventID").merge(d, on="deploymentID", how="left")
        mm["source_env"], mm["source_project"] = env, src.get("project_name", pid)
        parts.append(mm)
    pool = pd.concat(parts, ignore_index=True)
    pool["key"] = pool["locationName"].fillna("") + "/" + pool["fileName"]
    return pool.drop_duplicates("key")


def _sample(rows, n, max_seq, max_cam_share, rng):
    by_cam = defaultdict(lambda: defaultdict(list))
    for r in rows.itertuples(index=False):
        by_cam[r.locationName][r.eventID].append(r)
    for cam in by_cam.values():
        for seq in cam.values():
            rng.shuffle(seq)
    cams = list(by_cam)
    rng.shuffle(cams)
    cam_cap = max(1, math.floor(n * max_cam_share))
    if len(cams) * cam_cap < n:  # too few cameras: relax the per-camera cap
        cam_cap = math.ceil(n / max(1, len(cams)))
    taken, per_cam, per_seq = [], defaultdict(int), defaultdict(int)
    for seq_cap in (max_seq, 10 ** 6):  # second pass relaxes the per-sequence cap
        progress = True
        while len(taken) < n and progress:
            progress = False
            for cam in cams:
                if len(taken) >= n or per_cam[cam] >= cam_cap:
                    continue
                seqs = sorted(by_cam[cam], key=lambda s: per_seq[s])
                for s in seqs:
                    if per_seq[s] < seq_cap and by_cam[cam][s]:
                        taken.append(by_cam[cam][s].pop())
                        per_seq[s] += 1
                        per_cam[cam] += 1
                        progress = True
                        break
        if len(taken) >= n:
            break
    return taken


def select(cfg, root, config_path=None):
    root = Path(root)
    res = root / "results" / cfg["test_set"]
    res.mkdir(parents=True, exist_ok=True)
    folder = _download_sources(cfg, root)
    pool = _pool(cfg, folder)
    sp = cfg["sampling"]
    rng = random.Random(sp.get("seed", 1))
    avail = pool.groupby("label").agg(images=("mediaID", "size"), sequences=("eventID", "nunique"),
                                      cameras=("locationName", "nunique")).sort_values("images", ascending=False)
    avail.to_csv(res / "class_availability.csv")

    rows = []
    for cls, spec in sp["classes"].items():
        labels = spec["source_labels"]
        sub = pool[pool["label"].isin(labels)]
        picked = _sample(sub, sp["per_class"], sp["max_per_sequence"], sp["max_share_per_camera"], rng)
        for r in picked:
            rows.append({
                "class": cls, "tag": spec["tag"], "in_model": spec.get("in_model", True),
                "file_name": r.fileName, "source_label": r.label, "source_camera": r.locationName,
                "source_sequence": r.eventID, "source_media_id": r.mediaID, "source_env": r.source_env,
                "source_project": r.source_project, "source_classified_by": r.classified_by,
                "source_url": r.filePath, "timestamp": r.timestamp,
                "local_file": f"data/{cfg['test_set']}/images/{cls}/{r.locationName}__{r.fileName}",
            })
        print(f"  {cls:32s} {len(picked):4d} images from {sub['locationName'].nunique()} cameras "
              f"({len(sub)} validated available)")
    man = pd.DataFrame(rows)
    man.to_csv(res / "manifest.csv", index=False)
    print(f"manifest: {len(man)} images, {man['class'].nunique()} classes -> {res / 'manifest.csv'}")
    return man


def fetch(cfg, root, classes=None):
    """Download manifest images not yet on disk (used for local copies; upload streams on its own)."""
    root = Path(root)
    man = pd.read_csv(root / "results" / cfg["test_set"] / "manifest.csv", dtype=str)
    if classes:
        man = man[man["class"].isin(classes)]
    apis = {}
    n = 0
    for r in man.itertuples(index=False):
        dest = root / r.local_file
        if dest.exists() and dest.stat().st_size > 0:
            continue
        api = apis.setdefault(r.source_env, Api(r.source_env))
        resp = api.call("GET", r.source_url, timeout=300)
        if resp.status_code != 200:
            print(f"  {r.file_name}: {resp.status_code}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        n += 1
    print(f"downloaded {n} images")
