"""The metrics of the sales forecast (MSE, PSI, Gini, K² Score), the evaluation on the test years, and what the README says about both.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_metrics.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
stats = pytest.importorskip("scipy.stats")

from data.process import sales_evaluation as ev  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_metrics as m  # noqa: E402
from data.process import sales_model as sm  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FOLDER = REPO / "data" / "eval" / "sales_forecast"
READMES = ("README.md", "README.es.md")


# ---------------------------------------------------------------- MSE and its readable forms


def test_the_mse_is_the_mean_of_the_squared_errors_and_its_percentage_uses_its_root():
    actual, forecast = [100.0, 200.0, 300.0], [110.0, 180.0, 300.0]
    assert m.mse(actual, forecast) == pytest.approx((100 + 400 + 0) / 3)
    assert m.rmse_percent_of_mean(actual, forecast) == pytest.approx(np.sqrt(500 / 3) / 200 * 100)
    assert m.mape(actual, forecast) == pytest.approx((10 + 10 + 0) / 3)
    assert m.bias_percent(actual, forecast) == pytest.approx((10 - 10 + 0) / 3)


@pytest.mark.parametrize("actual, forecast", [([1, 2], [1]), ([], []), ([1, float("nan")], [1, 2]), ([1, 2], [1, float("inf")])])
def test_series_that_cannot_be_compared_are_refused(actual, forecast):
    with pytest.raises(ValueError):
        m.mse(actual, forecast)


# ---------------------------------------------------------------- Gini


def test_the_gini_is_one_for_the_right_order_and_negative_for_the_opposite_one():
    actual = np.array([5.0, 9.0, 7.0, 12.0, 6.0])
    assert m.normalized_gini(actual, actual) == pytest.approx(1)
    assert m.normalized_gini(actual, -actual) == pytest.approx(-1)
    assert m.normalized_gini(actual, actual * 10 + 3) == pytest.approx(1)  # only the order counts


def test_a_forecast_that_says_the_same_for_every_month_orders_nothing():
    assert m.normalized_gini([5.0, 9.0, 7.0], [1.0, 1.0, 1.0]) == pytest.approx(0)


def test_the_gini_does_not_depend_on_the_order_of_the_rows():
    actual, forecast = np.array([5.0, 9.0, 7.0, 12.0, 6.0]), np.array([1.0, 2.0, 2.0, 3.0, 1.0])  # with ties
    shuffled = [3, 0, 4, 2, 1]
    assert m.normalized_gini(actual, forecast) == pytest.approx(m.normalized_gini(actual[shuffled], forecast[shuffled]))


def test_the_gini_needs_a_positive_target_that_varies():
    with pytest.raises(ValueError):
        m.normalized_gini([0.0, 1.0], [0.0, 1.0])
    with pytest.raises(ValueError):
        m.normalized_gini([5.0, 5.0], [1.0, 2.0])


# ---------------------------------------------------------------- PSI


def test_the_psi_is_zero_for_the_same_distribution_and_large_for_one_that_moved():
    reference = np.arange(100.0)
    assert m.psi(reference, reference) == pytest.approx(0, abs=1e-9)
    assert m.psi(reference, reference + 1000) > m.PSI_SIGNIFICANT


def test_the_psi_of_a_small_case_by_hand():
    reference = np.arange(1.0, 11.0)  # 5 bins, two values each
    current = np.array([9.0, 9.5, 10.0, 10.5])  # all in the top bin
    expected = np.full(5, 2.5 / 12.5)
    actual = (np.array([0, 0, 0, 0, 4]) + 0.5) / 6.5
    assert m.psi(reference, current) == pytest.approx(float(np.sum((actual - expected) * np.log(actual / expected))))


def test_values_outside_the_range_of_the_reference_are_counted_in_the_end_bins():
    reference = np.arange(100.0)
    assert m.psi(reference, [-50.0] * 10) > 1 and np.isfinite(m.psi(reference, [10_000.0] * 10))


def test_with_samples_this_small_chance_alone_reaches_the_noise_level_and_often_passes_the_usual_threshold():
    """The claim of the README, checked by simulation: two samples of the SAME distribution, with 72 and 24 values."""
    rng = np.random.default_rng(42)
    values = np.array([m.psi(rng.normal(size=72), rng.normal(size=24)) for _ in range(4000)])
    assert np.quantile(values, 0.95) == pytest.approx(m.psi_noise_level(72, 24), rel=0.08)
    assert 0.23 < (values > m.PSI_SIGNIFICANT).mean() < 0.33  # "about 28 %": a false "large change" more than one time in four


# ---------------------------------------------------------------- K² Score


def test_the_k2_score_is_the_dagostino_pearson_test_of_the_errors():
    rng = np.random.default_rng(1)
    actual, forecast = rng.normal(100, 5, 40), np.full(40, 100.0)
    reference = stats.normaltest(actual - forecast)
    assert m.k2_score(actual, forecast) == pytest.approx((reference.statistic, reference.pvalue))


def test_the_k2_score_notices_lopsided_errors():
    rng = np.random.default_rng(2)
    base = np.full(200, 1000.0)
    assert m.k2_score(base + rng.normal(0, 5, 200), base)[1] > 0.05
    assert m.k2_score(base + rng.lognormal(2, 1, 200), base)[1] < 0.001


def test_the_k2_test_needs_twenty_errors():
    with pytest.raises(ValueError, match="20"):
        m.k2_score(np.arange(1.0, 20.0), np.arange(1.0, 20.0))


# ---------------------------------------------------------------- why a low MSE is not enough: the claims of the README, shown


def test_the_same_mse_can_hide_a_forecast_that_always_falls_short():
    rng = np.random.default_rng(3)
    actual = rng.uniform(800, 1100, 24)
    always_short, both_ways = actual - 30, actual + np.where(np.arange(24) % 2 == 0, 30, -30)
    assert m.mse(actual, always_short) == pytest.approx(m.mse(actual, both_ways))
    assert m.bias_percent(actual, always_short) < -2.5 and abs(m.bias_percent(actual, both_ways)) < 0.5


def test_the_k2_score_cannot_see_the_bias():
    rng = np.random.default_rng(4)
    actual = rng.normal(1000, 20, 60)
    forecast = np.full(60, 1000.0)
    assert m.k2_score(actual, forecast) == pytest.approx(m.k2_score(actual, forecast - 500))


def test_a_worse_mse_can_order_the_months_better():
    actual = np.array([800.0, 900.0, 910.0, 1000.0])
    scaled = actual * 0.9  # always 10 % short: the order is perfect
    flat_but_close = np.array([905.0, 900.0, 899.0, 902.0])  # near the middle, the weak month and the strong one in the wrong places
    assert m.mse(actual, flat_but_close) < m.mse(actual, scaled)
    assert m.normalized_gini(actual, scaled) == pytest.approx(1)
    assert m.normalized_gini(actual, flat_but_close) < 0.9


# ---------------------------------------------------------------- the evaluation of the model on the test years


@pytest.fixture(scope="module")
def evaluated():
    sales = sf.load_sales()
    train, test = sf.build_model_frames(sales)
    forecaster = sm.train_forecaster(train, sm.tune(train)[0].params)
    before = forecaster.predict(test)
    report = ev.evaluate(sales, train, test, forecaster)
    return sales, train, test, forecaster, before, report


def test_the_four_metrics_of_the_brief_are_reported_on_the_24_test_months(evaluated):
    _, _, test, forecaster, _, report = evaluated
    model = report["model"]
    assert model["months"] == 24 and report["test_months"] == "2024-01 to 2025-12"
    actual, forecast = test["revenue_usd"].to_numpy(), forecaster.predict(test)
    assert model["mse_usd2"] == pytest.approx(m.mse(actual, forecast))
    assert model["gini"] == pytest.approx(m.normalized_gini(actual, forecast))
    assert (model["k2_statistic"], model["k2_p_value"]) == pytest.approx(m.k2_score(actual, forecast))
    assert set(report["psi"]["values"]) == {"revenue_usd", "ratio_to_a_year_before", "forecast_usd"}
    assert "CANNOT be measured" in report["psi"]["business_line_mix"]


def test_evaluating_does_not_change_the_model(evaluated):
    _, _, test, forecaster, before, _ = evaluated
    np.testing.assert_array_equal(forecaster.predict(test), before)


def test_on_the_test_years_the_model_beats_the_rule_without_a_model(evaluated):
    report = evaluated[-1]
    model, rival = report["model"], report[ev.NO_MODEL]
    assert model["mse_usd2"] < rival["mse_usd2"] / 2 and model["gini"] > rival["gini"] and abs(model["bias_percent"]) < abs(rival["bias_percent"])


def test_forecasting_24_months_ahead_uses_no_real_value_after_2023(evaluated):
    sales, _, test, forecaster, before, _ = evaluated
    history = sales[sales["month"] < "2024-01-01"]
    first = ev.forecast_ahead(forecaster, history, 24)
    changed = sales.copy()
    changed.loc[96:, "revenue_usd"] *= 9
    again = ev.forecast_ahead(forecaster, changed[changed["month"] < "2024-01-01"], 24)
    pd.testing.assert_series_equal(first, again)
    assert list(first.index) == list(test["month"])
    assert first.iloc[0] == pytest.approx(before[0])  # the first month has the same past in both ways of forecasting
    assert not np.allclose(first.to_numpy()[1:], before[1:])  # afterwards it feeds on its own forecasts


# ---------------------------------------------------------------- the file of numbers and the README say what the code says


def _close(saved, computed, path="report"):
    if isinstance(computed, dict):
        assert set(saved) == set(computed), path
        for key in computed:
            _close(saved[key], computed[key], f"{path}.{key}")
    elif isinstance(computed, list):
        assert len(saved) == len(computed), path
        for index, (mine, theirs) in enumerate(zip(saved, computed)):
            _close(mine, theirs, f"{path}[{index}]")
    elif isinstance(computed, float):
        assert saved == pytest.approx(computed, rel=1e-6, abs=1e-9), path
    else:
        assert saved == computed, path


def test_the_metrics_file_of_the_repository_is_what_the_code_computes(evaluated):
    _close(json.loads((FOLDER / "metrics.json").read_text(encoding="utf-8")), evaluated[-1])


@pytest.mark.parametrize("name", READMES)
def test_every_number_of_the_tables_of_the_readme_is_the_computed_one(evaluated, name):
    report, text = evaluated[-1], (FOLDER / name).read_text(encoding="utf-8")
    columns = (report["model"], report[ev.NO_MODEL], report["model_24_months_ahead"])
    expected_rows = [
        [f"{c['mse_usd2']:,.0f}" for c in columns],
        [f"{c['rmse_usd']:,.0f}" for c in columns],
        [f"{c['rmse_percent_of_mean_revenue']:.2f} %" for c in columns],
        [f"{c['gini']:.3f}" for c in columns],
        [f"{c['k2_statistic']:.2f} ({c['k2_p_value']:.2f})" for c in columns],
        [f"{c['mape_percent']:.2f} %" for c in columns],
        [f"{c['bias_percent']:+.2f} %" for c in columns],
        [f"{c['r_squared']:.3f}" for c in columns],
    ]
    for cells in expected_rows:
        assert " | ".join(cells) + " |" in text, cells
    for item in report["psi"]["values"].values():
        assert f"| {item['psi']:.3f} |" in text
    assert f"| {report['psi']['noise_level_95']:.3f} |" in text
    august = report["model_by_kind_of_month"]["August"]
    assert f"{august['mape_percent']:.1f} %" in text and august["bias_percent"] == pytest.approx(-august["mape_percent"])  # "falling short both times"


@pytest.mark.parametrize("name, headings", [
    ("README.md", ("## What each metric measures", "## Why a low MSE is not enough on its own")),
    ("README.es.md", ("## Qué mide cada métrica", "## Por qué un MSE bajo no basta por sí solo")),
])
def test_the_readme_explains_every_metric_and_why_a_low_mse_is_not_enough(name, headings):
    text = (FOLDER / name).read_text(encoding="utf-8")
    for heading in headings:
        assert heading in text
    meaning = text.split(headings[0])[1].split(headings[1])[0]
    for metric in ("**MSE", "**PSI", "**Gini", "**K² Score"):
        assert metric in meaning
    assert len([line for line in text.split(headings[1])[1].splitlines() if line[:2] in ("1.", "2.", "3.", "4.", "5.", "6.")]) == 6
