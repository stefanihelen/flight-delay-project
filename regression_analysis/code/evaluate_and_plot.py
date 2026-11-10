#!/usr/bin/env python
"""Evaluate actual held-out predictions and render three traceable figures.

No model is fitted here. All comparisons use identical, complete prediction rows.
The bootstrap resamples actual daily sums; it never generates artificial flights.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


SEED = 20261107
COLORS = {"baseline": "#687780", "weather": "#246E9F"}
LABELS = {"baseline": "Controls only", "weather": "Controls + weather"}
CONTRASTS = {
    "wind_5_10": "Wind 5 to <10 kt",
    "wind_10_20": "Wind 10 to <20 kt",
    "wind_20_plus": "Wind ≥20 kt",
    "visibility_5_10km": "Visibility 5 to <10 km",
    "visibility_1_5km": "Visibility 1 to <5 km",
    "visibility_under_1km": "Visibility <1 km",
    "rain_vs_dry": "Precipitation versus none",
    "temperature_5_to_15": "Temperature 5 to 15 °C",
    "temperature_15_to_25": "Temperature 15 to 25 °C",
}


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def loss_arrays(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # Clipping is restricted to log scoring, at machine epsilon.
    q = np.clip(p, np.finfo(float).eps, 1 - np.finfo(float).eps)
    return (p - y) ** 2, -(y * np.log(q) + (1 - y) * np.log1p(-q))


def threshold_table(y: np.ndarray, p: np.ndarray, model: str) -> pd.DataFrame:
    order = np.argsort(p, kind="stable")
    ordered_p = p[order]
    positive_cumulative = np.concatenate(([0], np.cumsum(y[order], dtype=np.int64)))
    total_pos = int(y.sum())
    rows = []
    for threshold in np.round(np.arange(0.05, 0.601, 0.01), 2):
        left = int(np.searchsorted(ordered_p, threshold, side="left"))
        tp = total_pos - int(positive_cumulative[left])
        fp = len(y) - left - tp
        fn = total_pos - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / total_pos if total_pos else 0.0
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
        rows.append(dict(model=model, split="validation", threshold=float(threshold),
                         precision=precision, recall=recall, f1=f1, n=len(y)))
    result = pd.DataFrame(rows)
    # A tie is resolved to the lower threshold, declared before test evaluation.
    chosen = int(result["f1"].to_numpy().argmax())
    result["selected"] = False
    result.loc[chosen, "selected"] = True
    return result


def score(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    predicted = p >= threshold
    positive = y == 1
    tp = int((predicted & positive).sum())
    fp = int((predicted & ~positive).sum())
    fn = int((~predicted & positive).sum())
    tn = int((~predicted & ~positive).sum())
    brier, logloss = loss_arrays(y, p)
    return {
        "n": len(y), "prevalence": float(y.mean()), "threshold": threshold,
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
        "brier": float(brier.mean()), "logloss": float(logloss.mean()),
        "accuracy": (tp + tn) / len(y),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
    }


def daily_bootstrap(test: pd.DataFrame, repetitions: int, block_length: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    daily_rows = []
    for date, group in test.groupby("date_id", sort=True):
        y = group["y"].to_numpy(dtype=np.int8)
        row = {"date_id": int(date), "n": len(group)}
        for model in LABELS:
            brier, logloss = loss_arrays(y, group[f"p_{model}"].to_numpy())
            row[f"{model}_brier_sum"] = float(brier.sum())
            row[f"{model}_logloss_sum"] = float(logloss.sum())
        daily_rows.append(row)
    daily = pd.DataFrame(daily_rows).set_index("date_id")
    # Explicit calendar-day slots, including any day with no covered flights.
    day_ids = np.arange(int(daily.index.min()), int(daily.index.max()) + 1)
    daily = daily.reindex(day_ids, fill_value=0).rename_axis("date_id").reset_index()
    n_days = len(daily)
    if n_days < block_length:
        raise ValueError("Too few test days for the specified moving-block bootstrap")
    values = daily.drop(columns="date_id").to_numpy(dtype=float)
    rng = np.random.default_rng(SEED)
    totals = np.empty((repetitions, values.shape[1]))
    offsets = np.arange(block_length)
    for b in range(repetitions):
        starts = rng.integers(0, n_days - block_length + 1, size=math.ceil(n_days / block_length))
        indices = (starts[:, None] + offsets).ravel()[:n_days]
        totals[b] = values[indices].sum(axis=0)
    if (totals[:, 0] <= 0).any():
        raise ValueError("A bootstrap replicate has no covered flights")
    names = list(daily.drop(columns="date_id").columns)
    interval_rows, difference_rows = [], []
    for metric in ("brier", "logloss"):
        bootstrap_scores = {}
        points = {}
        for model in LABELS:
            column = names.index(f"{model}_{metric}_sum")
            bootstrap_scores[model] = totals[:, column] / totals[:, 0]
            points[model] = float(values[:, column].sum() / values[:, 0].sum())
            low, high = np.quantile(bootstrap_scores[model], [0.025, 0.975])
            interval_rows.append(dict(split="test", model=model, metric=metric, estimate=points[model],
                                      lower=float(low), upper=float(high), repetitions=repetitions))
        differences = bootstrap_scores["weather"] - bootstrap_scores["baseline"]
        low, high = np.quantile(differences, [0.025, 0.975])
        difference_rows.append(dict(split="test", comparison="weather_minus_baseline", metric=metric,
                                    estimate=points["weather"] - points["baseline"],
                                    lower=float(low), upper=float(high), repetitions=repetitions))
    settings = {
        "method": "Non-circular moving calendar-day block bootstrap of daily sums and counts",
        "block_length_days": block_length, "repetitions": repetitions, "seed": SEED,
        "test_calendar_days": n_days, "observed_test_days": int((daily["n"] > 0).sum()),
        "interval": "95% percentile interval", "refit_models": False,
        "paired": True,
        "scope": "Conditional held-out loss uncertainty for fixed fitted models and thresholds; excludes training/model-selection uncertainty.",
        "limitations": "Approximately 61 test days provide limited independent time blocks; no claim of future-year uncertainty.",
        "auc_ap_intervals": "Not estimated; ROC AUC and AP are point estimates only.",
    }
    return pd.DataFrame(interval_rows), pd.DataFrame(difference_rows), {"settings": settings, "daily": daily}


def calibration_rows(test: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    rows = []
    for model in LABELS:
        p = test[f"p_{model}"].to_numpy()
        # Quantile boundaries are descriptive only; no refitting or calibration.
        edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
        if len(edges) == 1:
            bins = np.zeros(len(p), dtype=int)
        else:
            bins = np.searchsorted(edges[1:-1], p, side="right")
        for bin_id in np.unique(bins):
            selected = bins == bin_id
            rows.append(dict(split="test", model=model, bin=int(bin_id + 1), n=int(selected.sum()),
                             mean_prediction=float(p[selected].mean()),
                             observed_rate=float(test.loc[selected, "y"].mean()),
                             prediction_min=float(p[selected].min()), prediction_max=float(p[selected].max()),
                             binning="Up to 10 model-specific quantile bins; duplicate boundaries merged"))
    return pd.DataFrame(rows)


def style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
        "font.size": 10, "axes.labelsize": 11, "axes.labelweight": "semibold",
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlepad": 12,
        "xtick.labelsize": 10, "ytick.labelsize": 10, "axes.linewidth": 1.0,
        "xtick.major.width": 1.0, "ytick.major.width": 1.0,
        "legend.fontsize": 9, "legend.frameon": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    })


def save_figure(fig, path: Path, caption: str, caption_y: float = 0.025) -> None:
    fig.text(0.025, caption_y, caption, ha="left", va="bottom", fontsize=8.1, linespacing=1.4)
    fig.canvas.draw()
    for ax in fig.axes:
        for text in ax.get_xticklabels() + ax.get_yticklabels():
            text.set_fontweight("medium")
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.08)
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def figures(out: Path, test: pd.DataFrame, metrics: pd.DataFrame, calibration: pd.DataFrame,
            contrasts: pd.DataFrame, forest_model: str) -> list[Path]:
    folder = out / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    style()
    n_test = len(test)
    forest = contrasts.loc[contrasts["model"] == forest_model].copy().set_index("contrast")
    missing = set(CONTRASTS) - set(forest.index)
    if missing:
        raise ValueError(f"Missing main-model weather contrasts: {sorted(missing)}")
    forest = forest.loc[list(CONTRASTS)]
    if not np.isfinite(forest[["odds_ratio", "lower", "upper"]].to_numpy()).all():
        raise ValueError("Non-finite forest estimates")
    if (forest[["odds_ratio", "lower", "upper"]] <= 0).any().any():
        raise ValueError("Odds ratios and confidence limits must be positive for a log axis")
    if ((forest["lower"] > forest["odds_ratio"]) | (forest["upper"] < forest["odds_ratio"])).any():
        raise ValueError("Invalid confidence interval ordering")
    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    fig.subplots_adjust(left=0.37, right=0.96, top=0.88, bottom=0.24)
    positions = np.arange(len(forest))[::-1]
    ax.axvline(1, color="#808080", linestyle="--", linewidth=1.0, zorder=1)
    ax.errorbar(forest["odds_ratio"], positions,
                xerr=np.vstack([forest["odds_ratio"] - forest["lower"], forest["upper"] - forest["odds_ratio"]]),
                fmt="o", color=COLORS["weather"], markersize=5.5, elinewidth=1.5, capsize=3, zorder=3)
    ax.set_yticks(positions, [CONTRASTS[c] for c in forest.index])
    ax.set_ylim(-0.6, len(forest) - 0.4)
    ax.set_xscale("log")
    low = min(0.9, float(forest["lower"].min()) * 0.85)
    high = max(1.1, float(forest["upper"].max()) * 1.15)
    ax.set_xlim(low, high)
    candidates = np.array([0.125, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12, 16])
    ticks = candidates[(candidates >= low) & (candidates <= high)]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.minorticks_off()
    ax.set_xlabel("Adjusted odds ratio (log scale)")
    fig.suptitle("Which weather conditions are linked to delay?", y=0.97, fontsize=12, fontweight="semibold")
    caption = (f"BTS + NOAA, Jan–Dec 2024; n = {int(forest['n'].iloc[0]):,} valid-arrival flights.\n"
               "95% CIs: two-way cluster-robust, by origin airport and date; no multiplicity adjustment.\n"
               "References: wind <5 kt; visibility ≥10 km; precipitation = 1-h total >0 versus 0 mm.")
    save_figure(fig, folder / "01_weather_associations", caption)

    y = test["y"].to_numpy()
    fig, ax = plt.subplots(figsize=(5.5, 5.1))
    fig.subplots_adjust(left=0.14, right=0.97, top=0.87, bottom=0.25)
    ax.plot([0, 1], [0, 1], color="#B7B7B7", linestyle=":", linewidth=1.0)
    for model in LABELS:
        fpr, tpr, _ = roc_curve(y, test[f"p_{model}"].to_numpy(), drop_intermediate=True)
        auc = float(metrics.loc[(metrics["split"] == "test") & (metrics["model"] == model), "roc_auc"].iloc[0])
        ax.plot(fpr, tpr, color=COLORS[model], linewidth=1.6,
                linestyle="--" if model == "baseline" else "-", label=f"{LABELS[model]}  AUC {auc:.3f}")
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="False-positive rate", ylabel="True-positive rate")
    ax.legend(loc="lower right", borderaxespad=0.5, handlelength=2.0)
    fig.suptitle("Does weather improve delay discrimination?", y=0.97, fontsize=12, fontweight="semibold")
    caption = (f"BTS + NOAA, Nov–Dec 2024; n = {n_test:,} common predictable flights.\n"
               "Trained Jan–Aug; thresholds selected Sep–Oct. ROC uses all test scores.\n"
               "AUC is a point estimate; no AUC confidence interval is claimed.")
    save_figure(fig, folder / "02_temporal_test_roc", caption)

    fig, ax = plt.subplots(figsize=(5.5, 5.1))
    fig.subplots_adjust(left=0.14, right=0.97, top=0.87, bottom=0.25)
    upper = min(1.0, max(0.5, float(calibration[["mean_prediction", "observed_rate"]].to_numpy().max()) * 1.12))
    ax.plot([0, upper], [0, upper], color="#B7B7B7", linestyle=":", linewidth=1.0)
    for model in LABELS:
        part = calibration.loc[calibration["model"] == model]
        ax.plot(part["mean_prediction"], part["observed_rate"], marker="s" if model == "baseline" else "o",
                color=COLORS[model], linewidth=1.5, markersize=4.5,
                linestyle="--" if model == "baseline" else "-", label=LABELS[model])
    ax.set(xlim=(0, upper), ylim=(0, upper), xlabel="Mean predicted delay probability", ylabel="Observed delay proportion")
    ax.legend(loc="upper left", borderaxespad=0.6)
    fig.suptitle("Do predicted delay probabilities match outcomes?", y=0.97, fontsize=11.5, fontweight="semibold")
    caption = (f"BTS + NOAA, Nov–Dec 2024; n = {n_test:,} common predictable flights.\n"
               "Up to 10 model-specific quantile bins; descriptive points, without CIs.\n"
               "Diagonal = perfect calibration; predictions were not recalibrated on the test set.")
    save_figure(fig, folder / "03_temporal_test_calibration", caption)
    return [folder / f"{name}.pdf" for name in
            ("01_weather_associations", "02_temporal_test_roc", "03_temporal_test_calibration")]


def audit_source(script: Path, scripts: Path, qa: Path) -> dict:
    result = subprocess.run([sys.executable, str(scripts / "validate_figure.py"), str(script), "--json"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    (qa / "source_preflight.json").write_text(result.stdout, encoding="utf-8")
    (qa / "source_preflight.stderr.txt").write_text(result.stderr, encoding="utf-8")
    write_json(qa / "source_preflight_reviews.json", {
        "EXPORT-RASTER": "The requested bundle is PNG, PDF and SVG for a course report; TIFF was not requested.",
        "RASTER-DPI": "300 dpi is the requested raster preview resolution; PDF and SVG are vector exports.",
        "DATA-EXCLUSION": "dropna is only used to inspect probability validity. All actual exclusions are counted before and after, by split and model, in coverage.csv.",
        "DEMO-DATA": "The random generator resamples observed daily sums for uncertainty estimation. No simulated flight data or fabricated model result is used.",
    })
    if result.returncode != 0:
        raise RuntimeError(f"Figure source preflight failed; inspect {qa / 'source_preflight.json'}")
    return {"source_preflight_exit_code": result.returncode}


def audit_pdfs(pdfs: list[Path], scripts: Path, qa: Path) -> list[dict]:
    rows = []
    for pdf in pdfs:
        name = pdf.stem
        write_json(qa / f"{name}.alignment.json", {"status": "NOT APPLICABLE", "reason": "One plot area; single-panel figure"})
        jobs = [
            ("glyph", [sys.executable, str(scripts / "audit_pdf_text.py"), str(pdf), "--min-pt", "5", "--json"]),
            ("collision", [sys.executable, str(scripts / "audit_figure_collisions.py"), str(pdf),
                           "--json-out", str(qa / f"{name}.collision.json"),
                           "--overlay-pdf", str(qa / f"{name}.collision-overlay.pdf")]),
        ]
        for kind, command in jobs:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            (qa / f"{name}.{kind}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (qa / f"{name}.{kind}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            rows.append(dict(figure=pdf.name, check=kind, exit_code=result.returncode))
    write_json(qa / "automatic_audit_summary.json", {"checks": rows, "visual_review": "Pending; inspect final PNGs before delivery"})
    if any(row["exit_code"] != 0 for row in rows):
        raise RuntimeError(f"A rendered figure audit requires correction; inspect {qa}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = Path(__file__).resolve().parents[1]
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--work", type=Path, default=default_out.parents[1] / "work")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--forest-model", default="main")
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    parser.add_argument("--block-length", type=int, default=7)
    parser.add_argument("--qa-scripts", type=Path, default=Path.home() / ".codex" / "skills" / "nature-figure" / "scripts")
    parser.add_argument("--skip-qa", action="store_true", help="Only for reproducing outside the original environment; QA remains required before delivery")
    args = parser.parse_args()
    if args.bootstrap_repetitions < 100 or args.block_length < 1:
        raise ValueError("Need at least 100 bootstrap repetitions and a positive block length")
    out, work = args.out.resolve(), args.work.resolve()
    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    qa = work / "figure_qa"
    qa.mkdir(parents=True, exist_ok=True)
    predictions = args.predictions or work / "holdout_predictions.csv"
    d = pd.read_csv(predictions, usecols=["date_id", "month", "y", "p_baseline", "p_weather"])
    if not d["y"].isin([0, 1]).all() or not d["month"].isin([9, 10, 11, 12]).all():
        raise ValueError("Unexpected holdout outcome or month")
    if d["date_id"].isna().any():
        raise ValueError("Missing holdout dates")
    for model in LABELS:
        present = d[f"p_{model}"].dropna()
        if not np.isfinite(present.to_numpy()).all() or not present.between(0, 1).all():
            raise ValueError(f"Invalid non-missing probabilities in {model}")
    d["split"] = np.where(d["month"] <= 10, "validation", "test")
    common = d[["p_baseline", "p_weather"]].notna().all(axis=1)
    coverage, metrics_rows, selected_tables = [], [], []
    kept = d.loc[common].copy()
    val = kept.loc[kept["split"] == "validation"]
    test = kept.loc[kept["split"] == "test"].copy()
    if not len(val) or not len(test) or val["y"].nunique() != 2 or test["y"].nunique() != 2:
        raise ValueError("Each holdout split needs covered flights of both outcome classes")
    thresholds = {}
    for model in LABELS:
        selected = threshold_table(val["y"].to_numpy(dtype=np.int8), val[f"p_{model}"].to_numpy(), model)
        thresholds[model] = float(selected.loc[selected["selected"], "threshold"].iloc[0])
        selected_tables.append(selected)
    for split, group in d.groupby("split", sort=False):
        part = kept.loc[kept["split"] == split]
        for model in LABELS:
            covered_model = int(group[f"p_{model}"].notna().sum())
            coverage.append(dict(split=split, model=model, total_rows=len(group),
                                 model_prediction_rows=covered_model, missing_prediction_rows=len(group) - covered_model,
                                 common_prediction_rows=len(part), excluded_common_rows=len(group) - len(part),
                                 common_coverage_rate=len(part) / len(group)))
            metrics_rows.append(dict(split=split, model=model, total_rows=len(group), excluded_common_rows=len(group) - len(part),
                                     **score(part["y"].to_numpy(dtype=np.int8), part[f"p_{model}"].to_numpy(), thresholds[model])))
    metrics = pd.DataFrame(metrics_rows)
    intervals, differences, bootstrap = daily_bootstrap(test, args.bootstrap_repetitions, args.block_length)
    for row in intervals.itertuples(index=False):
        selection = (metrics["split"] == row.split) & (metrics["model"] == row.model)
        metrics.loc[selection, f"{row.metric}_lower"] = row.lower
        metrics.loc[selection, f"{row.metric}_upper"] = row.upper
    calibration = calibration_rows(test)
    metrics.to_csv(tables / "prediction_metrics.csv", index=False)
    pd.concat(selected_tables, ignore_index=True).to_csv(tables / "threshold_selection.csv", index=False)
    pd.DataFrame(coverage).to_csv(tables / "coverage.csv", index=False)
    calibration.to_csv(tables / "calibration.csv", index=False)
    intervals.to_csv(tables / "holdout_loss_intervals.csv", index=False)
    differences.to_csv(tables / "paired_metric_differences.csv", index=False)
    bootstrap["daily"].to_csv(tables / "test_daily_loss_totals.csv", index=False)
    diagnostics = json.loads((tables / "model_diagnostics.json").read_text(encoding="utf-8"))
    training_prevalence = float(diagnostics["predict_baseline"]["mean_outcome"])
    if not 0 < training_prevalence < 1:
        raise ValueError("Invalid training prevalence")
    dummy_rows = []
    for split, part in kept.groupby("split"):
        dummy_rows.append(dict(split=split, model="training_prevalence_only", training_prevalence=training_prevalence,
                               **score(part["y"].to_numpy(dtype=np.int8), np.full(len(part), training_prevalence), 0.5)))
    pd.DataFrame(dummy_rows).to_csv(tables / "dummy_baseline_metrics.csv", index=False)
    contract = {
        "backend": "Python Matplotlib exclusively", "archetype": "quantitative grid; three separate single-panel figures",
        "figures": [
            {"name": "01_weather_associations", "question": "Which weather conditions are associated with delay after adjustment?",
             "role": "Adjusted association and cluster-robust uncertainty", "source": "tables/weather_contrasts.csv",
             "size_inches": [7.2, 5.5], "interval": "Two-way origin/date cluster-robust 95% CI; no multiplicity correction"},
            {"name": "02_temporal_test_roc", "question": "Does adding weather improve held-out discrimination?",
             "role": "Temporal prediction comparison on common covered test flights", "source": "holdout predictions",
             "size_inches": [5.5, 5.1], "interval": "None; point estimates only"},
            {"name": "03_temporal_test_calibration", "question": "Are predicted probabilities calibrated on the held-out period?",
             "role": "Descriptive calibration, without refitting", "source": "tables/calibration.csv",
             "size_inches": [5.5, 5.1], "interval": "None; descriptive bin summaries only"},
        ],
        "source_data": "Observed 2024 BTS flights linked to NOAA weather; no synthetic observations",
        "exports": ["PNG 300 dpi", "editable-text PDF", "editable-text SVG"], "minimum_glyph_pt": 5,
        "alignment": "NOT APPLICABLE: each figure has one plot area",
        "cohort_rule": "Inference cohort defined in regression; evaluation excludes any row lacking either prediction and reports exclusions",
        "image_integrity": "Charts computed directly from tabular results; no image editing or manipulation",
    }
    write_json(out / "figure_contract.json", contract)
    evaluation = {
        "split": {"train": "2024-01 through 2024-08", "validation": "2024-09 through 2024-10", "test": "2024-11 through 2024-12"},
        "comparison_population": "Same rows with finite probabilities for both models in each split",
        "threshold_selection": {"objective": "Maximum validation F1", "grid": "0.05 to 0.60 inclusive, step 0.01", "tie_break": "Lowest threshold", "selected": thresholds},
        "average_precision_definition": "sklearn average_precision_score; AP, not trapezoidal PR-AUC",
        "bootstrap": bootstrap["settings"],
        "log_score_clipping": "Machine epsilon only; raw probabilities used for other metrics",
        "calibration": "Up to 10 model-specific quantile bins; duplicate boundaries merged; no test-set recalibration",
        "uncertainty_warning": "Fitted-model and tuning uncertainty are excluded; short held-out time horizon limits generalization.",
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "matplotlib": matplotlib.__version__},
        "qa_skipped": bool(args.skip_qa),
    }
    write_json(tables / "evaluation.json", evaluation)
    if not args.skip_qa:
        audit_source(Path(__file__).resolve(), args.qa_scripts, qa)
    contrasts = pd.read_csv(tables / "weather_contrasts.csv")
    pdfs = figures(out, test, metrics, calibration, contrasts, args.forest_model)
    if not args.skip_qa:
        audit_pdfs(pdfs, args.qa_scripts, qa)
    print(metrics.to_string(index=False))
    print("Paired loss differences (weather minus baseline):")
    print(differences.to_string(index=False))
    print(f"Completed evaluation and figures: {out}")


if __name__ == "__main__":
    main()
