"""Put the test set into every benchmark project and start the AI.

Per run project: one location and one camera named "benchmark", one tag per class
(the class's WIMP name; 'blank', 'Homo sapiens', 'vehicle' for non-animal classes),
one deployment per class carrying that tag. Colin's evaluation reads the true label
from the deployment tag.

Images are streamed: each batch of 10 is downloaded from its source project (or
read from data/ if already there), uploaded to every run that still needs it, and
the downloaded copy is deleted. Peak disk use is a few hundred MB, whatever the
size of the test set. When a class is complete in a run, its deployment gets
automaticAi=true and is finalized, which queues sequence creation and the AI.

Resumable: state/<set>/upload_state.json records every file uploaded per run.
Time-boxed: --max-seconds stops cleanly between batches (exit code 75 = run again).
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .api import Api

BATCH = 10
WORKERS = 12
DEPLOY_START = "2015-01-01T00:00:00.000Z"
DEPLOY_END = "2026-12-31T23:59:59.000Z"
_lock = threading.Lock()


def _resolve_tags(api, pid, names):
    r = api.call("POST", f"/projects/{pid}/tags/resolve", json={"tags": names})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"tags/resolve: {r.status_code} {r.text[:300]}")
    j = r.json()
    items = j.get("tags", j) if isinstance(j, dict) else j
    out = {}
    for name, t in zip(names, items):
        out[name] = t["id"] if isinstance(t, dict) else t
    return out


def _location_and_camera(api, pid, cfg):
    lc = cfg.get("benchmark_location", {"name": "benchmark", "lat": -17.27, "lng": 145.48})
    locs = {l["name"]: l for l in api.get(f"/projects/{pid}/locations")}
    loc = locs.get(lc["name"])
    if not loc:
        r = api.call("POST", f"/projects/{pid}/locations", json={"name": lc["name"], "lat": lc["lat"], "lng": lc["lng"]})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create location: {r.status_code} {r.text[:300]}")
        loc = r.json()
    cams = {c.get("label"): c for c in api.get(f"/projects/{pid}/cameras")}
    cam = cams.get("benchmark")
    if not cam:
        r = api.call("POST", f"/projects/{pid}/cameras", json={"label": "benchmark"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create camera: {r.status_code} {r.text[:300]}")
        cam = r.json()
    return loc["id"], cam["id"]


def _prepare_run(cfg, run, classes, tag_of, state):
    """Check the project, create location/camera/tags and one deployment per class."""
    api = Api(run["env"])
    pid = run.get("project_id")
    if not pid:
        raise SystemExit(f"{run['id']}: project_id is empty; create the project in the WIMP UI first")
    name = api.get(f"/projects/{pid}").get("name", "")
    if name.strip() != run["project_name"].strip():
        raise SystemExit(f"{run['id']}: project {pid} is '{name}', config says '{run['project_name']}'")
    rs = state.setdefault(run["id"], {"deployments": {}})
    if all(rs["deployments"].get(c, {}).get("id") for c in classes):
        return api
    loc_id, cam_id = _location_and_camera(api, pid, cfg)
    tag_ids = _resolve_tags(api, pid, [tag_of[c] for c in classes])
    for c in classes:
        d = rs["deployments"].setdefault(c, {"uploaded": []})
        if d.get("id"):
            continue
        body = {"location": loc_id, "camera": cam_id, "startDate": DEPLOY_START, "endDate": DEPLOY_END,
                "utcOffset": "+10:00", "tags": [tag_ids[tag_of[c]]], "automaticAi": True,
                "notes": f"benchmark {cfg['test_set']} class={c}"}
        r = api.call("POST", f"/projects/{pid}/deployments", json=body)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"{run['id']} create deployment {c}: {r.status_code} {r.text[:300]}")
        d["id"] = r.json()["id"]
    return api


def _send(api, pid, did, paths):
    handles = [open(p, "rb") for p in paths]
    try:
        body = [("file", (Path(p).name, h, "image/jpeg")) for p, h in zip(paths, handles)]
        r = api.call("POST", f"/projects/{pid}/deployments/{did}/upload", files=body, timeout=900, tries=3)
    finally:
        for h in handles:
            h.close()
    return r.status_code == 200, ("" if r.status_code == 200 else f"{r.status_code} {r.text[:200]}")


def transfer(cfg, manifest, root, runs, max_seconds=None):
    root = Path(root)
    t_end = time.time() + max_seconds if max_seconds else None
    state_path = root / "state" / cfg["test_set"] / "upload_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    def save():
        with _lock:
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(state_path)

    classes = list(dict.fromkeys(manifest["class"]))
    tag_of = {c: manifest.loc[manifest["class"] == c, "tag"].iloc[0] for c in classes}
    apis = {r["id"]: _prepare_run(cfg, r, classes, tag_of, state) for r in runs}
    save()
    src_api = {}
    uploaded = {(r["id"], c): set(state[r["id"]]["deployments"][c]["uploaded"]) for r in runs for c in classes}
    errors = []

    def do_batch(cls, rows):
        if t_end and time.time() > t_end:
            return
        need = {r["id"]: [x for x in rows if x.local_file not in uploaded[(r["id"], cls)]] for r in runs}
        todo = {x.local_file: x for v in need.values() for x in v}
        if not todo:
            return
        fetched = []
        for lf, x in todo.items():
            p = root / lf
            if not (p.exists() and p.stat().st_size > 0):
                api = src_api.setdefault(x.source_env, Api(x.source_env))
                resp = api.call("GET", x.source_url, timeout=300)
                if resp.status_code != 200:
                    errors.append((lf, f"download {resp.status_code}"))
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(resp.content)
                fetched.append(p)
        for r in runs:
            files = [x.local_file for x in need[r["id"]] if (root / x.local_file).exists()]
            if not files:
                continue
            did = state[r["id"]]["deployments"][cls]["id"]
            ok, msg = _send(apis[r["id"]], r["project_id"], did, [str(root / f) for f in files])
            if ok:
                with _lock:
                    uploaded[(r["id"], cls)].update(files)
                    state[r["id"]]["deployments"][cls]["uploaded"] = sorted(uploaded[(r["id"], cls)])
            else:
                errors.append((f"{r['id']}/{cls}", msg))
        if not cfg.get("keep_local_images", False):
            for p in fetched:
                p.unlink(missing_ok=True)
        save()

    for cls in classes:
        rows = list(manifest[manifest["class"] == cls].itertuples(index=False))
        batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(lambda b: do_batch(cls, b), batches))
        expected = {x.local_file for x in rows}
        for r in runs:
            d = state[r["id"]]["deployments"][cls]
            got = uploaded[(r["id"], cls)] & expected
            if len(got) == len(expected) and not d.get("finalized"):
                api = apis[r["id"]]
                api.call("PATCH", f"/projects/{r['project_id']}/deployments/{d['id']}", json={"automaticAi": True})
                resp = api.call("POST", f"/projects/{r['project_id']}/deployments/{d['id']}/finalizeUpload")
                if resp.status_code in (200, 201, 204):
                    d["finalized"] = True
                else:
                    errors.append((f"{r['id']}/{cls}", f"finalize {resp.status_code} {resp.text[:200]}"))
                save()
        line = "  ".join(f"{r['id']}:{len(uploaded[(r['id'], cls)] & expected)}/{len(expected)}"
                         f"{'F' if state[r['id']]['deployments'][cls].get('finalized') else ''}" for r in runs)
        print(f"{cls:28s} {line}", flush=True)
        if t_end and time.time() > t_end:
            break

    for e in errors[:10]:
        print("  ERROR", e)
    done = all(state[r["id"]]["deployments"][c].get("finalized") for r in runs for c in classes)
    return done


def status_run(run):
    api = Api(run["env"])
    pid = run["project_id"]
    rows = []
    for d in api.get(f"/projects/{pid}/deployments"):
        st = api.get(f"/projects/{pid}/deployments/{d['id']}/status")
        rows.append({"run": run["id"], "class": (d.get("notes") or "").split("class=")[-1],
                     "status": st.get("status"), "ai": st.get("aiModelState"),
                     "images": st.get("nrAssets"), "sequences": st.get("nrSequences"),
                     "pct_ai": st.get("percentInspectedWithAi")})
    return rows
