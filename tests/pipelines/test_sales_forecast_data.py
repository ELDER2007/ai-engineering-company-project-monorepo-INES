"""The data of the sales forecast (``data/process/sales_forecast.py``): the rules of the dataset, the empty values, the features and the scaling.

The 8/2 years split and the absence of leakage between training and test are in ``test_sales_forecast_split.py``.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_data.py
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from data.process import sales_forecast as sf  # noqa: E402


@pytest.fixture(scope="module")
def sales() -> pd.DataFrame:
    return sf.load_sales()  # the dataset given with the project, not a made-up one


# ---------------------------------------------------------------- the dataset and its rules (briefing, sections 2 and 5)


def test_the_given_dataset_is_the_consolidated_series_of_120_months_and_positive(sales):
    assert list(sales.columns) == list(sf.COLUMNS)
    assert len(sales) == 120 and set(sales["business_line"]) == {"consolidated"}
    assert sales["month"].is_monotonic_increasing and (sales["revenue_usd"] > 0).all()


def test_only_the_consolidated_rows_are_used(tmp_path, sales):
    other = sales.assign(business_line="training", revenue_usd=1.0, month=sales["month"].dt.strftime("%Y-%m-%d"))
    mine = sales.assign(month=sales["month"].dt.strftime("%Y-%m-%d"))
    pd.concat([mine, other]).to_csv(tmp_path / "both.csv", index=False)
    pd.testing.assert_frame_equal(sf.load_sales(tmp_path / "both.csv"), sales)


def _broken(sales, how):
    frame = sales.copy()
    if how == "missing month":
        return frame.drop(index=40)
    if how == "repeated month":
        return pd.concat([frame, frame.iloc[[40]]])
    if how == "zero revenue":
        frame.loc[40, "revenue_usd"] = 0
    if how == "negative revenue":
        frame.loc[40, "revenue_usd"] = -5
    if how == "empty cell":
        frame.loc[40, "active_contracts"] = None
    if how == "not the first day":
        frame.loc[40, "month"] = frame.loc[40, "month"] + pd.Timedelta(days=3)
    if how == "missing column":
        return frame.drop(columns="active_contracts")
    return frame


@pytest.mark.parametrize("how", ["missing month", "repeated month", "zero revenue", "negative revenue", "empty cell", "not the first day", "missing column"])
def test_a_dataset_that_breaks_a_rule_is_refused(sales, how):
    with pytest.raises(sf.DatasetError):
        sf.validate_sales(_broken(sales, how))


def test_the_lags_and_rolling_statistics_are_the_past_months(sales):
    featured = sf.add_features(sales)
    row, revenue = 40, sales["revenue_usd"]
    assert featured.loc[row, "revenue_lag_1"] == revenue[39] and featured.loc[row, "revenue_lag_12"] == revenue[28]
    assert featured.loc[row, "revenue_roll_mean_3"] == pytest.approx(revenue[37:40].mean())
    assert featured.loc[row, "revenue_roll_std_12"] == pytest.approx(revenue[28:40].std())
    assert featured.loc[row, "yoy_growth_lag_1"] == pytest.approx(revenue[39] / revenue[27] - 1)
    assert featured.loc[row, "yoy_growth_lag_12"] == pytest.approx(revenue[28] / revenue[16] - 1)


def test_the_calendar_features_mark_the_months_of_the_briefing(sales):
    featured = sf.add_features(sales)
    assert set(featured.loc[featured["is_august"] == 1, "month"].dt.month) == {8}
    assert set(featured.loc[featured["is_january_or_february"] == 1, "month"].dt.month) == {1, 2}
    assert featured["months_since_start"].tolist() == list(range(120))


def test_the_model_frames_keep_the_whole_test_and_drop_only_the_start_of_training(sales):
    train, test = sf.build_model_frames(sales)
    assert len(test) == 24 and test["month"].min() == pd.Timestamp("2024-01-01")
    assert train["month"].min() == pd.Timestamp("2018-01-01") and train["month"].max() == pd.Timestamp("2023-12-01")  # 24 months of past are needed
    assert len(train) == 96 - 24
    assert not train[list(sf.FEATURES)].isna().any().any() and not test[list(sf.FEATURES)].isna().any().any()


# ---------------------------------------------------------------- the patterns the briefing says the data has (section 4)


def test_the_data_shows_the_seasonality_of_the_briefing(sales):
    """August 15-25 % below, January and February 15-20 % above. The "average" is the one of the other months of the same year."""
    frame = sales.assign(year=sales["month"].dt.year, number=sales["month"].dt.month)
    normal = frame[~frame["number"].isin((1, 2, 8))].groupby("year")["revenue_usd"].mean()
    ratio = frame["revenue_usd"] / frame["year"].map(normal) - 1
    assert ratio[frame["number"] == 8].between(-0.25, -0.15).all()
    # January and February: 14.5 % to 20.9 % in the data, about the 15-20 % of the briefing, with one point of tolerance for its noise
    assert ratio[frame["number"].isin((1, 2))].between(0.14, 0.21).all()


def test_the_data_grows_every_year_and_alternates_fast_and_slow_years(sales):
    growth = sales.groupby(sales["month"].dt.year)["revenue_usd"].sum().pct_change().dropna()
    assert (growth > 0).all()
    fast = growth[[2017, 2019, 2021, 2023, 2025]]
    slow = growth[[2018, 2020, 2022, 2024]]
    assert fast.min() > slow.max()  # about 7 % and about 1 % a year, in turns


# ================================================================ "Preparación de datos": the four items of the brief


def written(tmp_path, sales, *edits):
    """The given dataset written again as a file, with the given cells changed as TEXT: ``(row, column, value)``."""
    text = sales.assign(month=sales["month"].dt.strftime("%Y-%m-%d")).astype(str)
    for row, column, value in edits:
        text.loc[row, column] = value
    text.to_csv(tmp_path / "sales.csv", index=False)
    return tmp_path / "sales.csv"


# ---------------- 1. load the dataset and check that the columns are those of the context document


def test_the_columns_of_the_given_file_are_exactly_those_of_the_briefing():
    briefing = (sf.DEFAULT_DATASET.parents[2] / "BRIEFING_NEXOVA_SALES.md").read_text(encoding="utf-8")
    documented = [line.split("`")[1] for line in briefing.split("### 2.")[1].split("###")[0].splitlines() if line.startswith("| `")]
    assert documented == list(sf.COLUMNS)  # the code and the document say the same
    assert sf.DEFAULT_DATASET.read_text(encoding="utf-8").splitlines()[0].split(",") == documented  # and so does the file
    assert sf.DEFAULT_DATASET.name == "nexova_sales.csv" and sf.DEFAULT_DATASET.parts[-3:-1] == ("data", "raw")


@pytest.mark.parametrize(
    "break_it, message",
    [
        (lambda t: t.drop(columns="active_contracts"), "missing columns: active_contracts"),
        (lambda t: t.rename(columns={"revenue_usd": "revenue"}), "missing columns: revenue_usd"),
        (lambda t: t.assign(notes="x"), "columns that the briefing does not describe: notes"),
        (lambda t: t.assign(business_line="consulting"), "business_line values that the briefing does not allow"),
        (lambda t: t.assign(revenue_usd="a lot"), "revenue_usd must be a number"),
        (lambda t: t.assign(active_contracts="12.5"), "active_contracts must be a whole number"),
        (lambda t: t.assign(month="01/2016"), "month must be a date YYYY-MM-01"),
    ],
    ids=["missing", "renamed", "extra", "unknown-line", "not-a-number", "half-contract", "bad-date"],
)
def test_a_file_whose_columns_or_types_differ_is_refused_with_the_reason(tmp_path, sales, break_it, message):
    text = sales.assign(month=sales["month"].dt.strftime("%Y-%m-%d")).astype(str)
    break_it(text).to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(sf.DatasetError, match=message):
        sf.load_sales(tmp_path / "bad.csv")


def test_the_types_after_loading_are_those_of_the_briefing(sales):
    assert pd.api.types.is_datetime64_any_dtype(sales["month"])
    assert pd.api.types.is_float_dtype(sales["revenue_usd"]) and pd.api.types.is_float_dtype(sales["avg_contract_value_usd"])
    assert pd.api.types.is_integer_dtype(sales["active_contracts"])


# ---------------- 2. treat the empty values before training


def test_the_given_dataset_has_nothing_to_treat():
    assert sf.load_sales_with_report()[1] == []


@pytest.mark.parametrize("empty", ["", "   ", "NaN"])
def test_an_empty_revenue_is_rebuilt_from_the_contracts_and_their_value(tmp_path, sales, empty):
    clean, report = sf.load_sales_with_report(written(tmp_path, sales, (40, "revenue_usd", empty)))
    assert report == [{"month": "2019-05", "column": "revenue_usd", "method": "contracts x average value"}]
    assert clean.loc[40, "revenue_usd"] == pytest.approx(sales.loc[40, "revenue_usd"], rel=0.01)
    assert not clean.isna().any().any()


@pytest.mark.parametrize("column", ["active_contracts", "avg_contract_value_usd"])
def test_an_empty_contracts_or_value_is_rebuilt_from_the_other_two(tmp_path, sales, column):
    clean, report = sf.load_sales_with_report(written(tmp_path, sales, (40, column, "")))
    assert [r["column"] for r in report] == [column]
    assert clean.loc[40, column] == pytest.approx(sales.loc[40, column], rel=0.02)


def test_when_it_cannot_be_rebuilt_it_comes_from_the_same_month_a_year_before_not_from_the_month_before(tmp_path, sales):
    """August is filled with the August before: filling it with July would erase the season."""
    row = 43  # 2019-08
    clean, report = sf.load_sales_with_report(written(tmp_path, sales, (row, "revenue_usd", ""), (row, "active_contracts", "")))
    assert clean.loc[row, "month"] == pd.Timestamp("2019-08-01")
    assert clean.loc[row, "revenue_usd"] == sales.loc[row - 12, "revenue_usd"]
    assert report[0] == {"month": "2019-08", "column": "revenue_usd", "method": "same month a year before"}


def test_in_the_first_year_it_comes_from_the_month_before(tmp_path, sales):
    clean, report = sf.load_sales_with_report(written(tmp_path, sales, (5, "revenue_usd", ""), (5, "active_contracts", "")))
    assert clean.loc[5, "revenue_usd"] == sales.loc[4, "revenue_usd"] and report[0]["method"] == "month before"


def test_filling_never_uses_a_later_month(tmp_path, sales):
    """Interpolating or filling backwards would bring the future in: whatever happens after the empty month must not change what is put in it."""
    edits = ((60, "revenue_usd", ""), (60, "active_contracts", ""))
    first = sf.load_sales(written(tmp_path, sales, *edits))
    future = sales.copy()
    future.loc[61:, "revenue_usd"] *= 3
    second = sf.load_sales(written(tmp_path, future, *edits))
    pd.testing.assert_frame_equal(first.loc[:60], second.loc[:60])


def test_an_empty_revenue_in_a_test_month_is_not_made_up(tmp_path, sales):
    with pytest.raises(sf.DatasetError, match="test month 2025-03"):
        sf.load_sales(written(tmp_path, sales, (110, "revenue_usd", ""), (110, "active_contracts", "")))


def test_the_very_first_month_has_nothing_to_be_filled_from(tmp_path, sales):
    with pytest.raises(sf.DatasetError, match="no earlier month"):
        sf.load_sales(written(tmp_path, sales, (0, "revenue_usd", ""), (0, "active_contracts", "")))


def test_no_empty_value_reaches_the_training_rows(sales):
    train, test = sf.build_model_frames(sales)
    assert not train.isna().any().any() and not test.isna().any().any()


# ---------------- 4. scale the variables that need it (item 3, the split, is in test_sales_forecast_split.py)


def test_every_feature_is_either_scaled_or_a_zero_one_flag(sales):
    assert set(sf.SCALED_FEATURES) | set(sf.FLAG_FEATURES) == set(sf.FEATURES)
    assert not set(sf.SCALED_FEATURES) & set(sf.FLAG_FEATURES)
    train, _ = sf.build_model_frames(sales)
    assert all(set(train[flag].unique()) <= {0, 1} for flag in sf.FLAG_FEATURES)
    magnitudes = train[list(sf.SCALED_FEATURES)].abs().max()
    assert magnitudes.max() / magnitudes.min() > 1_000_000  # why: dollars next to a growth of a few hundredths


def test_scaling_puts_the_training_features_on_the_same_scale_and_leaves_the_flags(sales):
    pytest.importorskip("sklearn")
    train, _ = sf.build_model_frames(sales)
    scaled = sf.build_scaler().fit_transform(train[list(sf.FEATURES)])
    assert sorted(scaled.columns) == sorted(sf.FEATURES)
    for feature in sf.SCALED_FEATURES:
        assert scaled[feature].mean() == pytest.approx(0, abs=1e-9) and scaled[feature].std(ddof=0) == pytest.approx(1)
    for flag in sf.FLAG_FEATURES:
        assert scaled[flag].tolist() == train[flag].tolist()


# ---------------- the training script (deliverable of the briefing: in scripts/)


def run_script(*arguments):
    import subprocess
    import sys

    root = sf.DEFAULT_DATASET.parents[2]
    return subprocess.run([sys.executable, str(root / "scripts" / "train_sales_forecast.py"), *arguments], cwd=root, capture_output=True, text=True, timeout=120, check=False)


def test_the_training_script_prepares_the_given_dataset(tmp_path):
    pytest.importorskip("sklearn")
    out = run_script("--output", str(tmp_path))  # a test never rewrites the files of the repository
    assert out.returncode == 0, out.stderr
    assert "120 months" in out.stdout and "Empty values treated: 0." in out.stdout
    assert "96 months to train (2016-01 to 2023-12), 24 to test (2024-01 to 2025-12)" in out.stdout


def test_the_training_script_says_why_it_cannot_use_a_bad_file(tmp_path, sales):
    pytest.importorskip("sklearn")
    sales.drop(columns="revenue_usd").to_csv(tmp_path / "bad.csv", index=False)
    out = run_script("--data", str(tmp_path / "bad.csv"))
    assert out.returncode == 1 and "missing columns: revenue_usd" in out.stderr and "Traceback" not in out.stderr
    assert run_script("--data", str(tmp_path / "nothing.csv")).returncode == 1
