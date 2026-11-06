"""Public provenance tables: exactly which cameras, sequences and images each test set used.

python -m wimpbench.provenance --config config/awt_2026_11.yaml
python -m wimpbench.provenance --config config/awt_2026_11_by_image.yaml

Read-only (GET requests only) against the source projects and the benchmark run
projects listed in the config. Starts from the committed public manifest
(results/<set>/manifest.csv: class + file name), so it documents the images that were
actually used, even if more sequences have been validated since.

Writes to results/<set>/provenance/:
  images.csv       one row per test image: class, source project / deployment / camera /
                   sequence / media IDs, timestamp, the image's position in its sequence,
                   how the sequence counts as validated, and (by image) the pick rule
  sequences.csv    one row per source sequence used: class, camera, frames in the
                   sequence, frames used
  deployments.csv  one row per source deployment: camera, dates, review status,
                   images used per class (no coordinates)
  benchmark_media.csv  one row per test image per model run: the benchmark project,
                   deployment and media IDs the image got on upload, so any prediction
                   in an export can be traced back to its source image
  README.md        column definitions and counts

Not written (kept out on purpose): coordinates, media URLs/file paths (signed links),
and the names of the people who classified sequences (only "human" vs "AI" is given).
"""
import argparse
import re
from pathlib import Path

import pandas as pd
import yaml

from .api import Api
from .select_images import _download_sources

ROOT = Path(__file__).resolve().parents[1]


def _source_tables(cfg, folder):
    media, seq_info, deps = [], [], []
    for src in cfg["sources"]:
        env, pid = src["env"], src["project_id"]
        p = f"{env}_{pid[:8]}_"
        m = pd.read_csv(folder / f"{p}media.csv", dtype=str)
        o = pd.read_csv(folder / f"{p}observations.csv", dtype=str)
        d = pd.read_csv(folder / f"{p}deployments.csv", dtype=str)
        s = pd.read_csv(folder / f"{p}status.csv")
        full = set(s.loc[s["percentInspected"] >= 99.9, "deploymentID"])
        m["source_sequence_id"] = m["mediaComments"].str.extract(r"sequenceID:(\S+)", expand=False)
        m["source_env"], m["source_project_id"] = env, pid
        m["source_project_name"] = src.get("project_name", pid)
        m = m.merge(d[["deploymentID", "locationName"]], on="deploymentID", how="left")
        m = m.sort_values(["source_sequence_id", "timestamp", "fileName"])
        m["frame_in_sequence"] = m.groupby("source_sequence_id").cumcount() + 1
        m["frames_in_sequence"] = m.groupby("source_sequence_id")["mediaID"].transform("size")
        media.append(m)
        o["by_human"] = o["classificationMethod"].eq("human")
        g = o.groupby("eventID").agg(classified_by_human=("by_human", "all"),
                                     deploymentID=("deploymentID", "first")).reset_index()
        g["deployment_fully_inspected"] = g["deploymentID"].isin(full)
        g["source_env"] = env
        seq_info.append(g.rename(columns={"eventID": "source_sequence_id"}).drop(columns="deploymentID"))
        keep = [c for c in ("deploymentID", "locationName", "deploymentStart", "deploymentEnd",
                            "cameraModel", "cameraHeight", "baitUse", "habitat", "deploymentTags")
                if c in d.columns]
        dd = d[keep].copy()
        dd = dd.merge(s[["deploymentID"] + [c for c in ("percentInspected",) if c in s.columns]],
                      on="deploymentID", how="left")
        dd["source_env"], dd["source_project_id"] = env, pid
        deps.append(dd)
    return pd.concat(media, ignore_index=True), pd.concat(seq_info, ignore_index=True), \
        pd.concat(deps, ignore_index=True)


def _benchmark_media(cfg):
    rows = []
    for run in cfg["runs"]:
        api = Api(run["env"])
        m = api.csv(f"/projects/{run['project_id']}/media.csv")
        d = api.csv(f"/projects/{run['project_id']}/deployments.csv")
        m = m.merge(d[["deploymentID"] + [c for c in ("deploymentTags",) if c in d.columns]],
                    on="deploymentID", how="left")
        m["bench_sequence_id"] = m["mediaComments"].str.extract(r"sequenceID:(\S+)", expand=False)
        m["run"], m["bench_env"], m["bench_project_id"] = run["id"], run["env"], run["project_id"]
        rows.append(m[["run", "bench_env", "bench_project_id", "deploymentID", "bench_sequence_id",
                       "mediaID", "fileName"]].rename(columns={"deploymentID": "bench_deployment_id",
                                                               "mediaID": "bench_media_id",
                                                               "fileName": "uploaded_file_name"}))
    return pd.concat(rows, ignore_index=True)


def build(cfg):
    res = ROOT / "results" / cfg["test_set"]
    out = res / "provenance"
    out.mkdir(parents=True, exist_ok=True)
    man = pd.read_csv(res / "manifest.csv", dtype=str)
    folder = _download_sources(cfg, ROOT)
    media, seqs, deps = _source_tables(cfg, folder)

    # by-image sets: the chosen source sequence per image is known; use it to disambiguate
    picks = None
    sel = cfg.get("selection", {}).get("sequences_from")
    if sel:
        picks = pd.read_csv(ROOT / sel, dtype=str)

    cand = man.merge(media, left_on="file_name", right_on="fileName", how="left")
    if picks is not None:
        key = set(zip(picks["source_env"], picks["source_sequence"]))
        ok = [(e, q) in key for e, q in zip(cand["source_env"], cand["source_sequence_id"])]
        cand = cand[pd.Series(ok, index=cand.index) | cand["mediaID"].isna()]
    n_match = cand.groupby("file_name")["mediaID"].nunique()
    ambiguous = sorted(n_match[n_match > 1].index)
    unmatched = sorted(n_match[n_match == 0].index)
    # the same camera file can sit in both the PROD and the TEST source project; keep the
    # first match (PROD listed first in the config) and say how many copies exist
    cand["source_matches"] = cand["file_name"].map(n_match)
    img = cand.drop_duplicates("file_name")
    img = img.merge(seqs, on=["source_env", "source_sequence_id"], how="left")
    img["validation_basis"] = img.apply(
        lambda r: "deployment fully inspected" if r.get("deployment_fully_inspected") is True
        else ("classified by a person" if r.get("classified_by_human") is True else "unknown"), axis=1)
    if cfg.get("selection"):
        rule_file = ROOT / "state" / cfg["test_set"] / "manifest_full.csv"
        if rule_file.exists():
            full = pd.read_csv(rule_file, dtype=str)[["file_name", "pick_rule", "pick_score"]]
            img = img.merge(full, on="file_name", how="left")
    img["uploaded_file_name"] = img["locationName"].fillna("") + "__" + img["file_name"]
    cols = ["class", "tag", "in_model", "file_name", "uploaded_file_name", "source_env",
            "source_project_name", "source_project_id", "deploymentID", "locationName",
            "source_sequence_id", "mediaID", "timestamp", "frame_in_sequence", "frames_in_sequence",
            "validation_basis", "source_matches", "pick_rule", "pick_score"]
    img = img[[c for c in cols if c in img.columns]].rename(columns={
        "deploymentID": "source_deployment_id", "locationName": "camera", "mediaID": "source_media_id"})
    img.to_csv(out / "images.csv", index=False)

    sq = img.groupby(["source_env", "source_sequence_id"]).agg(
        cls=("class", "first"), camera=("camera", "first"),
        source_deployment_id=("source_deployment_id", "first"),
        frames_in_sequence=("frames_in_sequence", "first"), frames_used=("file_name", "size"),
        first_timestamp=("timestamp", "min"), validation_basis=("validation_basis", "first")).reset_index()
    sq.rename(columns={"cls": "class"}).to_csv(out / "sequences.csv", index=False)

    used = img.groupby(["source_deployment_id", "class"]).size().unstack(fill_value=0)
    used["images_used"] = used.sum(axis=1)
    dep = deps.merge(used, left_on="deploymentID", right_index=True, how="inner")
    dep.rename(columns={"deploymentID": "source_deployment_id", "locationName": "camera"}) \
       .to_csv(out / "deployments.csv", index=False)

    bm = _benchmark_media(cfg)
    bm = bm.merge(img[["file_name", "uploaded_file_name"]], on="uploaded_file_name", how="inner")
    bm[["run", "file_name", "bench_env", "bench_project_id", "bench_deployment_id",
        "bench_sequence_id", "bench_media_id"]].to_csv(out / "benchmark_media.csv", index=False)

    lines = [f"# Provenance tables: {cfg['test_set']}", "",
             f"Built by `python -m wimpbench.provenance --config <config>` (read-only API calls).", "",
             f"- images.csv: {len(img)} images ({len(man)} in the public manifest; "
             f"{len(unmatched)} not found in the source export, {len(ambiguous)} with more than one match)",
             f"- sequences.csv: {len(sq)} source sequences",
             f"- deployments.csv: {len(dep)} source deployments (cameras), no coordinates",
             f"- benchmark_media.csv: {len(bm)} rows ({bm['run'].nunique()} model runs)", "",
             "Key columns: `source_media_id` / `source_sequence_id` / `source_deployment_id` are IDs in the",
             "source WIMP project (`source_env`, `source_project_id`); `bench_*` IDs are the copies in each",
             "benchmark run project. `frame_in_sequence` is the image's position (1 = first) among",
             "`frames_in_sequence` frames, ordered by timestamp. `validation_basis` is why the sequence",
             "counts as human-validated (WIMP exports have no per-sequence validation flag).",
             "Left out on purpose: coordinates, media URLs, and the names of people who classified images."]
    if unmatched:
        lines += ["", "Not found in source exports: " + ", ".join(unmatched[:50])]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[4:8]))
    return img


def fetch_images(cfg, dest=None, classes=None):
    """Download the exact test images listed in provenance/images.csv from the source projects.

    Needs read access to the source projects. Saves data/<set>/images/<class>/<camera>__<file>,
    the same names the images were uploaded with. Skips files already on disk.
    """
    res = ROOT / "results" / cfg["test_set"]
    img = pd.read_csv(res / "provenance" / "images.csv", dtype=str)
    if classes:
        img = img[img["class"].isin(classes)]
    folder = _download_sources(cfg, ROOT)
    paths = {}
    for src in cfg["sources"]:
        m = pd.read_csv(folder / f"{src['env']}_{src['project_id'][:8]}_media.csv", dtype=str,
                        usecols=["mediaID", "filePath"])
        paths.update({(src["env"], k): v for k, v in zip(m["mediaID"], m["filePath"])})
    dest = Path(dest or ROOT / "data" / cfg["test_set"] / "images")
    apis, n, missing = {}, 0, []
    for r in img.itertuples(index=False):
        out = dest / r[0] / r.uploaded_file_name  # r[0] is the class column
        if out.exists() and out.stat().st_size > 0:
            continue
        url = paths.get((r.source_env, r.source_media_id))
        if not url:
            missing.append(r.file_name)
            continue
        api = apis.setdefault(r.source_env, Api(r.source_env))
        resp = api.call("GET", url, timeout=300)
        if resp.status_code != 200:
            missing.append(r.file_name)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        n += 1
    print(f"downloaded {n} images to {dest}; {len(missing)} not available")
    return missing


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--fetch", action="store_true",
                    help="download the images listed in provenance/images.csv instead of building tables")
    ap.add_argument("--classes", nargs="*", help="with --fetch: only these classes")
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.config).read_text())
    fetch_images(cfg, classes=a.classes) if a.fetch else build(cfg)
