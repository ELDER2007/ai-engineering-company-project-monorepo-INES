"""The evaluation of the trained forecast on the two test years (2024-2025).

The model arrives here already chosen and trained (``sales_model``): nothing in this module changes it, and nothing may be tuned after reading these
numbers, or the test years would stop being a test.

Two ways of forecasting are measured:

* **one month ahead** (the metrics of the deliverable): each test month is forecast knowing the real months before it.
* **24 months ahead** (extra, ``forecast_ahead``): standing at the end of 2023, every month is forecast from the forecasts before it. This is what
  "the revenue of the coming months" means for a budget, and it is the harder of the two.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.process import sales_forecast as sf
from data.process import sales_metrics as metrics
from data.process.sales_model import Forecaster
from data.process.sales_range import range_report

NO_MODEL = "same month a year before (no model)"
MIX_NOTE = (
    "The change of the mix of business lines (headhunting, outsourcing, training) between training and test CANNOT be measured: the given dataset only "
    "has the 'consolidated' row. The shares in the briefing (about 35 %, 45 % and 20 %) are one fixed figure, not a series: an index computed from them "
    "would be zero by construction, and splitting the revenue by line would mean inventing data."
)


def forecast_ahead(forecaster: Forecaster, history: pd.DataFrame, months: int) -> pd.Series:
    """``months`` months after the end of ``history`` (month, revenue_usd), each one forecast from the ones before: no real value after ``history`` is used."""
    series = history[["month", sf.TARGET]].sort_values("month").reset_index(drop=True)
    made = {}
    for _ in range(months):
        month = series["month"].iloc[-1] + pd.DateOffset(months=1)
        series = pd.concat([series, pd.DataFrame({"month": [month], sf.TARGET: [np.nan]})], ignore_index=True)
        value = float(forecaster.predict(sf.add_features(series).tail(1))[0])  # the features of a month never use its own revenue
        series.loc[series.index[-1], sf.TARGET] = value
        made[month] = value
    return pd.Series(made, name="forecast_ahead")


def _by_group(test: pd.DataFrame, forecast: np.ndarray, groups: dict) -> dict:
    out = {}
    for name, chosen in groups.items():
        mask = chosen.to_numpy()
        actual, mine = test.loc[mask, sf.TARGET].to_numpy(), forecast[mask]
        out[name] = {"months": int(mask.sum()), "mape_percent": metrics.mape(actual, mine), "bias_percent": metrics.bias_percent(actual, mine)}
    return out


def stability(train: pd.DataFrame, test: pd.DataFrame, forecaster: Forecaster) -> dict:
    """PSI between the training rows and the test months, of three things, and how much PSI chance alone gives with samples of these sizes."""
    pairs = {
        # the revenue itself: the company grows, so its level moves up. Expected, and it is why the model does not forecast dollars directly
        "revenue_usd": (train[sf.TARGET], test[sf.TARGET]),
        # what the model forecasts: how much a month is against the same month a year before
        "ratio_to_a_year_before": (train[sf.TARGET] / train["revenue_lag_12"], test[sf.TARGET] / test["revenue_lag_12"]),
        # the model's own answers (the usual "score PSI")
        "forecast_usd": (forecaster.predict(train), forecaster.predict(test)),
    }
    result = {}
    for name, (reference, current) in pairs.items():
        value = metrics.psi(reference, current)
        result[name] = {"psi": value, "reading": metrics.psi_reading(value)}
    return {
        "bins": metrics.PSI_BINS,
        "reference_months": int(len(train)),
        "current_months": int(len(test)),
        "noise_level_95": metrics.psi_noise_level(len(train), len(test)),
        "values": result,
        "business_line_mix": MIX_NOTE,
    }


def evaluate(sales: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame, forecaster: Forecaster) -> dict:
    """Every number of the evaluation, as plain data (it is what ``metrics.json`` holds)."""
    actual = test[sf.TARGET].to_numpy()
    one_ahead = forecaster.predict(test)
    no_model = test["revenue_lag_12"].to_numpy()
    history = sales[sales["month"] < test["month"].min()]
    far = forecast_ahead(forecaster, history, len(test))
    assert list(far.index) == list(test["month"])
    number, year = test["month"].dt.month, test["month"].dt.year
    return {
        "test_months": f"{test['month'].min():%Y-%m} to {test['month'].max():%Y-%m}",
        "mean_monthly_revenue_usd": float(actual.mean()),
        "model": metrics.accuracy_report(actual, one_ahead),
        NO_MODEL: metrics.accuracy_report(actual, no_model),
        "model_24_months_ahead": metrics.accuracy_report(actual, far.to_numpy()),
        "model_by_kind_of_month": _by_group(test, one_ahead, {"August": number == 8, "January and February": number.isin((1, 2)), "the other months": ~number.isin((1, 2, 8))}),
        "model_by_year": _by_group(test, one_ahead, {str(y): year == y for y in sorted(year.unique())}),
        "psi": stability(train, test, forecaster),
        "range": range_report(train, test, forecaster),  # the forecast with its range of variability: what the picture draws
    }
