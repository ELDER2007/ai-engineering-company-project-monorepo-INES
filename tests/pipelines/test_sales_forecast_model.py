"""The model of the sales forecast (``data/process/sales_model.py``): a scikit-learn regression, chosen without the test years, with its reasons written down.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_model.py
"""

from __future__ import annotations

import re

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from sklearn.base import is_regressor  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402

from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_model as sm  # noqa: E402

SMALL_GRID = ({"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}, {"max_depth": 5, "min_samples_leaf": 4, "max_features": 0.5})
CHOSEN = SMALL_GRID[0]


@pytest.fixture(scope="module")
def sales():
    return sf.load_sales()


@pytest.fixture(scope="module")
def frames(sales):
    return sf.build_model_frames(sales)


@pytest.fixture(scope="module")
def forecaster(frames):
    return sm.train_forecaster(frames[0], CHOSEN)


# ---------------------------------------------------------------- a scikit-learn regression, Random Forest


def test_the_model_is_a_random_forest_regressor_of_scikit_learn_behind_the_scaler(forecaster):
    assert list(forecaster.pipeline.named_steps) == ["scale", "model"]
    model = forecaster.pipeline.named_steps["model"]
    assert type(model) is RandomForestRegressor and is_regressor(model)
    assert model.random_state == 42 and len(model.estimators_) == 300


def test_the_same_data_and_settings_give_the_same_forecast(frames, forecaster):
    again = sm.train_forecaster(frames[0], CHOSEN)
    np.testing.assert_array_equal(forecaster.predict(frames[1]), again.predict(frames[1]))


def test_it_gives_one_positive_amount_in_dollars_for_every_month(frames, forecaster):
    forecast = forecaster.predict(frames[1])
    assert forecast.shape == (24,) and np.isfinite(forecast).all() and (forecast > 0).all()


def test_the_forecast_is_the_ratio_times_the_revenue_of_a_year_before(frames, forecaster):
    test = frames[1]
    ratio = forecaster.pipeline.predict(test[list(sf.FEATURES)])
    np.testing.assert_allclose(forecaster.predict(test), ratio * test["revenue_lag_12"].to_numpy())
    np.testing.assert_allclose(sm.to_ratio(frames[0]) * frames[0]["revenue_lag_12"], frames[0]["revenue_usd"])


def test_it_can_forecast_above_everything_it_saw_which_a_tree_on_dollars_cannot(sales, frames, forecaster):
    """January and February 2025 are above every training month. A tree answers an average of training targets: with dollars as target it would be capped."""
    train, test = frames
    ceiling = sales.loc[sales["month"] < "2024-01-01", "revenue_usd"].max()
    assert (test["revenue_usd"] > ceiling).sum() == 2
    on_dollars = RandomForestRegressor(random_state=42, n_estimators=50).fit(train[list(sf.FEATURES)], train["revenue_usd"])
    assert on_dollars.predict(test[list(sf.FEATURES)]).max() <= ceiling
    richer = test.assign(revenue_lag_12=test["revenue_lag_12"] * 2)  # a year that starts twice as high
    assert forecaster.predict(richer).max() > ceiling


# ---------------------------------------------------------------- the choice is made without the test years


def test_every_validated_year_is_forecast_by_a_model_that_only_saw_earlier_months(frames):
    folds = list(sm.time_folds(frames[0]))
    assert [year for year, _, _ in folds] == [2020, 2021, 2022, 2023]
    for year, past, current in folds:
        assert past["month"].max() < current["month"].min() and set(current["month"].dt.year) == {year} and len(current) == 12
    assert len(folds[0][1]) == 24  # even the first one has two years to learn from


def test_the_tuning_returns_the_best_setting_first(frames):
    results = sm.tune(frames[0], SMALL_GRID)
    assert [r.rmse for r in results] == sorted(r.rmse for r in results)
    assert len(sm.PARAM_GRID) == 18 and CHOSEN in sm.PARAM_GRID


def test_too_few_years_to_validate_are_refused(frames):
    with pytest.raises(ValueError, match="validation years"):
        list(sm.time_folds(frames[0][frames[0]["month"] < "2021-01-01"]))


# ---------------------------------------------------------------- explainability


def test_the_weight_of_every_feature_is_known_and_the_growth_of_a_year_ago_weighs_most(forecaster):
    weights = forecaster.feature_importances()
    assert sorted(weights.index) == sorted(sf.FEATURES) and weights.sum() == pytest.approx(1)
    assert weights.index[0] == "yoy_growth_lag_12"  # the turn of fast and slow years that the briefing describes
    assert weights.is_monotonic_decreasing


# ---------------------------------------------------------------- the reasons are written in the code, and they are true


@pytest.fixture(scope="module")
def comparison(frames):
    pytest.importorskip("xgboost")
    return sm.compare_algorithms(frames[0])


def test_the_code_documents_the_three_criteria_of_the_brief():
    text = sm.__doc__
    assert "WHY RANDOM FOREST AND NOT XGBOOST" in text
    for criterion in ("Data size", "Explainability", "Time available for tuning"):
        assert f"**{criterion}.**" in text
    assert "IN ACCURACY THE TWO ARE TIED" in text and "In fairness to XGBoost: it trains FASTER" in text  # what speaks for the other one is said too


def _stated(label: str) -> tuple[float, float]:
    """The ``RMSE ... USD   ... %`` that the documentation states for ``label``."""
    line = next(line for line in sm.__doc__.splitlines() if line.strip().startswith(label) and "RMSE" in line)
    rmse, mape = re.search(r"RMSE ([\d ]+?) USD\s+([\d.]+) %", line).groups()
    return float(rmse.replace(" ", "")), float(mape)


@pytest.mark.parametrize("label, name", [("Random Forest ", "Random Forest"), ("XGBoost ", "XGBoost"), ("(no model)", "same month a year before (no model)")])
def test_the_numbers_written_in_the_code_are_the_ones_the_comparison_gives(comparison, label, name):
    rmse, mape = _stated(label)
    assert comparison[name].rmse == pytest.approx(rmse, rel=0.02) and comparison[name].mape == pytest.approx(mape, abs=0.1)


def test_what_the_code_says_about_the_years_is_true(comparison):
    forest, boost = comparison["Random Forest"].rmse_by_year, comparison["XGBoost"].rmse_by_year
    assert [year for year in forest if boost[year] < forest[year]] == [2020, 2021, 2023]  # "XGBoost is better in THREE of the four"
    assert np.std(list(forest.values())) < np.std(list(boost.values()))  # "the forest varies less from one year to another"


def test_in_the_time_validation_the_model_is_better_than_using_no_model(comparison):
    assert comparison["Random Forest"].rmse < comparison["same month a year before (no model)"].rmse * 0.85


# ---------------------------------------------------------------- features and forecast against the patterns of the briefing (sections 4 and 6)
# The data itself is checked in test_sales_forecast_data.py and the calendar flags too. Here: the growth feature, and what the model makes of it all.
# This only CHECKS the frozen model: nothing was chosen or tuned with it.


def test_the_growth_feature_follows_the_alternation_of_fast_and_slow_years(sales):
    """``yoy_growth_lag_12`` is how much the same month grew a year ago. Since fast (about 7 %) and slow (about 1 %) years take turns, it is high in
    the even years (after a fast one) and low in the odd years (after a slow one): that is what lets the model tell which kind of year it is in."""
    featured = sf.add_features(sales).dropna(subset=["yoy_growth_lag_12"])
    by_year = featured.groupby(featured["month"].dt.year)["yoy_growth_lag_12"].mean()
    assert (by_year[[2018, 2020, 2022, 2024]] > 0.05).all()
    assert (by_year[[2019, 2021, 2023, 2025]] < 0.035).all()


def test_the_forecast_reproduces_the_seasonality_and_the_growth_of_the_briefing(sales, frames, forecaster):
    test = frames[1].assign(forecast=forecaster.predict(frames[1]))
    year, month = test["month"].dt.year, test["month"].dt.month
    normal = test[~month.isin((1, 2, 8))].groupby(year)["forecast"].mean()
    ratio = test["forecast"] / year.map(normal) - 1
    assert ratio[month == 8].between(-0.25, -0.15).all()  # August: 15 to 25 % below the normal months
    assert ratio[month.isin((1, 2))].between(0.14, 0.21).all()  # January and February: about 15 to 20 % above (the tolerance the data needs too)
    totals = test.groupby(year)["forecast"].sum()
    before = sales.loc[sales["month"].dt.year == 2023, "revenue_usd"].sum()
    first = totals[2024] / before - 1
    second = totals[2025] / sales.loc[sales["month"].dt.year == 2024, "revenue_usd"].sum() - 1
    assert 0 < first < second  # it keeps growing, and it sees that 2024 is a slow year and 2025 a fast one
