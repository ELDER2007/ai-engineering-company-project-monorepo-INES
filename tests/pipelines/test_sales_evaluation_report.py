"""The root-cause analysis (``data/process/sales_root_cause.py``) and the technical report (``data/eval/evaluation_report.md`` and ``.es.md``).

Every figure of the report is compared with the saved results, the saved results with what the code computes today, and what the report SAYS about them
is checked claim by claim.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_evaluation_report.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from data.process import sales_diagnosis as sd  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_model as sm  # noqa: E402
from data.process import sales_root_cause as rc  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[2]
EVAL = REPOSITORY / "data" / "eval"
REPORTS = {"en": EVAL / "evaluation_report.md", "es": EVAL / "evaluation_report.es.md"}
SMALL_GRID = ({"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}, {"max_depth": 5, "min_samples_leaf": 4, "max_features": 0.5})


@pytest.fixture(scope="module")
def sales():
    return sf.load_sales()


@pytest.fixture(scope="module")
def series(sales):
    return sales[sales["month"] < sd.TEST_STARTS].reset_index(drop=True)


@pytest.fixture(scope="module")
def diagnosis():
    return json.loads((EVAL / "regression_eval" / "diagnosis.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cause():
    return json.loads((EVAL / "regression_eval" / "root_cause.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=sorted(REPORTS))
def report(request):
    return request.param, REPORTS[request.param].read_text(encoding="utf-8")


def small(**changes) -> rc.Candidate:
    return rc.Candidate("test", grid=SMALL_GRID, **changes)


@pytest.fixture(scope="module")
def small_folds(series):
    return rc.evaluate_candidate(series, small())


# ================================================================ the analysis


def test_every_part_of_the_analysis_refuses_the_test_years(sales, small_folds):
    for call in (rc.noise_estimate, lambda s: rc.error_against_noise(small_folds, s), lambda s: rc.evaluate_candidate(s, small()),
                 lambda s: rc.anchor_profile(s, ["2023-01"]), rc.root_cause_report):
        with pytest.raises(ValueError, match="training years only"):
            call(sales)


def made_up_series(seed: int, chance: float = 0.03) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Eight years with a KNOWN chance variation: a season, a growth that alternates, and noise of standard deviation ``chance``."""
    months = pd.date_range("2016-01-01", "2023-12-01", freq="MS")
    season = np.array([1.18, 1.16, 1.0, 1.01, 0.99, 1.0, 0.98, 0.8, 1.0, 1.02, 0.99, 1.0])[months.month - 1]
    growth = np.cumprod([1 + (0.07 if date.year % 2 else 0.01) / 12 for date in months])
    left = np.random.default_rng(seed).normal(0, chance, len(months))
    level = 700_000 * season * growth
    return pd.DataFrame({"month": months, "revenue_usd": level * np.exp(left)}), level, left


def test_the_noise_estimate_finds_a_known_chance_variation():
    estimates = [rc.noise_estimate(made_up_series(seed)[0]) for seed in range(20)]
    for name in estimates[0]["fits"]:
        assert np.mean([item["fits"][name]["std_percent"] for item in estimates]) == pytest.approx(3.0, abs=0.3), name
        assert all(item["fits"][name]["in_sample_percent"] < item["fits"][name]["std_percent"] for item in estimates)  # a fit misses less on what it saw
    assert estimates[0]["from_the_briefing_percent"] == pytest.approx(5 / 3**0.5)


def test_the_control_finds_the_month_that_is_copied_and_only_that_one():
    """A forecast that knows the level exactly but copies the chance of the month 12 before: lag 12 must stand out, 11 and 13 must not."""
    series, level, left = made_up_series(seed=1)
    rows = [{"month": f"{series['month'].iloc[i]:%Y-%m}", "revenue_usd": float(series["revenue_usd"].iloc[i]),
             "forecast_usd": float(level[i] * np.exp(left[i - 12]))} for i in range(48, 96)]
    for spec, lags in rc.error_against_noise([{"monthly": rows}], series).items():
        assert lags["12"]["correlation"] > 0.5, spec
        assert abs(lags["11"]["correlation"]) < 0.35 and abs(lags["13"]["correlation"]) < 0.35, spec
        assert lags["12"]["share_of_variance"] == pytest.approx(lags["12"]["correlation"] ** 2)


def test_the_two_year_anchor_by_hand_and_without_looking_at_its_own_month_or_later(series):
    featured = rc.add_two_year_anchor(series)
    at = int(np.flatnonzero(featured["month"] == "2021-08-01")[0])
    revenue = series["revenue_usd"].to_numpy()
    growth = revenue[at - 12:at].mean() / revenue[at - 24:at - 12].mean()
    assert featured[rc.SMOOTHED_ANCHOR].iloc[at] == pytest.approx((revenue[at - 12] * growth + revenue[at - 24] * growth**2) / 2)
    for month in pd.date_range("2018-01-01", "2023-12-01", freq="MS"):
        known = series[series["month"] <= month][["month", "revenue_usd"]].copy()
        known.loc[known["month"] == month, "revenue_usd"] = np.nan
        assert rc.add_two_year_anchor(known)[rc.SMOOTHED_ANCHOR].iloc[-1] == pytest.approx(featured.set_index("month").loc[month, rc.SMOOTHED_ANCHOR]), month


def test_the_two_year_anchor_loses_no_training_row(series):
    columns = [*sf.FEATURES, rc.SMOOTHED_ANCHOR]
    assert len(rc.add_two_year_anchor(series).dropna(subset=columns)) == len(sf.add_features(series).dropna(subset=list(sf.FEATURES))) == 72


def test_for_the_current_anchor_it_is_the_same_evaluation_as_the_diagnosis(series, small_folds):
    train = sf.add_features(series).dropna(subset=list(sf.FEATURES)).reset_index(drop=True)
    expected = sd.cross_validate(train, series, grid=SMALL_GRID)
    for mine, theirs in zip(small_folds, expected, strict=True):
        assert mine["params"] == theirs["params"]
        for part in ("training", "validation", "validation_from_boundary", "no_model"):
            assert mine[part] == pytest.approx(theirs[part]), (mine["fold"], part)


def test_no_model_of_a_candidate_learns_from_its_validation_months_or_later(series, monkeypatch):
    seen, real = [], rc.fit

    def spy(past, params, anchor):
        seen.append(past["month"].max())
        return real(past, params, anchor)

    chosen_from, real_choose = [], rc._choose
    monkeypatch.setattr(rc, "fit", spy)

    def spy_choose(past, candidate):
        start = len(seen)
        chosen_from.append((past["month"].max(), start))
        return real_choose(past, candidate)

    monkeypatch.setattr(rc, "_choose", spy_choose)
    folds = rc.evaluate_candidate(series, small(anchor=rc.SMOOTHED_ANCHOR, build=rc.add_two_year_anchor))
    ends = [start for _, start in chosen_from] + [len(seen)]
    for fold, (past_end, start), end in zip(folds, chosen_from, ends[1:], strict=True):
        first_validated = pd.Timestamp(f"{fold['validated_months'][:7]}-01")
        assert past_end < first_validated and end > start and max(seen[start:end]) < first_validated, fold["fold"]


def test_the_forecast_from_the_boundary_of_a_candidate_uses_no_real_value_after_it(series, small_folds):
    changed = series.copy()
    last = changed["month"] >= "2023-07-01"  # the validation block of fold 8
    changed.loc[last, "revenue_usd"] *= 3
    again = rc.evaluate_candidate(changed, small())[-1]
    assert again["params"] == small_folds[-1]["params"]
    # other real values after the boundary: the forecasts from it must be the same ones, only their error changes
    train = sf.add_features(series).dropna(subset=list(sf.FEATURES)).reset_index(drop=True)
    predict = rc.fit(train.iloc[:-6], again["params"], "revenue_lag_12")
    first = rc._from_boundary(predict, series[series["month"] < "2023-07-01"], 6, sf.add_features)
    second = rc._from_boundary(predict, changed[changed["month"] < "2023-07-01"], 6, sf.add_features)
    assert first == pytest.approx(second)
    assert again["validation_from_boundary"] == pytest.approx(sd.errors(changed.loc[last, "revenue_usd"], first))


def folds_with(validation, training) -> list[dict]:
    return [{"validation": {"rmse_usd": v}, "training": {"rmse_usd": t}} for v, t in zip(validation, training, strict=True)]


@pytest.mark.parametrize("validation, training, accepted, why", [
    ([90] * 8, [50] * 8, True, None),
    ([90] * 5 + [105] * 3, [50] * 8, True, None),
    ([60] * 4 + [101] * 4, [50] * 8, False, "improves_enough_folds"),
    ([99] * 7 + [150], [60] * 8, False, "lower_mean_validation_rmse"),
    ([90] * 8, [30] * 8, False, "gap_not_wider"),
])
def test_the_rule_asks_for_the_three_conditions(validation, training, accepted, why):
    verdict = rc.meets_rule(folds_with([100] * 8, [50] * 8), folds_with(validation, training))
    assert verdict["accepted"] is accepted
    if why:
        assert verdict[why] is False


def test_the_sensitivity_leaves_out_the_best_fold():
    verdict = rc.meets_rule(folds_with([100] * 8, [50] * 8), folds_with([20] + [101] * 7, [50] * 8))
    assert verdict["mean_change_usd"] == pytest.approx((-80 + 7) / 8) and verdict["mean_change_without_best_fold_usd"] == pytest.approx(1.0)


def test_the_candidates_are_the_four_declared_ones():
    assert list(rc.CANDIDATES) == [rc.CURRENT, "shallower_trees", "bigger_leaves", rc.SMOOTHED_ANCHOR]
    assert rc.CANDIDATES[rc.CURRENT].grid == sm.PARAM_GRID and rc.CANDIDATES[rc.CURRENT].anchor == "revenue_lag_12"
    assert {setting["max_depth"] for setting in rc.CANDIDATES["shallower_trees"].grid} == {2}
    assert len(rc.CANDIDATES["shallower_trees"].grid) == 6 and all(setting in [{**g, "max_depth": 2} for g in sm.PARAM_GRID] for setting in rc.CANDIDATES["shallower_trees"].grid)
    assert {setting["min_samples_leaf"] for setting in rc.CANDIDATES["bigger_leaves"].grid} == {6}
    assert rc.CANDIDATES[rc.SMOOTHED_ANCHOR].grid == sm.PARAM_GRID


# ================================================================ the saved numbers are the computed ones


def test_the_saved_current_model_is_the_one_of_the_diagnosis(diagnosis, cause):
    mine = cause["candidates"][rc.CURRENT]["folds"]
    for saved, other in zip(mine, diagnosis["cross_validation_all_past"]["folds"], strict=True):
        assert saved["params"] == other["params"] and saved["training"] == pytest.approx(other["training"]) and saved["validation"] == pytest.approx(other["validation"])


def test_the_saved_noise_control_and_anchor_profile_are_what_the_code_computes_today(series, cause):
    noise = rc.noise_estimate(series)
    for name, fit in noise["fits"].items():
        assert fit == pytest.approx(cause["noise"]["fits"][name]), name
    for candidate, item in cause["candidates"].items():
        today = rc.error_against_noise(item["folds"], series)
        for spec, lags in today.items():
            for lag, values in lags.items():
                assert values == pytest.approx(cause["error_against_noise"][candidate][spec][lag]), (candidate, spec, lag)
    profile = rc.anchor_profile(series, [row["month"] for fold in cause["candidates"][rc.CURRENT]["folds"] for row in fold["monthly"]])
    for anchor in ("revenue_lag_12", rc.SMOOTHED_ANCHOR):
        assert profile[anchor]["spread_within_the_year_percent"] == pytest.approx(cause["anchor_profile"][anchor]["spread_within_the_year_percent"])
        assert profile[anchor]["mean_offset_by_year_percent"] == pytest.approx(cause["anchor_profile"][anchor]["mean_offset_by_year_percent"])


def test_the_saved_numbers_of_the_recommended_correction_are_what_the_code_computes_today(series, cause):
    today = rc.evaluate_candidate(series, rc.CANDIDATES["shallower_trees"])
    for mine, saved in zip(today, cause["candidates"]["shallower_trees"]["folds"], strict=True):
        assert mine["params"] == saved["params"]
        for part in ("training", "validation", "validation_from_boundary"):
            assert mine[part] == pytest.approx(saved[part]), (mine["fold"], part)
    current = cause["candidates"][rc.CURRENT]["folds"]
    assert rc.meets_rule(current, today)["mean_change_usd"] == pytest.approx(cause["candidates"]["shallower_trees"]["against_current"]["mean_change_usd"])


def test_the_saved_verdict_of_every_candidate_follows_from_its_folds(cause):
    current = cause["candidates"][rc.CURRENT]["folds"]
    verdicts = {}
    for name, item in cause["candidates"].items():
        if name != rc.CURRENT:
            again = rc.meets_rule(current, item["folds"])
            assert set(again) == set(item["against_current"])
            for key, value in again.items():
                assert value == pytest.approx(item["against_current"][key]), (name, key)
            verdicts[name] = again["accepted"]
    assert verdicts == {"shallower_trees": True, "bigger_leaves": False, rc.SMOOTHED_ANCHOR: False}


# ================================================================ the report


def usd(value: float) -> str:
    return f"{value:,.0f}"


def table_rows(text: str) -> list[list[str]]:
    return [[cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")] for line in text.splitlines() if line.strip().startswith("|")]


def test_both_reports_exist_and_link_to_each_other():
    assert "evaluation_report.es.md" in REPORTS["en"].read_text(encoding="utf-8")
    assert "(./evaluation_report.md)" in REPORTS["es"].read_text(encoding="utf-8")


def test_the_report_classifies_the_model_explicitly_before_anything_else(report):
    language, text = report
    verdict = {"en": "**Classification: OVERFITTING (moderate).**", "es": "**Clasificación: OVERFITTING (moderado).**"}[language]
    assert text.count(verdict) == 1 and text.index(verdict) < text.index("## 1.")
    assert len(re.findall(r"\*\*(?:Classification|Clasificación):", text)) == 1


def test_the_report_interprets_the_pattern_of_the_learning_curve_explicitly(report, diagnosis):
    language, text = report
    heading = {"en": "**Pattern of the curve: overfitting.**", "es": "**Patrón de la curva: overfitting.**"}[language]
    assert text.index(heading) < text.index("## 3.")
    curve = diagnosis["learning_curve"]
    training = [point["training_rmse_usd"]["mean"] for point in curve]
    validation = [point["validation_rmse_usd"]["mean"] for point in curve]
    for value in (min(training), max(training), validation[0], validation[-1], validation[0] - training[0], validation[-1] - training[-1]):
        assert usd(value) in text.split(heading)[1].split("## 3.")[0], value
    assert all(v > t for t, v in zip(training, validation, strict=True))  # "far above it at every size": they never meet
    assert max(training) - min(training) < 0.2 * (validation[0] - validation[-1] + max(training))  # "almost flat"


def test_the_report_compares_two_metrics_and_justifies_the_main_one_with_measured_business_evidence(report, diagnosis):
    language, text = report
    section = text.split("## 1.")[1].split("## 2.")[0]
    profile = diagnosis["validation_error_profile"]
    august = profile["by_kind_of_month"]["August"]
    for value in (f"{profile['worst_months_share_of_squared_error']:.0%}".replace("%", " %"), f"{profile['worst_months_share_of_absolute_error']:.0%}".replace("%", " %"),
                  usd(august["rmse_usd"]), usd(profile["overall"]["rmse_usd"])):
        assert value in section, value
    for word in ("MAE", "RMSE", "MSE", "Laura", "Gini"):
        assert word in section, word
    assert august["rmse_usd"] == max(item["rmse_usd"] for item in profile["by_kind_of_month"].values())  # "August is where it misses most"
    folds_saved = diagnosis["cross_validation_all_past"]["folds"]
    losses = [sum(f["validation"][k] > f["no_model"][k] for f in folds_saved) for k in ("rmse_usd", "mae_usd")]
    assert losses == [2, 3]
    assert {"en": "in 2 of the 8 folds with RMSE and in 3 with MAE", "es": "en 2 de los 8 bloques con RMSE y en 3 con MAE"}[language] in section


def test_the_report_points_to_the_chronological_order_test_and_how_to_run_it(report):
    _, text = report
    assert (REPOSITORY / "tests" / "pipelines" / "test_sales_cv_chronological_order.py").is_file()
    assert "uv run pytest tests/pipelines/test_sales_cv_chronological_order.py" in text


def test_every_relative_link_of_the_report_exists_and_the_learning_curve_is_shown(report):
    language, text = report
    links = re.findall(r"\]\((\.[^)#]+)\)", text)
    assert links and all((EVAL / link).resolve().is_file() for link in links), [link for link in links if not (EVAL / link).resolve().is_file()]
    picture = {"en": "./learning_curve.png", "es": "./learning_curve.es.png"}[language]
    assert re.search(r"!\[[^\]]+\]\(" + re.escape(picture) + r"\)", text)


def test_the_learning_curve_table_has_the_measured_numbers(report, diagnosis):
    _, text = report
    points = {point["training_months"]: point for point in diagnosis["learning_curve"]}
    for size in (12, 24, 36, 48):
        train_, valid = points[size]["training_rmse_usd"]["mean"], points[size]["validation_rmse_usd"]["mean"]
        found = [row for row in table_rows(text) if len(row) == 4 and row[0] == str(size)]
        assert len(found) == 1 and found[0][1:] == [usd(train_), usd(valid), usd(valid - train_)], size


def test_the_cross_validation_table_has_the_mean_and_deviation(report, diagnosis):
    language, text = report
    summary = diagnosis["cross_validation_all_past"]["summary"]
    labels = {"en": ("Training", "Validation", "No model"), "es": ("Entrenamiento", "Validación", "Sin modelo")}[language]
    for label, part in zip(labels, ("training", "validation", "no_model"), strict=True):
        found = [row for row in table_rows(text) if len(row) == 4 and (row[0] == label or row[0].startswith(f"{label} ("))]
        assert len(found) == 1, label
        r, p, m = (summary[part][key] for key in ("rmse_usd", "rmse_percent_of_mean_revenue", "mae_usd"))
        assert found[0][1:] == [f"{usd(r['mean'])} ± {usd(r['std'])}", f"{p['mean']:.2f} ± {p['std']:.2f} %", f"{usd(m['mean'])} ± {usd(m['std'])}"]


def test_the_depth_table_has_the_measured_numbers_and_what_is_said_about_it_is_true(report, diagnosis):
    language, text = report
    by_depth = {point["max_depth"]: point for point in diagnosis["complexity_curve"]}
    for label, part in (({"en": "Training RMSE", "es": "RMSE entrenamiento"}[language], "training_rmse_usd"), ({"en": "Validation RMSE", "es": "RMSE validación"}[language], "validation_rmse_usd")):
        found = [row for row in table_rows(text) if len(row) == 5 and row[0] == label]
        assert len(found) == 1 and found[0][1:] == [usd(by_depth[depth][part]["mean"]) for depth in (1, 2, 3, None)]
    deeper = [point for point in diagnosis["complexity_curve"] if point["max_depth"] is None or point["max_depth"] >= 2]
    training = [point["training_rmse_usd"]["mean"] for point in deeper]
    validation = [point["validation_rmse_usd"]["mean"] for point in deeper]
    assert training == sorted(training, reverse=True) and validation == sorted(validation)  # past depth 2, only training improves


def test_the_control_table_has_the_measured_correlations_and_the_control_passes(report, cause):
    _, text = report
    specs = cause["error_against_noise"][rc.CURRENT]
    rows = [row for row in table_rows(text) if len(row) == 4 and re.fullmatch(r"[+-]0\.\d\d", row[2])]
    assert len(rows) == 2
    for row, name in zip(rows, ("a level for each year", "a growth rate for each year"), strict=True):
        assert row[1:] == [f"{specs[name][lag]['correlation']:+.2f}" for lag in ("11", "12", "13")]
    for lags in specs.values():
        assert 0.24 < lags["12"]["share_of_variance"] < 0.34  # "between a quarter and a third"
        assert abs(lags["11"]["correlation"]) < 0.2 and abs(lags["13"]["correlation"]) < 0.2
    shallow = [f"{item['12']['correlation']:+.2f}" for item in cause["error_against_noise"]["shallower_trees"].values()]
    assert all(value in text for value in shallow)


def test_the_candidate_table_shows_every_candidate_also_the_ones_that_failed(report, cause):
    language, text = report
    labels = {"en": ("Current model", "Depth 2", "Leaves of 6", "Base of two years"), "es": ("Modelo actual", "Profundidad 2", "Hojas de 6", "Base con dos años")}[language]
    yes, no, of = {"en": ("Yes", "No", "of"), "es": ("Sí", "No", "de")}[language]
    for label, (name, item) in zip(labels, cause["candidates"].items(), strict=True):
        found = [row for row in table_rows(text) if len(row) == 8 and row[0].startswith(label)]
        assert len(found) == 1, label
        s = item["summary"]
        assert found[0][1:5] == [usd(s["training"]["rmse_usd"]["mean"]), usd(s["validation"]["rmse_usd"]["mean"]), usd(s["gap_rmse_usd"]), usd(s["validation"]["mae_usd"]["mean"])]
        if name == rc.CURRENT:
            assert found[0][5:] == ["", "", ""]
        else:
            against = item["against_current"]
            assert found[0][5:] == [f"{against['mean_change_usd']:+,.0f} ± {usd(against['standard_error_of_change_usd'])}", f"{against['folds_improved']} {of} 8", yes if against["accepted"] else no]


def test_the_figures_written_in_the_text_are_the_measured_ones(report, diagnosis, cause):
    _, text = report
    everything, last = diagnosis["cross_validation_all_past"]["summary"], diagnosis["cross_validation_last_24_months"]["summary"]
    points = {point["training_months"]: point for point in diagnosis["learning_curve"]}
    valid = everything["validation"]["rmse_usd"]
    share = everything["validation"]["rmse_percent_of_mean_revenue"]
    current, shallow, anchor = (cause["candidates"][name] for name in (rc.CURRENT, "shallower_trees", rc.SMOOTHED_ANCHOR))
    against = shallow["against_current"]
    change = np.array(against["change_by_fold_usd"])
    spreads = [points[size]["validation_rmse_usd"]["std"] for size in (24, 30, 36, 42, 48)]
    later = [points[size]["validation_rmse_usd"]["mean"] for size in (24, 30, 36, 42, 48)]
    noise = cause["noise"]
    fits = noise["fits"].values()
    offsets = cause["anchor_profile"]["revenue_lag_12"]["mean_offset_by_year_percent"]
    smoothed = cause["anchor_profile"][rc.SMOOTHED_ANCHOR]["mean_offset_by_year_percent"]
    expected = [
        f"{usd(valid['min'])}", f"{usd(valid['max'])}", f"{share['min']:.2f} %", f"{share['max']:.2f} %",
        f"{valid['std'] / valid['mean']:.0%}".replace("%", " %"),
        f"{usd(last['validation']['rmse_usd']['mean'])} ± {usd(last['validation']['rmse_usd']['std'])}",
        f"{usd(everything['validation_from_boundary']['rmse_usd']['mean'])} ± {usd(everything['validation_from_boundary']['rmse_usd']['std'])}",
        f"{usd(points[12]['validation_rmse_usd']['mean'])} ± {usd(points[12]['validation_rmse_usd']['std'])}",
        usd(min(later)), usd(max(later)),
        usd(round(points[24]["validation_rmse_usd"]["mean"] - points[48]["validation_rmse_usd"]["mean"], -2)), usd(min(spreads)), usd(max(spreads)),
        f"{noise['lowest_percent']:.2f}-{noise['highest_percent']:.2f} %", f"{noise['from_the_briefing_percent']:.2f} %",
        f"{min(f['in_sample_percent'] for f in fits):.2f}-{max(f['in_sample_percent'] for f in fits):.2f} %",
        f"{current['training_relative_rmse_percent']['mean']:.2f} %", f"{shallow['training_relative_rmse_percent']['mean']:.2f} %",
        usd(-against["mean_change_usd"]), usd(against["standard_error_of_change_usd"]),
        f"{change.min() / change.sum():.0%}".replace("%", " %"), usd(-against["mean_change_without_best_fold_usd"]),
        f"{1 - against['gap_after_usd'] / against['gap_before_usd']:.0%}".replace("%", " %"),
        f"({-against['mean_change_usd'] / current['summary']['validation']['rmse_usd']['mean']:.0%})".replace("%", " %"),
        usd(anchor["anchor_alone_rmse_usd"]["mean"]), usd(current["anchor_alone_rmse_usd"]["mean"]),
        f"{offsets['2021']:+.1f} %", f"{offsets['2023']:+.1f} %", f"{offsets['2020']:+.1f} %", f"{offsets['2022']:+.1f} %",
        f"{min(smoothed.values()):+.1f} %", f"{max(smoothed.values()):+.1f} %",
        f"{cause['anchor_profile'][rc.SMOOTHED_ANCHOR]['spread_within_the_year_percent']:.2f} %",
        f"{cause['anchor_profile']['revenue_lag_12']['spread_within_the_year_percent']:.2f} %",
        usd(max(fold["validation"]["rmse_usd"] for fold in shallow["folds"])),
        usd(round(diagnosis["validation_error_profile"]["by_kind_of_month"]["August"]["rmse_usd"], -3)),
        usd(round(valid["mean"], -3)),
    ]
    missing = [value for value in expected if value not in text]
    assert not missing, missing
    ratio = shallow["summary"]["validation"]["rmse_usd"]["mean"] / shallow["summary"]["training"]["rmse_usd"]["mean"]
    assert f"{ratio:.1f} " in text
    assert 1.9 < valid["mean"] / everything["training"]["rmse_usd"]["mean"] < 2.1  # "it misses twice as much on validation"
    assert f"{points[48]['validation_rmse_usd']['mean'] / points[48]['training_rmse_usd']['mean']:.1f} " in text


def test_what_the_report_says_about_stability_is_true(diagnosis, cause):
    everything = diagnosis["cross_validation_all_past"]
    for folds_ in (everything["folds"], cause["candidates"]["shallower_trees"]["folds"]):
        assert [fold["fold"] for fold in folds_ if fold["validation"]["rmse_usd"] > fold["no_model"]["rmse_usd"]] == [1, 6]
    assert [fold["validated_months"] for fold in everything["folds"] if fold["fold"] in (1, 6)] == ["2020-01 to 2020-06", "2022-07 to 2022-12"]
    depths = [fold["params"]["max_depth"] for fold in everything["folds"]]
    assert depths.count(3) == 7 and depths.count(5) == 1
    last = diagnosis["cross_validation_last_24_months"]["summary"]["validation"]["rmse_usd"]
    assert last["mean"] > everything["summary"]["validation"]["rmse_usd"]["mean"] and last["std"] < everything["summary"]["validation"]["rmse_usd"]["std"]
    points = {point["training_months"]: point["validation_rmse_usd"] for point in diagnosis["learning_curve"]}
    assert points[24]["mean"] - points[48]["mean"] < min(points[size]["std"] for size in (24, 30, 36, 42, 48))
    assert (points[12]["mean"] - points[24]["mean"]) > 0.5 * (points[12]["mean"] - points[48]["mean"])  # most of the improvement comes before 24 months


def test_the_corrective_action_names_what_the_code_really_has_today():
    """The action is PROPOSED: the delivered model is untouched, and what the report says must be changed exists."""
    assert {setting["max_depth"] for setting in sm.PARAM_GRID} == {3, 5, None} and len(sm.PARAM_GRID) == 18
    source = (REPOSITORY / "data" / "process" / "sales_model.py").read_text(encoding="utf-8")
    assert "product((3, 5, None), (1, 2, 4), (0.5, 1.0))" in source
    assert "len(sm.PARAM_GRID) == 18" in (REPOSITORY / "tests" / "pipelines" / "test_sales_forecast_model.py").read_text(encoding="utf-8")
    for text in (path.read_text(encoding="utf-8") for path in REPORTS.values()):
        assert "`PARAM_GRID`" in text and "`(3, 5, None)`" in text and "`(2,)`" in text and "scripts/train_sales_forecast.py" in text


def test_with_the_proposed_change_the_training_rows_choose_the_settings_the_report_says(series, report):
    train = sf.add_features(series).dropna(subset=list(sf.FEATURES)).reset_index(drop=True)
    chosen = sm.tune(train, rc.CANDIDATES["shallower_trees"].grid)[0].params
    assert len(train) == 72 and chosen == {"max_depth": 2, "min_samples_leaf": 2, "max_features": 1.0}
    assert "`max_depth=2, min_samples_leaf=2, max_features=1.0`" in report[1]


def test_the_quotes_of_the_report_are_word_for_word_from_the_briefing(report):
    _, text = report
    briefing = (REPOSITORY / "BRIEFING_NEXOVA_SALES.md").read_text(encoding="utf-8").replace("**", "")
    quotes = [quote for quote in re.findall(r"«([^»]+)»", text)]
    assert len(quotes) >= 3
    for quote in quotes:
        assert quote in briefing, quote
    for word in ("Nexova", "revenue_usd", "consolidated", "Laura", "revenue_lag_12", "data/raw/nexova_sales.csv", "RMSE", "MAE", "MSE", "Gini"):
        assert word in text, word


READMES = {"en": EVAL / "regression_eval" / "README.md", "es": EVAL / "regression_eval" / "README.es.md"}


@pytest.fixture(scope="module", params=sorted(READMES))
def readme(request):
    return request.param, READMES[request.param].read_text(encoding="utf-8")


def test_the_readme_opens_with_the_same_verdict_as_the_report_and_its_measured_numbers(readme, diagnosis, cause):
    language, text = readme
    verdict = {"en": "**Diagnosis: moderate overfitting.**", "es": "**Diagnóstico: overfitting moderado.**"}[language]
    summary_part = text.split({"en": "## Files of the project", "es": "## Archivos del proyecto"}[language])[0]
    assert verdict in summary_part
    assert {"en": "**Classification: OVERFITTING (moderate).**", "es": "**Clasificación: OVERFITTING (moderado).**"}[language] in REPORTS[language].read_text(encoding="utf-8")
    everything = diagnosis["cross_validation_all_past"]
    summary = everything["summary"]
    gain = cause["candidates"]["shallower_trees"]["against_current"]["mean_change_usd"]
    for value in (usd(summary["validation"]["rmse_usd"]["mean"]), usd(summary["training"]["rmse_usd"]["mean"]), usd(summary["no_model"]["rmse_usd"]["mean"]),
                  usd(summary["validation"]["rmse_usd"]["min"]), usd(summary["validation"]["rmse_usd"]["max"]), f"{gain:+,.0f}"):
        assert value in summary_part, value
    lost = sum(fold["validation"]["rmse_usd"] > fold["no_model"]["rmse_usd"] for fold in everything["folds"])
    assert {"en": f"in {lost} of 8", "es": f"en {lost} de 8"}[language] in summary_part
    assert {"en": "**Proposed, not applied.**", "es": "**Propuesta, no aplicada.**"}[language] in summary_part


def test_every_link_of_the_readme_exists_and_it_shows_the_learning_curve(readme):
    language, text = readme
    folder = READMES[language].parent
    links = re.findall(r"\]\((\.[^)#]+)\)", text)
    assert links and all((folder / link).resolve().exists() for link in links), [link for link in links if not (folder / link).resolve().exists()]
    picture = {"en": "../learning_curve.png", "es": "../learning_curve.es.png"}[language]
    assert re.search(r"!\[[^\]]+\]\(" + re.escape(picture) + r"\)", text)


def test_the_readme_lists_the_files_of_the_project_and_how_to_run_each_test(readme):
    _, text = readme
    for name in ("sales_diagnosis.py", "sales_root_cause.py", "sales_diagnosis_plot.py", "evaluate_sales_model.py", "sales-cv-chronological-order.yml"):
        assert f"[`{name}`]" in text, name
    commands = "\n".join(re.findall(r"```bash\n(.*?)```", text, flags=re.S))
    for path in ("scripts/evaluate_sales_model.py", "tests/pipelines/test_sales_cv_chronological_order.py", "tests/pipelines/test_sales_diagnosis.py",
                 "tests/pipelines/test_sales_evaluation_report.py"):
        assert path in commands and (REPOSITORY / path).is_file(), path


def load_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("evaluate_for_cause", REPOSITORY / "scripts" / "evaluate_sales_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_prints_the_analysis_with_every_candidate_and_its_verdict(cause):
    printed = load_script().describe_root_cause(cause)
    for name in cause["candidates"]:
        assert name in printed
    assert printed.count("REJECTED") == 2 and printed.count("ACCEPTED") == 1
    assert "11 before" in printed and "13 before" in printed
