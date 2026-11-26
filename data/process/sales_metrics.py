"""The metrics of the sales forecast: MSE, PSI, Gini and K² Score (plus what is needed to read them).

Pure functions over arrays. Their definitions were written BEFORE the model was measured on the test years. What each one means and why a low MSE
is not enough on its own: ``data/eval/sales_forecast/README.md``.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

PSI_BINS = 5  # with 24 test months, 10 bins would leave about two months in each
PSI_PSEUDO_COUNT = 0.5  # added to every bin, so that an empty one does not turn the index into infinity
PSI_MODERATE, PSI_SIGNIFICANT = 0.10, 0.25  # the usual reading of the index (made for samples of thousands: see ``psi_noise_level``)


def _pair(actual, forecast) -> tuple[np.ndarray, np.ndarray]:
    a, f = np.asarray(actual, dtype=float), np.asarray(forecast, dtype=float)
    if a.shape != f.shape or a.ndim != 1 or not len(a):
        raise ValueError("actual and forecast must be two series of the same, non-zero, length")
    if not (np.isfinite(a).all() and np.isfinite(f).all()):
        raise ValueError("actual and forecast must not have empty or infinite values")
    return a, f


def mse(actual, forecast) -> float:
    """Mean squared error, in USD²: the average of the squared errors. Big errors weigh much more than small ones."""
    a, f = _pair(actual, forecast)
    return float(np.mean((f - a) ** 2))


def rmse_percent_of_mean(actual, forecast) -> float:
    """The square root of the MSE (back in USD) as a percentage of the mean monthly revenue. The MSE itself is in USD², so it cannot be a percentage of dollars."""
    a, f = _pair(actual, forecast)
    return float(np.sqrt(mse(a, f)) / a.mean() * 100)


def mape(actual, forecast) -> float:
    """Mean absolute percentage error: how far, on average, a month is from its forecast, relative to that month."""
    a, f = _pair(actual, forecast)
    return float(np.mean(np.abs(f - a) / np.abs(a)) * 100)


def bias_percent(actual, forecast) -> float:
    """Mean of (forecast - actual) relative to each month: below zero, the forecast falls short on average. The MSE cannot tell this."""
    a, f = _pair(actual, forecast)
    return float(np.mean((f - a) / a) * 100)


def _gini(values: np.ndarray, order_by: np.ndarray) -> float:
    """Gini of ``values`` when they are ranked by ``order_by``, from the highest to the lowest. Months with the same ``order_by`` share their place (their
    values are averaged), so the answer does not depend on the order of the rows."""
    order = np.argsort(-order_by, kind="mergesort")
    ranked, keys = values[order].astype(float), order_by[order]
    for key in np.unique(keys):
        tied = keys == key
        ranked[tied] = ranked[tied].mean()
    n = len(ranked)
    return float(np.cumsum(ranked).sum() / ranked.sum() / n - (n + 1) / (2 * n))


def normalized_gini(actual, forecast) -> float:
    """How well the forecast ORDERS the months by revenue. 1: the same order as reality. About 0: an order no better than chance. Below 0: the opposite.

    It is the Gini for a positive continuous target (the Gini of the forecast's order divided by the Gini of the perfect order). It looks at the order
    only: a forecast that is wrong by the same factor every month keeps a perfect Gini.
    """
    a, f = _pair(actual, forecast)
    if (a <= 0).any():
        raise ValueError("this Gini needs a positive target")
    best = _gini(a, a)
    if best <= 0:
        raise ValueError("all the months have the same revenue: there is no order to find")
    return _gini(a, f) / best


def psi(reference, current, bins: int = PSI_BINS) -> float:
    """Population Stability Index: how different the distribution of ``current`` is from that of ``reference``.

    The bins hold equal shares of ``reference`` (the training period); the ends are open, so values outside its range are counted in the first or the last
    one. ``sum((current_share - reference_share) * ln(current_share / reference_share))``. 0: the same shares. It says nothing about errors.
    """
    r, c = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    if bins < 2 or len(r) < bins or not len(c):
        raise ValueError("the reference needs at least as many values as bins, and the current sample cannot be empty")
    edges = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        raise ValueError("the reference does not vary enough to be cut into bins")
    inner = edges[1:-1]
    count = len(inner) + 1

    def shares(sample: np.ndarray) -> np.ndarray:
        counts = np.bincount(np.searchsorted(inner, sample, side="right"), minlength=count) + PSI_PSEUDO_COUNT
        return counts / counts.sum()

    expected, actual = shares(r), shares(c)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def psi_noise_level(reference_size: int, current_size: int, bins: int = PSI_BINS, confidence: float = 0.95) -> float:
    """The PSI that two samples of these sizes reach BY CHANCE, with nothing having changed, in ``1 - confidence`` of the cases (approximation:
    the index behaves like ``(1/reference + 1/current) x chi-square with bins-1 degrees of freedom``). Below this, a PSI is not evidence of a change."""
    return float((1 / reference_size + 1 / current_size) * stats.chi2.ppf(confidence, bins - 1))


def psi_reading(value: float) -> str:
    if value < PSI_MODERATE:
        return "stable"
    return "moderate change" if value < PSI_SIGNIFICANT else "large change"


def k2_score(actual, forecast) -> tuple[float, float]:
    """D'Agostino-Pearson K² on the errors (actual - forecast): ``(K², p-value)``. It asks whether the errors look like a normal bell, from their
    skewness and their kurtosis. A small p-value (below 0.05) says they do not: there are lopsided or extreme errors. A large one does NOT prove they are
    normal, only that this sample gives no evidence against it. It does not look at the mean: a forecast that is always short can pass it."""
    a, f = _pair(actual, forecast)
    if len(a) < 20:
        raise ValueError("the K² test needs at least 20 errors")
    statistic, p_value = stats.normaltest(a - f)
    return float(statistic), float(p_value)


def r_squared(actual, forecast) -> float:
    """Share of the month-to-month variation that the forecast explains (1: all of it; 0: as good as always saying the average). Given as context."""
    a, f = _pair(actual, forecast)
    total = np.sum((a - a.mean()) ** 2)
    if total == 0:
        raise ValueError("all the months have the same revenue")
    return float(1 - np.sum((a - f) ** 2) / total)


def accuracy_report(actual, forecast) -> dict:
    """The metrics that compare a forecast with reality, month by month."""
    k2, p_value = k2_score(actual, forecast)
    return {
        "months": int(len(np.asarray(actual))),
        "mse_usd2": mse(actual, forecast),
        "rmse_usd": float(np.sqrt(mse(actual, forecast))),
        "rmse_percent_of_mean_revenue": rmse_percent_of_mean(actual, forecast),
        "mape_percent": mape(actual, forecast),
        "bias_percent": bias_percent(actual, forecast),
        "gini": normalized_gini(actual, forecast),
        "k2_statistic": k2,
        "k2_p_value": p_value,
        "r_squared": r_squared(actual, forecast),
    }
