"""Image-level test set: one image per validated sequence (docs/02b_select_by_image.Rmd).

Two steps:

source-export    ONE Camtrap DP export with bounding boxes on each source project
                 (approved by Matthew; the only write ever made to a source project).
                 The export id is saved in state/ before polling, and a second POST is
                 refused while one is recorded, so re-running never creates another.
select-by-image  for each sequence in selection.sequences_from, pick one image: the
                 highest detector score for the class's box type (animal, person,
                 vehicle), or the middle image (by timestamp) for blanks and fallbacks.
"""
import io
import json
import time
import zipfile
from pathlib import Path

import pandas as pd

from .api import Api
from .select_images import PUBLIC_COLUMNS, _download_sources

# Box type (media-level observationType) that scores each class.
BOX_TYPE = {"Human": "human", "Vehicle": "vehicle"}


def _export_dir(cfg, root, src):
    return Path(root) / "state" / cfg["test_set"] / "source_exports" / f"{src['env']}_{src['project_id'][:8]}"


def source_export(cfg, root, poll_seconds=30, max_wait=3 * 3600):
    """Create (once), wait for and unzip a bounding-box export of each source project."""
    for src in cfg["sources"]:
        env, pid = src["env"], src["project_id"]
        run_ids = {r["project_id"] for r in cfg["runs"]}
        assert pid not in run_ids, "a source project must not also be a run project"
        if src.get("bbox_export") is False:
            print(f"  {env} source: no bounding-box export (bbox_export: false); middle-image fallback")
            continue
        out = _export_dir(cfg, root, src)
        out.mkdir(parents=True, exist_ok=True)
        if (out / "observations.csv").exists():
            print(f"  {env} source: export already downloaded")
            continue
        api = Api(env)
        rec = out / "export.json"
        existing = [e for e in api.get(f"/projects/{pid}/exports")
                    if e.get("includeBoundingBoxes") and e.get("status") in ("Completed", "Pending", "Started", "Running")]
        if rec.exists():
            exp_id = json.loads(rec.read_text())["id"]
        elif existing:  # e.g. made in the WIMP web UI: reuse it, no new write
            exp_id = sorted(existing, key=lambda e: e["createdAt"])[-1]["id"]
            rec.write_text(json.dumps({"id": exp_id}))
            print(f"  {env} source: reusing existing bounding-box export")
        else:
            # Approved write: exactly one POST per source project, ever.
            r = api.call("POST", f"/projects/{pid}/exports", tries=1,
                         json={"includeBoundingBoxes": True})
            if r.status_code not in (200, 201, 202):
                raise RuntimeError(f"{env} POST export: {r.status_code} {r.text[:300]}")
            body = r.json()
            exp_id = body.get("id") or body.get("exportId")
            if not exp_id:
                raise RuntimeError(f"{env} POST export: no id in response keys {list(body)}")
            rec.write_text(json.dumps({"id": exp_id}))
            print(f"  {env} source: export created")
        t0 = time.time()
        while True:
            st = api.get(f"/projects/{pid}/exports/{exp_id}")
            state = st.get("status") or st.get("state")
            if str(state).lower() == "completed":
                break
            if str(state).lower() in ("failed", "error", "cancelled"):
                raise RuntimeError(f"{env} export {state}")
            if time.time() - t0 > max_wait:
                raise TimeoutError(f"{env} export still {state}; run source-export again")
            print(f"  {env} source: export {state}; waiting")
            time.sleep(poll_seconds)
        r = api.call("GET", f"/projects/{pid}/exports/{exp_id}/archive", timeout=3600)
        if r.status_code != 200:
            raise RuntimeError(f"{env} archive: {r.status_code} {r.text[:200]}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                if name.endswith(".csv") or name.endswith(".json"):
                    target = out / Path(name).name
                    if Path(name).name == "export.json":
                        target = out / "export_datapackage.json"
                    target.write_bytes(z.read(name))
        print(f"  {env} source: archive unzipped ({len(r.content) // 1_000_000} MB)")


def media_scores(cfg, root):
    """Per media file and box type, the highest detector score in the source exports."""
    parts = []
    for src in cfg["sources"]:
        if src.get("bbox_export") is False:
            continue
        o = pd.read_csv(_export_dir(cfg, root, src) / "observations.csv", dtype=str)
        o = o[o["observationLevel"].eq("media") & o["mediaID"].notna()]
        o = o[o["bboxX"].notna()] if "bboxX" in o else o
        o["score"] = pd.to_numeric(o["classificationProbability"], errors="coerce")
        o["box_type"] = o["observationType"].where(o["observationType"].isin(["human", "vehicle"]), "animal")
        o = o[o["observationType"].isin(["animal", "human", "vehicle"])]
        g = o.groupby(["mediaID", "box_type"])["score"].max().reset_index()
        g["source_env"] = src["env"]
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def select_by_image(cfg, root):
    root = Path(root)
    res = root / "results" / cfg["test_set"]
    res.mkdir(parents=True, exist_ok=True)
    folder = _download_sources(cfg, root)
    seqs = pd.read_csv(root / cfg["selection"]["sequences_from"], dtype=str)
    classes = cfg["sampling"]["classes"]

    media = []
    for src in cfg["sources"]:
        env, pid = src["env"], src["project_id"]
        p = f"{env}_{pid[:8]}_"
        m = pd.read_csv(folder / f"{p}media.csv", dtype=str,
                        usecols=["mediaID", "deploymentID", "fileName", "filePath", "mediaComments", "timestamp"])
        d = pd.read_csv(folder / f"{p}deployments.csv", dtype=str)[["deploymentID", "locationName"]]
        o = pd.read_csv(folder / f"{p}observations.csv", dtype=str)
        cb = o.groupby("eventID")["classifiedBy"].first()
        m["sequence_id"] = m["mediaComments"].str.extract(r"sequenceID:(\S+)", expand=False)
        m = m.merge(d, on="deploymentID", how="left")
        m["source_env"], m["source_project"] = env, src.get("project_name", pid)
        m["source_classified_by"] = m["sequence_id"].map(cb)
        media.append(m)
    media = pd.concat(media, ignore_index=True)
    media = media[media["sequence_id"].isin(set(seqs["source_sequence"]))]

    sc = media_scores(cfg, root)
    sc = sc.pivot_table(index=["source_env", "mediaID"], columns="box_type", values="score").reset_index()
    media = media.merge(sc, on=["source_env", "mediaID"], how="left")

    no_scores = {s["env"] for s in cfg["sources"] if s.get("bbox_export") is False}
    rows, summary = [], []
    by_seq = {k: g for k, g in media.groupby(["source_env", "sequence_id"])}
    for cls, spec in classes.items():
        cs = seqs[seqs["class"].eq(cls)]
        n_score = n_fallback = n_noscore = n_missing = 0
        for s in cs.itertuples(index=False):
            g = by_seq.get((s.source_env, s.source_sequence))
            if g is None or not len(g):
                n_missing += 1
                continue
            g = g.sort_values(["timestamp", "fileName"]).reset_index(drop=True)
            middle = g.iloc[(len(g) - 1) // 2]
            rule, pick, score = "middle", middle, None
            if cls != "Blank" and s.source_env in no_scores:
                rule = "middle_no_source_scores"
            elif cls != "Blank":
                col = BOX_TYPE.get(cls, "animal")
                if col in g and g[col].notna().any():
                    i = g[col].idxmax()
                    pick, score, rule = g.loc[i], float(g.loc[i, col]), f"max_{col}_score"
                else:
                    rule = "fallback_middle"
            if rule.startswith("max_"):
                n_score += 1
            elif rule == "fallback_middle":
                n_fallback += 1
            elif rule == "middle_no_source_scores":
                n_noscore += 1
            rows.append({
                "class": cls, "tag": spec["tag"], "in_model": spec.get("in_model", True),
                "file_name": pick.fileName, "source_label": cls,
                "source_camera": pick.locationName, "source_sequence": s.source_sequence,
                "source_media_id": pick.mediaID, "source_env": s.source_env,
                "source_project": pick.source_project, "source_classified_by": pick.source_classified_by,
                "source_url": pick.filePath, "timestamp": pick.timestamp,
                "local_file": f"data/{cfg['test_set']}/images/{cls}/{pick.locationName}__{pick.fileName}",
                "pick_score": score, "pick_rule": rule, "sequence_images": len(g),
            })
        summary.append({"class": cls, "sequences": len(cs), "picked_by_score": n_score,
                        "middle_blank": len(cs) - n_missing if cls == "Blank" else 0,
                        "fallback_no_scored_box": n_fallback,
                        "fallback_no_source_scores": n_noscore,
                        "sequence_not_found": n_missing})
        print(f"  {cls:28s} {len(cs):4d} sequences: {n_score} by score, {n_fallback} no box, "
              f"{n_noscore} no source scores, {n_missing} missing")
    man = pd.DataFrame(rows)
    private = root / "state" / cfg["test_set"] / "manifest_full.csv"
    private.parent.mkdir(parents=True, exist_ok=True)
    man.to_csv(private, index=False)
    man[PUBLIC_COLUMNS].to_csv(res / "manifest.csv", index=False)
    pd.DataFrame(summary).to_csv(res / "selection_summary.csv", index=False)
    print(f"manifest: {len(man)} images -> {private} (private), {res / 'manifest.csv'} (public)")
    return man
