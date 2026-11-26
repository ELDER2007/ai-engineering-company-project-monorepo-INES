"""Data of the sales forecast: load and check Nexova's monthly revenue, split it in time, and build CAUSAL features.

The source of truth is ``BRIEFING_NEXOVA_SALES.md``: the dataset is ``data/raw/nexova_sales.csv`` (given, never generated here), the target is
``revenue_usd`` of the ``consolidated`` row, the first 8 years (2016-2023) train the model and the last 2 (2024-2025) test it.

No model here and no file is written: pure functions, so that the unit tests can call them with small frames.

**Causal features.** Every feature of the month ``t`` is computed ONLY from the months before ``t`` (``shift(1)`` or more) and from the calendar of
``t`` itself, which is known in advance. Nothing of month ``t`` or later enters it. In particular ``active_contracts`` and
``avg_contract_value_usd`` are NOT features: in every row of the dataset ``revenue_usd = active_contracts x avg_contract_value_usd`` (within 1 %),
so the values of the same month would hand the model the answer, and they are not known yet when the month has to be predicted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "raw" / "nexova_sales.csv"
COLUMNS = ("month", "revenue_usd", "active_contracts", "avg_contract_value_usd", "business_line")
TARGET = "revenue_usd"
MAIN_BUSINESS_LINE = "consolidated"
BUSINESS_LINES = ("headhunting", "outsourcing", "training", "consolidated")  # the values the briefing allows (section 2)
NUMERIC_COLUMNS = ("revenue_usd", "active_contracts", "avg_contract_value_usd")
FIRST_MONTH = pd.Timestamp("2016-01-01")
LAST_MONTH = pd.Timestamp("2025-12-01")
TEST_YEARS = 2

LAGS = (1, 2, 3, 12)
ROLLING_WINDOWS = (3, 6, 12)
LAG_FEATURES = tuple(f"revenue_lag_{lag}" for lag in LAGS)
ROLLING_FEATURES = tuple(f"revenue_roll_{stat}_{window}" for window in ROLLING_WINDOWS for stat in ("mean", "std"))
CALENDAR_FEATURES = ("month_of_year", "is_august", "is_january_or_february", "months_since_start")
# How much a month grew against the same month a year before: the last known month, and the same month a year ago. The second one says in which kind of year
# the series is: the briefing says fast and slow years take turns, so the growth of a year ago points the other way. It needs 24 months of past.
GROWTH_FEATURES = ("yoy_growth_lag_1", "yoy_growth_lag_12")
FEATURES = LAG_FEATURES + ROLLING_FEATURES + CALENDAR_FEATURES + GROWTH_FEATURES

# Scaling. The features live in very different magnitudes (revenue lags near 900 000 dollars, a growth near 0.05, a month between 1 and 12), so every one
# that is not already a 0/1 flag is standardised (mean 0, deviation 1). The flags stay as they are: they are 0 or 1 and they read as such.
FLAG_FEATURES = ("is_august", "is_january_or_february")
SCALED_FEATURES = tuple(feature for feature in FEATURES if feature not in FLAG_FEATURES)


class DatasetError(ValueError):
    """The dataset breaks one of the rules of the briefing."""


def check_columns(frame: pd.DataFrame) -> None:
    """The columns are EXACTLY those of the briefing (section 2): none missing and none that it does not describe."""
    missing = [column for column in COLUMNS if column not in frame.columns]
    if missing:
        raise DatasetError(f"missing columns: {', '.join(missing)}")
    unknown = [column for column in frame.columns if column not in COLUMNS]
    if unknown:
        raise DatasetError(f"columns that the briefing does not describe: {', '.join(map(str, unknown))}")


def _typed(frame: pd.DataFrame) -> pd.DataFrame:
    """The text of the file turned into the types of the briefing. An empty cell stays empty (to be treated); a cell with something that is not a value is an error."""
    out = frame.copy()
    unknown_lines = sorted(set(out["business_line"].dropna()) - set(BUSINESS_LINES))
    if unknown_lines:
        raise DatasetError(f"business_line values that the briefing does not allow: {', '.join(unknown_lines)}")
    if out["month"].isna().any():
        raise DatasetError("a row has no month: it cannot be placed in the series")
    months = pd.to_datetime(out["month"], format="%Y-%m-%d", errors="coerce")
    if months.isna().any():
        raise DatasetError(f"month must be a date YYYY-MM-01, found: {out.loc[months.isna(), 'month'].iloc[0]!r}")
    out["month"] = months
    for column in NUMERIC_COLUMNS:
        numbers = pd.to_numeric(out[column], errors="coerce")
        wrong = numbers.isna() & out[column].notna()
        if wrong.any():
            raise DatasetError(f"{column} must be a number, found: {out.loc[wrong, column].iloc[0]!r}")
        out[column] = numbers.astype(float)
    contracts = out["active_contracts"].dropna()
    if (contracts != contracts.round()).any():
        raise DatasetError("active_contracts must be a whole number")
    return out


def treat_missing(frame: pd.DataFrame, test_years: int = TEST_YEARS) -> tuple[pd.DataFrame, list[dict]]:
    """Fill the empty values of the three numeric columns BEFORE anything is built, and say what was filled. ``frame`` is typed and in chronological order.

    1. **From the other two columns of the same row**, because ``revenue = contracts x average`` in this dataset (within 1 %).
    2. If that is not possible, **from the past only**: the same month a year before (it keeps the season: August is not filled with July), and in the first
       year the month before. NEVER from a later month, neither by interpolating nor by filling backwards: that would be information of the future.

    A revenue of a TEST month that could only be filled from the past is refused: the model would be judged against a value that was made up.
    A month that is absent altogether is not "an empty value": ``validate_sales`` rejects it (the briefing forbids missing months).
    """
    out = frame.sort_values("month").reset_index(drop=True).copy()
    report: list[dict] = []
    if out.empty:
        return out, report
    first_test_month = out["month"].max() - pd.DateOffset(months=12 * test_years - 1)
    row_of = {month: index for index, month in enumerate(out["month"])}

    def note(index: int, column: str, value: float, method: str) -> None:
        out.loc[index, column] = value
        report.append({"month": out.loc[index, "month"].strftime("%Y-%m"), "column": column, "method": method})

    for index in range(len(out)):
        revenue, contracts, average = (out.loc[index, column] for column in NUMERIC_COLUMNS)
        if pd.isna(revenue) and pd.notna(contracts) and pd.notna(average):
            note(index, "revenue_usd", round(contracts * average, 2), "contracts x average value")
        elif pd.isna(contracts) and pd.notna(revenue) and pd.notna(average) and average > 0:
            note(index, "active_contracts", float(round(revenue / average)), "revenue / average value")
        elif pd.isna(average) and pd.notna(revenue) and pd.notna(contracts) and contracts > 0:
            note(index, "avg_contract_value_usd", round(revenue / contracts, 2), "revenue / contracts")
        for column in NUMERIC_COLUMNS:  # what is still empty comes from the past
            if pd.notna(out.loc[index, column]):
                continue
            month = out.loc[index, "month"]
            if column == TARGET and month >= first_test_month:
                raise DatasetError(f"the revenue of the test month {month:%Y-%m} is empty and cannot be rebuilt: it is not made up to be evaluated against")
            for offset, method in ((12, "same month a year before"), (1, "month before")):
                source = row_of.get(month - pd.DateOffset(months=offset))
                if source is not None and pd.notna(out.loc[source, column]):
                    note(index, column, out.loc[source, column], method)
                    break
            else:
                raise DatasetError(f"{column} of {month:%Y-%m} is empty and there is no earlier month to fill it from")
    return out, report


def validate_sales(frame: pd.DataFrame, first_month: pd.Timestamp = FIRST_MONTH, last_month: pd.Timestamp = LAST_MONTH) -> None:
    """The business restrictions of the briefing (section 5) and what a monthly series needs: every month once, from the first to the last, revenue positive."""
    check_columns(frame)
    if frame[list(COLUMNS)].isna().any().any():
        raise DatasetError("the dataset has empty cells")
    if (frame[TARGET] <= 0).any():
        raise DatasetError("revenue_usd must be positive in every month")
    months = pd.DatetimeIndex(frame["month"])
    if months.duplicated().any():
        raise DatasetError("a month appears more than once")
    if (months.day != 1).any():
        raise DatasetError("month must be the first day of the month (YYYY-MM-01)")
    absent = pd.date_range(first_month, last_month, freq="MS").difference(months)
    if len(absent):
        raise DatasetError(f"missing months: {', '.join(m.strftime('%Y-%m') for m in absent[:6])}")
    outside = months[(months < first_month) | (months > last_month)]
    if len(outside):
        raise DatasetError(f"months outside {first_month:%Y-%m} to {last_month:%Y-%m}")


def load_sales_with_report(path: str | Path = DEFAULT_DATASET) -> tuple[pd.DataFrame, list[dict]]:
    """The ``consolidated`` series of the given dataset: columns checked against the briefing, empty values treated, rules checked, in chronological order.
    The second value says every empty value that was filled and how (an empty list: there were none)."""
    raw = pd.read_csv(path, dtype=str, skipinitialspace=True)
    check_columns(raw)
    raw = raw.apply(lambda column: column.str.strip()).replace("", pd.NA)
    typed = _typed(raw)
    consolidated = typed[typed["business_line"] == MAIN_BUSINESS_LINE]
    if consolidated.empty:
        raise DatasetError(f"there is no {MAIN_BUSINESS_LINE!r} row in the dataset")
    clean, report = treat_missing(consolidated[list(COLUMNS)])
    clean["active_contracts"] = clean["active_contracts"].astype("int64")
    clean["business_line"] = clean["business_line"].astype(str)
    validate_sales(clean)
    return clean, report


def load_sales(path: str | Path = DEFAULT_DATASET) -> pd.DataFrame:
    """``load_sales_with_report`` without the report."""
    return load_sales_with_report(path)[0]


def split_train_test(frame: pd.DataFrame, test_years: int = TEST_YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split BY TIME, never at random: the last ``test_years`` years test the model, everything before trains it.

    With the 10 years of the dataset this is 8 years to train (2016-01 to 2023-12, 96 months) and 2 to test (2024-01 to 2025-12, 24 months).
    """
    if test_years < 1:
        raise ValueError("test_years must be at least 1")
    ordered = frame.sort_values("month").reset_index(drop=True)
    first_test_month = ordered["month"].max() - pd.DateOffset(months=12 * test_years - 1)
    train = ordered[ordered["month"] < first_test_month]
    test = ordered[ordered["month"] >= first_test_month]
    if train.empty:
        raise ValueError(f"there is nothing left to train with after keeping {test_years} years for the test")
    return train.reset_index(drop=True), test.reset_index(drop=True)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` (month, revenue_usd) in chronological order plus the columns of ``FEATURES``. The first months have empty values (no past yet).

    The features are built on the WHOLE series and the split comes after: a test month uses the real months before it (also test months), which is what
    is known one month ahead. This is a ONE-STEP-AHEAD forecast.
    """
    out = frame.sort_values("month").reset_index(drop=True).copy()
    revenue = out[TARGET]
    for lag in LAGS:
        out[f"revenue_lag_{lag}"] = revenue.shift(lag)
    past = revenue.shift(1)  # every window ends at the month BEFORE: the month itself never enters its own statistics
    for window in ROLLING_WINDOWS:
        out[f"revenue_roll_mean_{window}"] = past.rolling(window).mean()
        out[f"revenue_roll_std_{window}"] = past.rolling(window).std()
    out["month_of_year"] = out["month"].dt.month
    out["is_august"] = (out["month"].dt.month == 8).astype(int)
    out["is_january_or_february"] = out["month"].dt.month.isin((1, 2)).astype(int)
    first = out["month"].iloc[0]
    out["months_since_start"] = (out["month"].dt.year - first.year) * 12 + (out["month"].dt.month - first.month)
    out["yoy_growth_lag_1"] = revenue.shift(1) / revenue.shift(13) - 1
    out["yoy_growth_lag_12"] = revenue.shift(12) / revenue.shift(24) - 1
    return out


def build_model_frames(frame: pd.DataFrame, test_years: int = TEST_YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features, then the split in time, then the rows without enough past are left out (they can only be at the start of the training years)."""
    featured = add_features(frame)
    train, test = split_train_test(featured, test_years)
    complete_train = train.dropna(subset=list(FEATURES)).reset_index(drop=True)
    if test[list(FEATURES)].isna().any().any():
        raise DatasetError("a test month has not enough past to build its features")
    return complete_train, test


def build_scaler():
    """Standardises ``SCALED_FEATURES`` and leaves the flags as they are. It has to be FITTED ON THE TRAINING ROWS ONLY and then only applied to the test
    rows: a mean or a deviation computed with the test years would let the model see them. (scikit-learn is imported here: the rest of this module needs only pandas.)

    A note for the model: trees (Random Forest, XGBoost) split by thresholds, so scaling does not change what they learn. It is done so that no feature is
    compared with another of a very different magnitude, and so that a model that does care (a linear one, used as a reference) can be compared fairly.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import StandardScaler

    scaler = ColumnTransformer([("standard", StandardScaler(), list(SCALED_FEATURES))], remainder="passthrough", verbose_feature_names_out=False)
    return scaler.set_output(transform="pandas")
