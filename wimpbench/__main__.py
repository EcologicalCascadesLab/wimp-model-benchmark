"""python -m wimpbench <step> --config config/<set>.yaml

Steps: check, select, fetch, upload, status, export, evaluate
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_cfg(path):
    return yaml.safe_load(Path(path).read_text())


def runs_selected(cfg, only):
    runs = cfg["runs"]
    if only:
        keep = set(only.split(","))
        runs = [r for r in runs if r["id"] in keep]
    return runs


def main(argv=None):
    p = argparse.ArgumentParser(prog="wimpbench")
    p.add_argument("step", choices=["check", "select", "fetch", "upload", "status", "export", "evaluate"])
    p.add_argument("--config", required=True)
    p.add_argument("--only", help="comma-separated run ids")
    a = p.parse_args(argv)
    cfg = load_cfg(a.config)
    res = ROOT / "results" / cfg["test_set"]

    if a.step == "check":
        from .api import Api
        for env in ("prod", "test"):
            try:
                api = Api(env)
                me = api.get("/me")
                print(f"{env}: signed in as {me.get('name') or me.get('email')}; {len(api.projects())} projects")
            except SystemExit as e:
                print(f"{env}: {e}")
        for r in cfg["runs"]:
            if not r.get("project_id"):
                print(f"  {r['id']}: no project_id yet (create in WIMP UI)")
                continue
            from .api import Api
            name = Api(r["env"]).get(f"/projects/{r['project_id']}").get("name")
            flag = "ok" if name.strip() == r["project_name"].strip() else "NAME MISMATCH"
            print(f"  {r['id']}: {name} [{flag}]")

    elif a.step == "select":
        from .select_images import select
        select(cfg, ROOT, a.config)

    elif a.step == "fetch":
        from .select_images import fetch
        fetch(cfg, ROOT)

    elif a.step == "upload":
        from .upload import upload_run
        manifest = pd.read_csv(res / "manifest.csv", dtype=str)
        manifest = manifest[manifest["local_file"].notna()]
        for r in runs_selected(cfg, a.only):
            print(f"== {r['id']}")
            upload_run(cfg, r, manifest, ROOT)

    elif a.step == "status":
        from .upload import status_run
        rows = []
        for r in runs_selected(cfg, a.only):
            if r.get("project_id"):
                rows += status_run(r)
        df = pd.DataFrame(rows)
        print(df.to_string(index=False) if len(df) else "no runs with project_id")

    elif a.step == "export":
        from .export import export_run
        for r in runs_selected(cfg, a.only):
            print(f"== {r['id']} -> {export_run(cfg, r, ROOT)}")

    elif a.step == "evaluate":
        from .evaluate import evaluate
        evaluate(cfg, ROOT)
        print(f"results in {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
