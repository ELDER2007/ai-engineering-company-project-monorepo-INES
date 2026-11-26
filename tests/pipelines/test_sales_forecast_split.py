"""THE UNIT TESTS OF THE SPLIT (deliverable of ``BRIEFING_NEXOVA_SALES.md``): the 8 / 2 years rule, and NO DATA LEAKAGE between training and test.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_split.py

Part 1, the rule: the first 8 years (2016-2023, 96 months) train, the 2 most recent (2024-2025, 24 months) test, split by time.

Part 2, no leakage. Information of the test years could reach the training through several doors, and each one has its test:

    a) the rows         a month in both sets, or a training month later than a test month
    b) the features     a feature that uses its own month or a later one, or a number computed over the whole series
    c) the columns      ``active_contracts`` and ``avg_contract_value_usd``: multiplied together they are the revenue of the same month
    d) the empty values a gap filled with a later month
    e) the scaler       a mean or a deviation computed with the test years (checked on the scaler INSIDE the trained model)
    f) the model        the choice of its settings, or its training, depending on the test years
    g) all of it        from the file to the trained model, with the test years replaced by anything: everything learnt must be identical

The strongest checks do not read the code: they CHANGE the test years and require that nothing learnt in training changes.

What is allowed, and is not leakage: a TEST month is forecast knowing the real months before it, test months included. That is information of ITS past
(a forecast one month ahead). It never reaches the training. The forecast of 24 months at once, which uses none of it, is tested in
``test_sales_forecast_metrics.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from data.process import sales_forecast as sf  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SETTINGS = ({"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}, {"max_depth": 5, "min_samples_leaf": 4, "max_features": 0.5})
FIRST_TEST_MONTH = pd.Timestamp("2024-01-01")


@pytest.fixture(scope="module")
def sales():
    return sf.load_sales()  # the dataset given with the project


def other_test_years(sales, factor=3.0):
    """The same series with 2024 and 2025 replaced by something else. 2016-2023 are untouched."""
    changed = sales.copy()
    later = changed["month"] >= FIRST_TEST_MONTH
    changed.loc[later, "revenue_usd"] = changed.loc[later, "revenue_usd"] * factor + 12_345
    return changed


def assert_eight_and_two_years(train, test):
    """The rule, in one place: the real split must pass it and a wrong split must not."""
    assert (len(train), len(test)) == (96, 24), f"96 months to train and 24 to test, not {len(train)} and {len(test)}"
    assert sorted(train["month"].dt.year.unique()) == list(range(2016, 2024)), "the training years are the first 8: 2016 to 2023"
    assert sorted(test["month"].dt.year.unique()) == [2024, 2025], "the test years are the 2 most recent: 2024 and 2025"
    assert train["month"].max() < test["month"].min(), "every training month is before every test month"
    assert not set(train["month"]) & set(test["month"]), "no month is in both"


# ================================================================ 1. the rule: 8 years to train, 2 to test


def test_the_split_respects_the_rule_of_8_years_to_train_and_2_to_test(sales):
    train, test = sf.split_train_test(sales)
    assert_eight_and_two_years(train, test)
    assert (train["month"].min(), train["month"].max()) == (pd.Timestamp("2016-01-01"), pd.Timestamp("2023-12-01"))
    assert (test["month"].min(), test["month"].max()) == (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-01"))
    assert sorted([*train["month"], *test["month"]]) == sorted(sales["month"])  # and no month is lost


def test_the_split_is_by_time_even_if_the_rows_arrive_out_of_order(sales):
    train, test = sf.split_train_test(sales.sample(frac=1, random_state=7))
    expected_train, expected_test = sf.split_train_test(sales)
    pd.testing.assert_frame_equal(train, expected_train)
    pd.testing.assert_frame_equal(test, expected_test)


@pytest.mark.parametrize("test_years", [0, -1, 10, 11])
def test_a_split_that_leaves_nothing_to_train_or_to_test_is_refused(sales, test_years):
    with pytest.raises(ValueError):
        sf.split_train_test(sales, test_years)


@pytest.mark.parametrize("wrong", ["at random", "one month early", "one month late", "three years to test"])
def test_the_check_of_the_rule_rejects_wrong_splits(sales, wrong):
    """The guard is not empty: each of these splits has to fail it."""
    if wrong == "at random":
        test = sales.sample(24, random_state=1)
        train = sales.drop(test.index)
    else:
        cut = {"one month early": 95, "one month late": 97, "three years to test": 84}[wrong]
        train, test = sales.iloc[:cut], sales.iloc[cut:]
    with pytest.raises(AssertionError):
        assert_eight_and_two_years(train, test)


def test_the_rows_given_to_the_model_keep_the_rule(sales):
    """With the features, the first 24 months have not enough past: they leave the TRAINING. The 24 test months are all there."""
    train, test = sf.build_model_frames(sales)
    assert len(test) == 24 and (test["month"].min(), test["month"].max()) == (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-01"))
    assert len(train) == 72 and (train["month"].min(), train["month"].max()) == (pd.Timestamp("2018-01-01"), pd.Timestamp("2023-12-01"))
    assert not set(train["month"]) & set(test["month"])


# ================================================================ 2. no data leakage between training and test


# ---------------- a) and b): rows and features


def test_nothing_that_happens_in_the_test_years_changes_the_training_rows(sales):
    """Rows, features and target of training: identical whatever 2024 and 2025 turn out to be. A number computed over the whole series would show here."""
    pd.testing.assert_frame_equal(sf.build_model_frames(sales)[0], sf.build_model_frames(other_test_years(sales))[0])


@pytest.mark.parametrize("position", [24, 50, 95, 96, 119])
def test_no_feature_uses_its_own_month_or_a_later_one(sales, position):
    """Change a month and everything after it: no feature up to that month may move (this includes the first test month, row 96)."""
    changed = sales.copy()
    changed.loc[position:, "revenue_usd"] = changed.loc[position:, "revenue_usd"] * 10 + 12_345
    pd.testing.assert_frame_equal(sf.add_features(sales).loc[:position, list(sf.FEATURES)], sf.add_features(changed).loc[:position, list(sf.FEATURES)])


def test_that_check_would_catch_a_feature_that_includes_its_own_month(sales):
    changed = sales.copy()
    changed.loc[50:, "revenue_usd"] *= 10
    leaky = lambda frame: frame["revenue_usd"].rolling(3).mean()  # noqa: E731  (the window includes the month itself)
    assert leaky(sales).loc[50] != leaky(changed).loc[50]


# ---------------- c) the columns that give the answer away


def test_the_target_and_the_two_columns_that_reveal_it_are_not_features(sales):
    product = sales["active_contracts"] * sales["avg_contract_value_usd"]
    assert ((product - sales["revenue_usd"]).abs() / sales["revenue_usd"]).max() < 0.01  # together they ARE the revenue of the month
    assert sf.TARGET not in sf.FEATURES and not any("contract" in feature for feature in sf.FEATURES)
    changed = sales.assign(active_contracts=1, avg_contract_value_usd=1.0)
    pd.testing.assert_frame_equal(sf.add_features(sales)[list(sf.FEATURES)], sf.add_features(changed)[list(sf.FEATURES)])


# ---------------- d) the empty values


def test_a_gap_in_the_last_training_months_is_never_filled_from_the_test_years(sales, tmp_path):
    """December 2023 is empty: the months next to it AFTER are test months. Interpolating or filling backwards would put them into the training."""

    def with_the_gap(frame):
        text = frame.assign(month=frame["month"].dt.strftime("%Y-%m-%d")).astype(str)
        text.loc[95, ["revenue_usd", "active_contracts"]] = ""
        path = tmp_path / "gap.csv"
        text.to_csv(path, index=False)
        return sf.load_sales_with_report(path)

    clean, report = with_the_gap(sales)
    again, _ = with_the_gap(other_test_years(sales))
    assert {item["month"] for item in report} == {"2023-12"}
    assert clean.loc[95, "revenue_usd"] == sales.loc[83, "revenue_usd"]  # December of the year before
    pd.testing.assert_frame_equal(clean.loc[:95], again.loc[:95])


# ---------------- e) the scaler and f) the model


@pytest.fixture(scope="module")
def model_module():
    pytest.importorskip("sklearn")
    from data.process import sales_model

    return sales_model


def standard_scaler_of(forecaster):
    return forecaster.pipeline.named_steps["scale"].named_transformers_["standard"]


def test_the_scaler_inside_the_trained_model_learnt_from_the_training_rows_only(sales, model_module):
    train, test = sf.build_model_frames(sales)
    scaler = standard_scaler_of(model_module.train_forecaster(train, SETTINGS[0]))
    columns = list(sf.SCALED_FEATURES)
    assert scaler.n_samples_seen_ == len(train) == 72
    np.testing.assert_allclose(scaler.mean_, train[columns].mean().to_numpy())
    np.testing.assert_allclose(scaler.scale_, train[columns].std(ddof=0).to_numpy())
    leaky_mean = pd.concat([train, test])[columns].mean().to_numpy()  # what it would have learnt with the test years in
    assert not np.allclose(scaler.mean_, leaky_mean)


def test_in_the_validation_too_each_scaler_only_sees_the_months_before_the_year_it_is_asked_about(sales, model_module):
    train, _ = sf.build_model_frames(sales)
    for year, past, current in model_module.time_folds(train):
        assert past["month"].max() < current["month"].min()
        pipeline = model_module.make_pipeline(model_module.random_forest(SETTINGS[0])).fit(past[list(sf.FEATURES)], model_module.to_ratio(past))
        scaler = pipeline.named_steps["scale"].named_transformers_["standard"]
        np.testing.assert_allclose(scaler.mean_, past[list(sf.SCALED_FEATURES)].mean().to_numpy())


def test_the_test_years_cannot_change_the_choice_of_settings_or_the_model(sales, model_module):
    train, test = sf.build_model_frames(sales)
    other_train = sf.build_model_frames(other_test_years(sales, factor=7.0))[0]
    mine, theirs = model_module.tune(train, SETTINGS), model_module.tune(other_train, SETTINGS)
    assert [(r.params, r.rmse) for r in mine] == [(r.params, r.rmse) for r in theirs]
    first = model_module.train_forecaster(train, mine[0].params).predict(test)
    second = model_module.train_forecaster(other_train, theirs[0].params).predict(test)
    np.testing.assert_array_equal(first, second)


# ---------------- g) from the file to the trained model


def test_end_to_end_with_any_test_years_everything_learnt_in_training_is_identical(sales, model_module, tmp_path):
    """The path of the training script: read the file, prepare, choose, train. The second file has OTHER 2024 and 2025."""
    spec = importlib.util.spec_from_file_location("train_sales_forecast_under_test", REPO / "scripts" / "train_sales_forecast.py")
    script = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = script  # the dataclass of the script looks its module up
    spec.loader.exec_module(script)

    def learn(frame, name):
        path = tmp_path / name
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        prepared = script.prepare(path)
        chosen = model_module.tune(prepared.train, SETTINGS)[0]
        return prepared, chosen, model_module.train_forecaster(prepared.train, chosen.params)

    real, real_choice, real_model = learn(sales, "real.csv")
    other, other_choice, other_model = learn(other_test_years(sales, factor=0.4), "other.csv")
    assert not np.allclose(real.test["revenue_usd"], other.test["revenue_usd"])  # the two files really differ in the test years
    pd.testing.assert_frame_equal(real.train, other.train)
    assert (real_choice.params, real_choice.rmse) == (other_choice.params, other_choice.rmse)
    np.testing.assert_array_equal(standard_scaler_of(real_model).mean_, standard_scaler_of(other_model).mean_)
    np.testing.assert_array_equal(standard_scaler_of(real_model).scale_, standard_scaler_of(other_model).scale_)
    pd.testing.assert_series_equal(real_model.feature_importances(), other_model.feature_importances())
    np.testing.assert_array_equal(real_model.predict(real.test), other_model.predict(real.test))  # asked the same, they answer the same
