"""Download each run project's Camtrap DP tables into Colin's Input_Data layout.

    Input_Data/<test_set>/<run_id>/{deployments,media,observations}.csv

Uses the realtime CSV projections (GET /projects/{id}/<table>.csv), which need no
export job. Colin's loader needs mediaComments to carry sequenceID; this is
checked after download.
"""
from pathlib import Path

from .api import Api

TABLES = ("deployments", "media", "observations")


def run_label(run):
    thr = run.get("detector_threshold", "default")
    thr = "MD default" if str(thr) == "default" else f"MD {float(thr):.2f}"
    return f"{thr} ({run['env'].upper()})"


def export_run(cfg, run, root):
    api = Api(run["env"])
    pid = run["project_id"]
    out = Path(root) / "Input_Data" / cfg["test_set"] / run["id"]
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        r = api.call("GET", f"/projects/{pid}/{t}.csv", timeout=900)
        if r.status_code != 200:
            raise RuntimeError(f"{run['id']} {t}.csv: {r.status_code} {r.text[:200]}")
        (out / f"{t}.csv").write_text(r.text, encoding="utf-8")
    # Colin names each run by observations.classifiedBy, which is identical for runs
    # that differ only in detector threshold or environment. Label the model with the
    # run so reports and the comparison stay distinguishable. The raw table is kept.
    import pandas as pd
    raw = Path(root) / "state" / cfg["test_set"] / "raw_exports" / run["id"]
    raw.mkdir(parents=True, exist_ok=True)
    obs_path = out / "observations.csv"
    (raw / "observations.csv").write_text(obs_path.read_text(encoding="utf-8"), encoding="utf-8")
    obs = pd.read_csv(obs_path, dtype=str)
    label = run_label(run)
    machine = obs["classifiedBy"].fillna("").str.strip() != ""
    obs.loc[machine, "classifiedBy"] = obs.loc[machine, "classifiedBy"] + " | " + label
    obs.to_csv(obs_path, index=False)

    media_head = (out / "media.csv").read_text(encoding="utf-8")[:20000]
    if "sequenceID:" not in media_head:
        print(f"  WARNING {run['id']}: media.csv has no sequenceID in mediaComments; "
              "use observation_level=media or the export-job archive instead")
    return out
