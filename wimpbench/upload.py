"""Create one deployment per class in each benchmark project, upload the images, start the AI.

Layout of the local test set (written by `fetch`):
    data/<test_set>/images/<class>/<file>
    results/<test_set>/manifest.csv   (columns include class, scientific_name, local_file)

Per run project: one location and one camera named "benchmark", one tag per class
(the class's WIMP scientific name; 'blank', 'Homo sapiens', 'vehicle' for the
non-animal classes), one deployment per class carrying that tag. Colin's
evaluation reads the true label from the deployment tag.

Resumable: progress is kept in state/<test_set>/<run_id>.json.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .api import Api

BATCH = 10
WORKERS = 8
DEPLOY_START = "2015-01-01T00:00:00.000Z"
DEPLOY_END = "2026-12-31T23:59:59.000Z"


def _load_state(path):
    return json.loads(path.read_text()) if path.exists() else {"deployments": {}}


def _save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


def _resolve_tags(api, pid, names):
    r = api.call("POST", f"/projects/{pid}/tags/resolve", json={"tags": names})
    if r.status_code != 200:
        raise RuntimeError(f"tags/resolve: {r.status_code} {r.text[:300]}")
    j = r.json()
    items = j.get("tags", j) if isinstance(j, dict) else j
    out = {}
    for name, t in zip(names, items):
        out[name] = t["id"] if isinstance(t, dict) else t
    return out


def _location_and_camera(api, pid, cfg):
    loc_cfg = cfg.get("benchmark_location", {"name": "benchmark", "lat": -17.0, "lng": 145.6})
    locs = {l["name"]: l for l in api.get(f"/projects/{pid}/locations")}
    loc = locs.get(loc_cfg["name"])
    if not loc:
        r = api.call("POST", f"/projects/{pid}/locations",
                     json={"name": loc_cfg["name"], "lat": loc_cfg["lat"], "lng": loc_cfg["lng"]})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create location: {r.status_code} {r.text[:300]}")
        loc = r.json()
    cams = {c["label"]: c for c in api.get(f"/projects/{pid}/cameras")}
    cam = cams.get("benchmark")
    if not cam:
        r = api.call("POST", f"/projects/{pid}/cameras", json={"label": "benchmark"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create camera: {r.status_code} {r.text[:300]}")
        cam = r.json()
    return loc["id"], cam["id"]


def _send(api, pid, did, files):
    handles = [open(f, "rb") for f in files]
    try:
        body = [("file", (Path(f).name, h, "image/jpeg")) for f, h in zip(files, handles)]
        r = api.call("POST", f"/projects/{pid}/deployments/{did}/upload", files=body, timeout=600, tries=3)
    finally:
        for h in handles:
            h.close()
    return r.status_code == 200, (r.text[:200] if r.status_code != 200 else "")


def upload_run(cfg, run, manifest, root):
    """Upload the whole test set to one run's project."""
    pid = run.get("project_id")
    if not pid:
        raise SystemExit(f"{run['id']}: project_id is empty; create the project in the WIMP UI first")
    api = Api(run["env"])
    name = api.get(f"/projects/{pid}").get("name", "")
    if name.strip() != run["project_name"].strip():
        raise SystemExit(f"{run['id']}: project {pid} is called '{name}', config says '{run['project_name']}'")

    state_path = root / "state" / cfg["test_set"] / f"{run['id']}.json"
    state = _load_state(state_path)
    loc_id, cam_id = _location_and_camera(api, pid, cfg)
    classes = sorted(manifest["class"].unique())
    tag_of = {c: manifest.loc[manifest["class"] == c, "tag"].iloc[0] for c in classes}
    tag_ids = _resolve_tags(api, pid, [tag_of[c] for c in classes])

    for c in classes:
        d = state["deployments"].setdefault(c, {"uploaded": []})
        if d.get("finalized"):
            continue
        if not d.get("id"):
            body = {"location": loc_id, "camera": cam_id, "startDate": DEPLOY_START, "endDate": DEPLOY_END,
                    "utcOffset": "+10:00", "tags": [tag_ids[tag_of[c]]], "automaticAi": True,
                    "notes": f"benchmark {cfg['test_set']} class={c}"}
            r = api.call("POST", f"/projects/{pid}/deployments", json=body)
            if r.status_code not in (200, 201):
                raise RuntimeError(f"create deployment {c}: {r.status_code} {r.text[:300]}")
            d["id"] = r.json()["id"]
            _save_state(state_path, state)
        done = set(d["uploaded"])
        todo = [f for f in manifest.loc[manifest["class"] == c, "local_file"] if f not in done]
        batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        failed = []
        with ThreadPoolExecutor(WORKERS) as ex:
            for batch, (ok, msg) in zip(batches, ex.map(lambda b: _send(api, pid, d["id"], [str(root / f) for f in b]), batches)):
                if ok:
                    d["uploaded"].extend(batch)
                else:
                    failed.append((batch[0], msg))
                _save_state(state_path, state)
        if failed:
            print(f"  {run['id']} {c}: {len(failed)} batches failed, e.g. {failed[0]}; rerun upload")
            continue
        api.call("PATCH", f"/projects/{pid}/deployments/{d['id']}", json={"automaticAi": True})
        r = api.call("POST", f"/projects/{pid}/deployments/{d['id']}/finalizeUpload")
        if r.status_code in (200, 201, 204):
            d["finalized"] = True
        else:
            print(f"  {run['id']} {c}: finalize {r.status_code} {r.text[:200]}")
        _save_state(state_path, state)
        print(f"  {run['id']} {c}: {len(d['uploaded'])} images, finalized={d.get('finalized', False)}")


def status_run(run):
    api = Api(run["env"])
    pid = run["project_id"]
    rows = []
    for d in api.get(f"/projects/{pid}/deployments"):
        st = api.get(f"/projects/{pid}/deployments/{d['id']}/status")
        rows.append({"run": run["id"], "deployment": d["id"], "notes": d.get("notes", ""),
                     "status": st.get("status"), "ai": st.get("aiModelState"),
                     "images": st.get("nrAssets"), "sequences": st.get("nrSequences"),
                     "pct_ai": st.get("percentInspectedWithAi")})
    return rows
