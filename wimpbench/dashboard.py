"""Comparison dashboard across all runs of a test set (results/<set>/dashboard.html).

Self-contained HTML (no scripts, no external assets) so it opens anywhere and can
be published as is. Run columns are ordered as in the config.
"""
import html

import pandas as pd


def _label(name):
    """'WildObs_QLD WetTropics | MD 0.25 (TEST)' -> 'Wet Tropics, MD 0.25 (TEST)'."""
    return (name.replace("WildObs_QLD WetTropics", "Wet Tropics")
                .replace("Megadetector V6", "MegaDetector V6 only").replace(" | ", ", "))


def _run_label(run):
    from .export import run_label
    clf = "MegaDetector V6 only" if "Megadetector" in run.get("classifier", "") else run.get("classifier", "")
    return f"{clf}, {run_label(run)}"


def _cell(v, fmt="{:.2f}", good=None):
    if pd.isna(v):
        return '<td class="na">-</td>'
    style = ""
    if good is not None:  # shade 0..1 from red to green
        x = max(0.0, min(1.0, float(v)))
        style = f' style="background:hsl({int(120 * x)},55%,{92 - 12 * x:.0f}%)"'
    return f"<td{style}>{fmt.format(v)}</td>"


def _pivot_html(df, index, columns, value, order, shade=True, index_name=""):
    p = df.pivot_table(index=index, columns=columns, values=value, aggfunc="first")
    p = p[[c for c in order if c in p.columns]]
    head = "".join(f"<th>{html.escape(c)}</th>" for c in p.columns)
    body = "".join(
        f"<tr><th class='row'>{html.escape(str(i))}</th>" + "".join(_cell(v, good=shade) for v in row) + "</tr>"
        for i, row in p.iterrows())
    return f"<table><tr><th>{html.escape(index_name)}</th>{head}</tr>{body}</table>"


def build_dashboard(cfg, res, colin, det):
    order = [_run_label(r) for r in cfg["runs"]]
    by_id = {r["id"]: _run_label(r) for r in cfg["runs"]}

    species_rows, full_rows = [], []
    for r in colin.runs:
        lab = _label(r.model_name)
        b = r.metrics.best_thresholds.copy()
        b.insert(0, "run", lab)
        species_rows.append(b)
        t = r.metrics.results.copy()
        t.insert(0, "run", lab)
        full_rows.append(t)
    species = pd.concat(species_rows) if species_rows else pd.DataFrame()
    full = pd.concat(full_rows) if full_rows else pd.DataFrame()
    species.to_csv(res / "species_metrics_best_threshold.csv", index=False)
    full.to_csv(res / "species_metrics.csv", index=False)
    # Colin's run labels and ours must line up
    order_species = [_label(r.model_name) for r in colin.runs]
    order_species = [o for o in order if o in order_species] + [o for o in order_species if o not in order]

    det = det.copy()
    if len(det):
        det["run_label"] = det["run"].map(by_id)
    uncl = det.groupby("run_label")["unclassified_share"].first() if len(det) else pd.Series(dtype=float)

    sections = []
    if len(det):
        sections.append("<h2>1. Detector: is there an animal, a person, a vehicle, or nothing?</h2>"
                        "<p>True and predicted labels collapsed to four classes. Recall = share of images of that class "
                        "given that class; precision = share of images given that class that really are it.</p>"
                        "<h3>Recall</h3>" + _pivot_html(det, "class", "run_label", "recall", order, index_name="class") +
                        "<h3>Precision</h3>" + _pivot_html(det, "class", "run_label", "precision", order, index_name="class") +
                        "<h3>Images left with no AI result (Unclassified)</h3><table><tr>" +
                        "".join(f"<th>{html.escape(o)}</th>" for o in order if o in uncl.index) + "</tr><tr>" +
                        "".join(_cell(uncl[o], "{:.1%}") for o in order if o in uncl.index) + "</tr></table>")
    if len(species):
        sp = species.rename(columns={"species": "class"})
        sections.append("<h2>2. Species classifier: F1 at each run's best confidence threshold</h2>"
                        "<p>From Colin Broughton's evaluation. F1 combines recall and precision (1 = perfect). "
                        "Rows marked * have no matching label in the Wet Tropics model.</p>" +
                        _pivot_html(sp.assign(**{"class": sp["class"].where(~sp["class"].isin(_not_in_model(cfg)),
                                                                            sp["class"] + " *")}),
                                    "class", "run", "f1_score", order_species, index_name="class") +
                        "<h3>Recall</h3>" + _pivot_html(sp, "class", "run", "recall", order_species, index_name="class") +
                        "<h3>Precision</h3>" + _pivot_html(sp, "class", "run", "precision", order_species, index_name="class"))
    reports = "".join(
        f'<li><a href="colin_reports/{cfg["test_set"]}/{html.escape(r.report_path.name)}">{html.escape(_label(r.model_name))}</a></li>'
        for r in colin.runs)
    if colin.comparison_report_path:
        reports += f'<li><a href="colin_reports/{cfg["test_set"]}/{html.escape(colin.comparison_report_path.name)}">Comparison report (all runs)</a></li>'

    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WIMP model benchmark: {html.escape(cfg['test_set'])}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#1f2328;line-height:1.45}}
h1{{font-size:1.6rem}} h2{{margin-top:2.2rem;border-bottom:1px solid #d0d7de;padding-bottom:.3rem}}
table{{border-collapse:collapse;font-size:13px;margin:.6rem 0 1.2rem;font-variant-numeric:tabular-nums}}
th,td{{padding:4px 8px;border:1px solid #e4e7eb;text-align:center}} th{{background:#f6f8fa;font-weight:600}}
th.row{{text-align:left;font-weight:500}} td.na{{color:#999}} .meta{{color:#57606a;font-size:14px}}
</style></head><body>
<h1>WIMP model benchmark: {html.escape(cfg['test_set'])}</h1>
<p>{html.escape(cfg.get('description', '').strip())}</p>
<p class="meta">{len(cfg['runs'])} model runs on the same human-validated images. Method: Colin Broughton's
WildObs benchmark workflow, automated in github.com/EcologicalCascadesLab/wimp-model-benchmark.
See <code>results/{html.escape(cfg['test_set'])}/README.md</code> for findings and caveats.</p>
{''.join(sections)}
<h2>3. Full reports</h2><ul>{reports}</ul>
</body></html>"""
    (res / "dashboard.html").write_text(page, encoding="utf-8")


def _not_in_model(cfg):
    from .utils_names import display_names
    return display_names([c for c, s in cfg["sampling"]["classes"].items() if s.get("in_model") is False])
