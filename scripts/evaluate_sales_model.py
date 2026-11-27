"""Formal evaluation of Nexova's sales forecast: bias, variance and stability.

Run from the root of the repository:      uv run python scripts/evaluate_sales_model.py

It measures the Random Forest of the previous project on the TRAINING years only (2016-2023): nested time-series cross-validation (all the past, and only
the last 24 months), the learning curve and the complexity curve. The numbers are written to ``data/eval/regression_eval/diagnosis.json`` and the curves
to ``diagnosis_curves.png`` (English) and ``diagnosis_curves.es.png`` (Spanish). THE LEARNING CURVE has an image of its own in ``data/eval/``:
``learning_curve.png`` and ``learning_curve.es.png``. What is measured and how: ``data/process/sales_diagnosis.py``.

Then it asks WHY the model misses and tries the corrections declared in advance (``data/process/sales_root_cause.py``); those numbers are written to
``root_cause.json`` next to the others. The written report that reads them all is ``data/eval/evaluation_report.md``.
It takes about 10 minutes. The random seed is fixed: running it again gives the same numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the root of the repository, so that ``data.`` can be imported

from data.process import sales_diagnosis as sd  # noqa: E402
from data.process import sales_diagnosis_plot as sdp  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_root_cause as rc  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "eval" / "regression_eval"
DEFAULT_CURVE_FOLDER = DEFAULT_OUTPUT.parent  # data/eval: where the learning curve is asked to be saved
REPORT_FILE = "diagnosis.json"
ROOT_CAUSE_FILE = "root_cause.json"


def describe_root_cause(report: dict) -> str:
    noise = report["noise"]
    lines = ["5. How much cannot be predicted (estimated chance variation of a month, % of its revenue):"]
    for name, fit in noise["fits"].items():
        lines.append(f"   season of each month + {name:<30} {fit['std_percent']:.2f} % ({fit['parameters']} parameters; the fit itself misses {fit['in_sample_percent']:.2f} % on the months it saw)")
    lines.append(f"   from the briefing's ±5 % of the ordinary months, if evenly spread: {noise['from_the_briefing_percent']:.2f} %")
    lines.append("6. Does the error carry the chance of the month the forecast is multiplied by? Correlation of the validation error with how unusual a month BEFORE was:")
    for name, specs in report["error_against_noise"].items():
        for spec, lags in specs.items():
            lines.append(f"   {name:<18} {spec:<28}" + "  ".join(f"{lag} before: {item['correlation']:+.2f}" for lag, item in lags.items()))
    for anchor, item in report["anchor_profile"].items():
        if anchor != "real_growth_by_year_percent":
            offsets = ", ".join(f"{year} {value:+.1f}" for year, value in item["mean_offset_by_year_percent"].items())
            lines.append(f"   {anchor:<18} against the real month: spread within the year {item['spread_within_the_year_percent']:.2f} % | mean offset by year (%): {offsets}")
    lines.append("7. Corrections declared before measuring them (same 8 folds, same nested choice). Rule: lower validation RMSE, in 5 of 8 folds or more, gap no wider.")
    for name, item in report["candidates"].items():
        s = item["summary"]
        lines.append(f"   {name} ({item['description']})")
        lines.append(f"      RMSE training {s['training']['rmse_usd']['mean']:>7,.0f} ± {s['training']['rmse_usd']['std']:>6,.0f} | validation {s['validation']['rmse_usd']['mean']:>7,.0f} ± {s['validation']['rmse_usd']['std']:>6,.0f}"
                     f" | from the boundary {s['validation_from_boundary']['rmse_usd']['mean']:>7,.0f} | gap {s['gap_rmse_usd']:>6,.0f} USD | MAE validation {s['validation']['mae_usd']['mean']:>7,.0f}")
        lines.append(f"      relative miss: training {item['training_relative_rmse_percent']['mean']:.2f} %, validation {item['validation_relative_rmse_percent']['mean']:.2f} %"
                     f" | the number it multiplies by, alone: RMSE {item['anchor_alone_rmse_usd']['mean']:,.0f} USD")
        if "against_current" in item:
            a = item["against_current"]
            lines.append(f"      against the current model: {a['mean_change_usd']:+,.0f} USD (standard error {a['standard_error_of_change_usd']:,.0f}; without its best fold {a['mean_change_without_best_fold_usd']:+,.0f})"
                         f" | better in {a['folds_improved']} of 8 | gap {a['gap_before_usd']:,.0f} -> {a['gap_after_usd']:,.0f} | {'ACCEPTED' if a['accepted'] else 'REJECTED'}")
    return "\n".join(lines)


def describe(report: dict) -> str:
    lines = [
        "Nexova, revenue_usd of the consolidated business line (data/raw/nexova_sales.csv).",
        f"Training years only: {report['months_used']} ({report['rows']} rows with features). The test years are not used.",
        "Settings of the evaluated model: " + ", ".join(f"{k}={v}" for k, v in report["model_settings"].items()) + ".",
    ]
    checks = report["fold_checks"]
    lines.append(f"0. Checks of the {len(checks['chronological_order'])} folds (TimeSeriesSplit, no shuffling):")
    for order, features in zip(checks["chronological_order"], checks["features_at_fold_boundaries"], strict=True):
        lines.append(f"   fold {order['fold']}: trains {order['training']}  ->  validates {order['validation']} | months in order: yes | "
                     f"lag/rolling features recomputed at the boundary ({features['training_rows_recomputed']} training + {features['validation_rows_recomputed']} validation rows): identical")
    for title, key in (("1. Cross-validation, learning from all the past", "cross_validation_all_past"),
                       (f"2. Cross-validation, learning from the last {sd.SLIDING_WINDOW} months only", f"cross_validation_last_{sd.SLIDING_WINDOW}_months")):
        block = report[key]
        lines.append(f"{title} (settings chosen inside each fold, with its past only). USD of revenue_usd; chosen metric: RMSE.")
        lines.append(f"   {'fold':<5}{'validates':<20}{'months':>6}{'RMSE train':>12}{'RMSE valid':>12}{'MAE train':>11}{'MAE valid':>11}{'boundary RMSE':>15}{'bias %':>8}{'no model RMSE':>15}")
        for fold in block["folds"]:
            lines.append(f"   {fold['fold']:<5}{fold['validated_months']:<20}{fold['training_months']:>6}{fold['training']['rmse_usd']:>12,.0f}{fold['validation']['rmse_usd']:>12,.0f}"
                         f"{fold['training']['mae_usd']:>11,.0f}{fold['validation']['mae_usd']:>11,.0f}{fold['validation_from_boundary']['rmse_usd']:>15,.0f}"
                         f"{fold['validation']['bias_percent']:>+8.2f}{fold['no_model']['rmse_usd']:>15,.0f}")
        s = block["summary"]
        lines.append(f"   MEAN ± STANDARD DEVIATION across the {len(block['folds'])} folds (% = of the mean monthly revenue of the months measured):")
        for label, part in (("training", "training"), ("validation, 1 month ahead", "validation"), ("validation, from the boundary", "validation_from_boundary"), ("no model", "no_model")):
            pieces = []
            for name, short in (("rmse", "RMSE"), ("mae", "MAE")):
                usd, share = s[part][f"{name}_usd"], s[part][f"{name}_percent_of_mean_revenue"]
                pieces.append(f"{short} {usd['mean']:>7,.0f} ± {usd['std']:>6,.0f} USD ({share['mean']:.2f} ± {share['std']:.2f} %)")
            lines.append(f"      {label:<31}" + "   ".join(pieces))
        lines.append(f"      gap between training and validation: RMSE {s['gap_rmse_usd']:,.0f} USD, MAE {s['gap_mae_usd']:,.0f} USD")
    profile = report["validation_error_profile"]
    lines.append(f"   The {profile['months']} validated months together: MAE {profile['overall']['mae_usd']:,.0f}, RMSE {profile['overall']['rmse_usd']:,.0f} USD (RMSE/MAE {profile['rmse_over_mae']:.2f}). "
                 f"The {len(profile['worst_months'])} worst months weigh {profile['worst_months_share_of_squared_error']:.0%} of the squared error and {profile['worst_months_share_of_absolute_error']:.0%} of the absolute error.")
    for name, item in profile["by_kind_of_month"].items():
        lines.append(f"      {name:<22} {item['months']:>2} months: MAE {item['mae_usd']:>7,.0f}  RMSE {item['rmse_usd']:>7,.0f} USD")
    lines.append(f"3. Learning curve (the same {report['learning_curve'][0]['blocks']} validation blocks for every size). USD:")
    for point in report["learning_curve"]:
        lines.append(f"   {point['training_months']:>3} months: RMSE training {point['training_rmse_usd']['mean']:>7,.0f}, validation {point['validation_rmse_usd']['mean']:>7,.0f}"
                     f" | MAE training {point['training_mae_usd']['mean']:>7,.0f}, validation {point['validation_mae_usd']['mean']:>7,.0f}")
    lines.append("4. Complexity curve (maximum depth of the trees, the same 8 folds). USD:")
    for point in report["complexity_curve"]:
        depth = "no limit" if point["max_depth"] is None else point["max_depth"]
        lines.append(f"   depth {depth!s:<9} RMSE training {point['training_rmse_usd']['mean']:>7,.0f}, validation {point['validation_rmse_usd']['mean']:>7,.0f}"
                     f" | MAE training {point['training_mae_usd']['mean']:>7,.0f}, validation {point['validation_mae_usd']['mean']:>7,.0f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate bias, variance and stability of Nexova's sales forecast.")
    parser.add_argument("--data", default=str(sf.DEFAULT_DATASET), help="the sales CSV (default: data/raw/nexova_sales.csv)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="folder for the numbers and the curves (default: data/eval/regression_eval)")
    parser.add_argument("--curve-output", help="folder for the learning curve (default: data/eval; with --output, that folder)")
    arguments = parser.parse_args(argv)
    # a run that sends its results elsewhere (a test, a trial) never rewrites the files of the repository
    curve_folder = Path(arguments.curve_output or (DEFAULT_CURVE_FOLDER if Path(arguments.output) == DEFAULT_OUTPUT else arguments.output))
    try:
        sales = sf.load_sales(arguments.data)
        train, _ = sf.build_model_frames(sales)  # the test rows are dropped here and never seen again
    except (sf.DatasetError, FileNotFoundError) as problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    series = sales[sales["month"] < sd.TEST_STARTS]
    report = sd.diagnose_data(train, series)
    print(describe(report))
    folder = Path(arguments.output)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / REPORT_FILE).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Numbers written to {folder / REPORT_FILE}")
    root_cause = rc.root_cause_report(series)
    print(describe_root_cause(root_cause))
    (folder / ROOT_CAUSE_FILE).write_text(json.dumps(root_cause, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Numbers written to {folder / ROOT_CAUSE_FILE}")
    for language, name in sdp.FILES.items():
        print(f"Curves written to {sdp.plot_diagnosis(report, folder / name, language)}")
    for language, name in sdp.LEARNING_CURVE_FILES.items():
        print(f"Learning curve written to {sdp.plot_learning_curve(report, curve_folder / name, language)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
