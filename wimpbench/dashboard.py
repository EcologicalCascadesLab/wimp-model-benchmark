"""Comparison dashboard across all runs of a test set (results/<set>/dashboard.html).

Tables now; charts are added once real results exist (see docs/07_dashboard.Rmd).
"""
import html

import pandas as pd


def _species_table(colin):
    rows = []
    for r in colin.runs:
        best = r.metrics.best_thresholds.copy()
        best.insert(0, "run", r.model_name)
        rows.append(best)
    return pd.concat(rows) if rows else pd.DataFrame()


def build_dashboard(cfg, res, colin, det):
    species = _species_table(colin)
    species.to_csv(res / "species_metrics_best_threshold.csv", index=False)
    full = []
    for r in colin.runs:
        t = r.metrics.results.copy()
        t.insert(0, "run", r.model_name)
        full.append(t)
    if full:
        pd.concat(full).to_csv(res / "species_metrics.csv", index=False)

    def table(df):
        return df.to_html(index=False, float_format=lambda x: f"{x:.2f}", na_rep="", border=0, classes="t")

    reports = "".join(
        f'<li><a href="colin_reports/{cfg["test_set"]}/{r.report_path.name}">{html.escape(r.model_name)}</a></li>'
        for r in colin.runs)
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>WIMP model benchmark: {html.escape(cfg['test_set'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}}
table.t{{border-collapse:collapse;font-size:14px;margin:1rem 0}}table.t td,table.t th{{padding:4px 10px;border-bottom:1px solid #ddd;text-align:right}}
table.t td:first-child,table.t th:first-child,table.t td:nth-child(2){{text-align:left}}</style></head><body>
<h1>WIMP model benchmark: {html.escape(cfg['test_set'])}</h1>
<p>{html.escape(cfg.get('description', ''))}</p>
<h2>Detector (MegaDetector) performance: animal / human / vehicle / blank</h2>
{table(det) if len(det) else '<p>No runs yet.</p>'}
<h2>Species classifier: best-F1 threshold per class</h2>
{table(species) if len(species) else '<p>No runs yet.</p>'}
<h2>Full reports (Colin Broughton's evaluation workflow)</h2><ul>{reports}</ul>
</body></html>"""
    (res / "dashboard.html").write_text(page, encoding="utf-8")
