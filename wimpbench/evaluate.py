"""Run Colin's evaluation over all runs of a test set, add detector metrics, build the dashboard.

Colin's code is called as a library from vendor/ (unchanged). Outputs:
    results/<test_set>/colin_reports/...      his HTML reports + comparison report
    results/<test_set>/detector_metrics.csv   animal/human/vehicle/blank per run
    results/<test_set>/detector_confusion_<run>.csv
    results/<test_set>/species_metrics.csv    per-class recall/precision/F1 per run and threshold
    results/<test_set>/dashboard.html
"""
import sys
from pathlib import Path

import pandas as pd

from . import detector_metrics as dm
from .dashboard import build_dashboard

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "model-benchmark-testing-workflow"


def _colin():
    sys.path.insert(0, str(VENDOR))
    from src.config import BenchmarkConfig  # noqa: E402
    from src.pipeline import run_benchmark  # noqa: E402
    return BenchmarkConfig, run_benchmark


def evaluate(cfg, root):
    root = Path(root).resolve()
    ts = cfg["test_set"]
    res = root / "results" / ts
    res.mkdir(parents=True, exist_ok=True)
    ev = cfg.get("evaluation", {})

    # 1. Colin's reports (one per run + comparison)
    BenchmarkConfig, run_benchmark = _colin()
    bc = BenchmarkConfig(
        test_set_name=ts,
        data_source_location=cfg.get("data_source_location", ""),
        data_collation_process=cfg.get("data_collation_process", ""),
        thresholds=ev.get("thresholds", [0.5, 0.6, 0.7, 0.8, 0.9]),
        observation_level=ev.get("observation_level", "event"),
        template=ev.get("template", "full"),
        export_errors=True,
        clear_existing_outputs=True,
        input_path=root / "Input_Data",
        output_path=res / "colin_reports",
        templates_path=VENDOR / "templates",
        log_path=root / "logs",
    )
    colin = run_benchmark(bc)

    # 2. Detector-level metrics per run
    det_rows = []
    for run in cfg["runs"]:
        folder = root / "Input_Data" / ts / run["id"]
        if not folder.exists():
            continue
        per_image = dm.load(folder, ev.get("observation_level", "event"))
        summary, cm = dm.metrics(per_image)
        cm.to_csv(res / f"detector_confusion_{run['id']}.csv")
        summary.insert(0, "run", run["id"])
        summary["env"] = run["env"]
        summary["detector_threshold"] = run["detector_threshold"]
        summary["unclassified_share"] = summary.attrs["unclassified_share"]
        det_rows.append(summary)
    det = pd.concat(det_rows) if det_rows else pd.DataFrame()
    det.to_csv(res / "detector_metrics.csv", index=False)

    build_dashboard(cfg, res, colin, det)
    return colin, det
