"""The RANGE OF VARIABILITY of the forecast: where the real revenue of a month can be expected to fall.

**The range (defined before it was measured on the test years).** A split-conformal interval on the relative error. While validating inside 2016-2023,
every validated month (2020 to 2023, 48 months) was forecast by a model that had not seen it: how far each one fell, ``|actual / forecast - 1|``, is an
honest sample of how wrong this model is on new months. For a level of 90 %, the half-width ``h`` is the error that at least 90 % of them (with the usual
correction for a finite sample) did not exceed, and the range of a forecast ``f`` is ``f x (1 - h)`` to ``f x (1 + h)``. The test years take no part.

What it does and does not promise:

* It is for the forecast **one month ahead**. For months further away the errors can be larger, and no range is given for them.
* "90 %" is an aim, not a guarantee: the months of a time series are not exchangeable, which is what the guarantee of the method needs. How many test months
  fall inside is counted and reported.
* Its width is the same percentage every month: it does not know that some months are harder than others.

**Why not the spread of the trees.** The 300 trees of the forest give 300 answers, and it is tempting to call their spread "the range". It only says how much
the trees DISAGREE with each other, not how far reality falls from them: the noise of the revenue itself is not in it. It is measured too
(``tree_spread``), so that the difference can be seen, and it is not the range that is drawn.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from data.process import sales_forecast as sf
from data.process import sales_model as sm

RANGE_LEVEL = 0.90


def validation_errors(train: pd.DataFrame, params: dict) -> np.ndarray:
    """``|actual / forecast - 1|`` of every validated month of the training years, each forecast by a model trained only on the months before its year."""
    errors = []
    for _, past, current in sm.time_folds(train):
        forecast = sm.train_forecaster(past, params).predict(current)
        errors.extend(np.abs(current[sf.TARGET].to_numpy() / forecast - 1))
    return np.asarray(errors)


def half_width(errors, level: float = RANGE_LEVEL) -> float:
    """The split-conformal quantile: the ``ceil((n + 1) x level)``-th smallest error."""
    ordered = np.sort(np.asarray(errors, dtype=float))
    if not 0 < level < 1:
        raise ValueError("the level of a range is between 0 and 1")
    position = math.ceil((len(ordered) + 1) * level)
    if position > len(ordered):
        raise ValueError(f"{len(ordered)} errors are too few for a range of {level:.0%}")
    return float(ordered[position - 1])


def bounds(forecast, half: float) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(forecast, dtype=float)
    return values * (1 - half), values * (1 + half)


def tree_spread(forecaster: sm.Forecaster, frame: pd.DataFrame, level: float = RANGE_LEVEL) -> tuple[np.ndarray, np.ndarray]:
    """The central ``level`` of the answers of the single trees, in dollars. NOT the range of the forecast (see the top of this module)."""
    scaled = forecaster.pipeline.named_steps["scale"].transform(frame[list(sf.FEATURES)])
    answers = np.stack([tree.predict(scaled.to_numpy()) for tree in forecaster.pipeline.named_steps["model"].estimators_])
    low, high = np.quantile(answers, [(1 - level) / 2, 1 - (1 - level) / 2], axis=0)
    previous = frame["revenue_lag_12"].to_numpy()
    return low * previous, high * previous


def range_report(train: pd.DataFrame, test: pd.DataFrame, forecaster: sm.Forecaster, level: float = RANGE_LEVEL) -> dict:
    """The range of every test month (one month ahead), and how many real values fall inside it."""
    errors = validation_errors(train, forecaster.params)
    half = half_width(errors, level)
    forecast = forecaster.predict(test)
    low, high = bounds(forecast, half)
    actual = test[sf.TARGET].to_numpy()
    inside = (actual >= low) & (actual <= high)
    trees_low, trees_high = tree_spread(forecaster, test, level)
    monthly = [
        {"month": f"{month:%Y-%m}", "actual_usd": float(a), "forecast_usd": float(f), "low_usd": float(lo), "high_usd": float(hi), "inside": bool(ok)}
        for month, a, f, lo, hi, ok in zip(test["month"], actual, forecast, low, high, inside, strict=True)
    ]
    return {
        "level": level,
        "half_width_percent": half * 100,
        "calibrated_on_validation_months": int(len(errors)),
        "calibration_years": [year for year, _, _ in sm.time_folds(train)],
        "test_months": int(len(test)),
        "inside": int(inside.sum()),
        "outside": [
            {"month": row["month"], "side": "below" if row["actual_usd"] < row["low_usd"] else "above", "beyond_percent": float(
                (row["low_usd"] - row["actual_usd"] if row["actual_usd"] < row["low_usd"] else row["actual_usd"] - row["high_usd"]) / row["forecast_usd"] * 100)}
            for row in monthly if not row["inside"]
        ],
        "tree_spread_inside": int(((actual >= trees_low) & (actual <= trees_high)).sum()),
        "tree_spread_mean_width_percent": float(np.mean((trees_high - trees_low) / forecast) * 100),
        "monthly": monthly,
    }
