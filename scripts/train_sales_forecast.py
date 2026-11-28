"""Training script of Nexova's sales forecast (``BRIEFING_NEXOVA_SALES.md``).

Run from the root of the repository:      uv run python scripts/train_sales_forecast.py

Stage 1, data preparation: load ``data/raw/nexova_sales.csv``, check its columns against the briefing, treat empty values, split by time (8 years to
train, the 2 most recent to test) and build the causal features. The scaler is part of the model, so it only ever learns from training rows.

Stage 2, training: a Random Forest (scikit-learn). Its settings are chosen by time validation INSIDE the training years; the test years take no part.
Why Random Forest and not XGBoost: ``data/process/sales_model.py``. ``--compare`` reproduces the comparison behind that choice.

Stage 3, evaluation on the two test years, with the model already fixed: MSE, PSI, Gini and K² Score, next to the rule without a model. The numbers are
printed and written to ``data/eval/sales_forecast/metrics.json`` (``--output`` changes the folder). What each metric means: the README of that folder.

Stage 4, the picture: the forecast WITH its range of variability against the real months of the test years, in ``forecast_test.png`` (English) and
``forecast_test.es.png`` (Spanish), in the same folder. How the range is built: ``data/process/sales_range.py``.

The random seed is fixed (``sales_model.SEED = 42``): running the script again over the same data gives the same numbers. Each step says what it did.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the root of the repository, so that ``data.`` can be imported

import pandas as pd  # noqa: E402

from data.process import sales_evaluation as ev  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_model as sm  # noqa: E402
from data.process import sales_plot as sp  # noqa: E402


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "eval" / "sales_forecast"
METRICS_FILE = "metrics.json"


@dataclass
class Prepared:
    """The data a model needs: the whole series, what was filled, and the rows to train and to test with their features. Scaling is NOT done here: the
    scaler is part of the model (``sales_model.make_pipeline``), so it is fitted exactly on the rows the model is fitted on, in the validation folds too."""

    sales: pd.DataFrame
    treated: list[dict]
    train: pd.DataFrame
    test: pd.DataFrame


def prepare(path: str | Path = sf.DEFAULT_DATASET) -> Prepared:
    sales, treated = sf.load_sales_with_report(path)
    train, test = sf.build_model_frames(sales)
    return Prepared(sales, treated, train, test)


def month(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m")


def describe(prepared: Prepared) -> str:
    sales, train, test = prepared.sales, prepared.train, prepared.test
    full_train, _ = sf.split_train_test(sales)
    filled = prepared.treated
    lines = [
        f"1. Dataset: {len(sales)} months of the {sf.MAIN_BUSINESS_LINE!r} series, {month(sales['month'].min())} to {month(sales['month'].max())}.",
        f"   Columns checked against the briefing: {', '.join(sf.COLUMNS)}.",
        f"2. Empty values treated: {len(filled)}." + "".join(f"\n   - {item['month']} {item['column']}: {item['method']}" for item in filled),
        f"3. Split by time: {len(full_train)} months to train ({month(full_train['month'].min())} to {month(full_train['month'].max())}), "
        f"{len(test)} to test ({month(test['month'].min())} to {month(test['month'].max())}).",
        f"   {len(full_train) - len(train)} first months have not enough past for the features: the model trains on {len(train)} rows.",
        f"4. Features: {len(sf.FEATURES)}, built from past months and the calendar only. Scaled inside the model: {len(sf.SCALED_FEATURES)} (fitted on training rows only); "
        f"0/1 flags left as they are: {', '.join(sf.FLAG_FEATURES)}.",
    ]
    return "\n".join(lines)


def describe_training(forecaster: sm.Forecaster, chosen: sm.Validation, tried: int, rows: int) -> str:
    years = sorted(chosen.rmse_by_year)
    weights = forecaster.feature_importances().head(5)
    lines = [
        f"5. Model: Random Forest (scikit-learn), trained on {rows} rows. It forecasts the month against the same month a year before.",
        f"   Settings chosen among {tried} by time validation on {years[0]}-{years[-1]} (training years only): "
        + ", ".join(f"{name}={value}" for name, value in forecaster.params.items()) + ".",
        f"   Mean error in those validated years: RMSE {chosen.rmse:,.0f} USD, {chosen.mape:.2f} % of the revenue of the month.",
        "   What weighs most in its splits: " + ", ".join(f"{name} {weight:.0%}" for name, weight in weights.items()) + ".",
        "   The test years (2024-2025) were not used to choose or to train.",
    ]
    return "\n".join(lines)


def describe_comparison(results: dict) -> str:
    lines = ["Comparison behind the choice (same folds, training years only):"]
    for name, result in results.items():
        per_year = ", ".join(f"{year}: {value:,.0f}" for year, value in result.rmse_by_year.items())
        lines.append(f"   {name:<38} RMSE {result.rmse:>7,.0f} USD  {result.mape:.2f} %   ({per_year})")
    return "\n".join(lines)


def describe_evaluation(report: dict) -> str:
    columns = (("model, 1 month ahead", report["model"]), ("no model", report[ev.NO_MODEL]), ("model, 24 months ahead", report["model_24_months_ahead"]))
    rows = (
        ("MSE (USD²)", "mse_usd2", "{:,.0f}"),
        ("  its square root (USD)", "rmse_usd", "{:,.0f}"),
        ("  as % of the mean month", "rmse_percent_of_mean_revenue", "{:.2f} %"),
        ("Gini", "gini", "{:.3f}"),
        ("K² Score (p-value)", None, None),
        ("MAPE", "mape_percent", "{:.2f} %"),
        ("bias (below 0: short)", "bias_percent", "{:+.2f} %"),
        ("R²", "r_squared", "{:.3f}"),
    )
    lines = [
        f"6. Evaluation on the test months {report['test_months']} (mean month: {report['mean_monthly_revenue_usd']:,.0f} USD). The model was not changed after this.",
        f"   {'':<26}" + "".join(f"{title:>24}" for title, _ in columns),
    ]
    for title, key, form in rows:
        cells = [f"{v['k2_statistic']:.2f} (p={v['k2_p_value']:.2f})" if key is None else form.format(v[key]) for _, v in columns]
        lines.append(f"   {title:<26}" + "".join(f"{cell:>24}" for cell in cells))
    psi = report["psi"]
    lines.append(
        f"7. PSI, training ({psi['reference_months']} rows) against test ({psi['current_months']} months), {psi['bins']} bins. "
        f"With samples this small, chance alone reaches {psi['noise_level_95']:.2f} (95 %):"
    )
    for name, item in psi["values"].items():
        above = "above" if item["psi"] > psi["noise_level_95"] else "within"
        lines.append(f"   {name:<26}{item['psi']:>6.3f}  {item['reading']}; {above} what chance gives")
    lines.append("   Mix of business lines: not measurable (the dataset only has the consolidated row).")
    lines.append("   Errors by kind of month (model, 1 month ahead): " + "; ".join(
        f"{name} {item['mape_percent']:.1f} % (bias {item['bias_percent']:+.1f} %, {item['months']} months)" for name, item in report["model_by_kind_of_month"].items()
    ) + ".")
    interval = report["range"]
    lines.append(
        f"8. Range of variability, {interval['level']:.0%}: the forecast ±{interval['half_width_percent']:.1f} % (from the errors on "
        f"{interval['calibrated_on_validation_months']} validated months of {interval['calibration_years'][0]}-{interval['calibration_years'][-1]}). "
        f"{interval['inside']} of {interval['test_months']} real test months fall inside."
        + "".join(f" Outside: {item['month']}, {item['side']} the range by {item['beyond_percent']:.1f} %." for item in interval["outside"])
    )
    return "\n".join(lines)


def write_metrics(report: dict, folder: str | Path) -> Path:
    """The numbers as a file (no date inside: running it again over the same data writes the same bytes)."""
    path = Path(folder) / METRICS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train Nexova's sales forecast.")
    parser.add_argument("--compare", action="store_true", help="also compare Random Forest with XGBoost (training years only)")
    parser.add_argument("--data", default=str(sf.DEFAULT_DATASET), help="the sales CSV (default: data/raw/nexova_sales.csv)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help=f"folder for {METRICS_FILE} and the pictures (default: data/eval/sales_forecast)")
    arguments = parser.parse_args(argv)
    try:
        prepared = prepare(arguments.data)
    except (sf.DatasetError, FileNotFoundError) as problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print(describe(prepared))
    results = sm.tune(prepared.train)  # the training rows only
    forecaster = sm.train_forecaster(prepared.train, results[0].params)
    print(describe_training(forecaster, results[0], len(results), len(prepared.train)))
    if arguments.compare:
        print(describe_comparison(sm.compare_algorithms(prepared.train)))
    report = ev.evaluate(prepared.sales, prepared.train, prepared.test, forecaster)  # the model is fixed from here on
    print(describe_evaluation(report))
    print(f"Metrics written to {write_metrics(report, arguments.output)}")
    for language, name in sp.FILES.items():
        print(f"Picture written to {sp.plot_forecast(report, Path(arguments.output) / name, language)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
