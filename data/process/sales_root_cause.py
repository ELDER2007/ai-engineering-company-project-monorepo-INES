"""Why the sales forecast misses, and which correction attacks that cause.

``sales_diagnosis`` measures THAT the model does much better on the months it learnt than on new ones. This module asks WHY, with checks that could have
said no, and then tries the corrections. As there: training years only (2016-2023), and the model delivered by the previous project is not changed.

**1. How much cannot be predicted** (``noise_estimate``). A model of the shape the briefing describes (a level for each month of the year plus a growth
that changes from year to year) is fitted to the logarithm of ``revenue_usd``; what it leaves unexplained estimates the chance variation. Two shapes of
growth are fitted, so the figure does not hang on one. It is an ESTIMATE, made with all the training years. A second reference does not come from our fit:
the briefing says the months outside August and January-February move "±5%" around the trend (if evenly spread, a standard deviation of 5/√3 = 2.89 %).

**2. Where the error comes from** (``error_against_noise``). The model answers a RATIO and multiplies it by ONE month, ``revenue_lag_12``. Hypothesis:
the chance variation of that single month is carried into the forecast. If so, the validation errors must move with how unusual the month 12 BEFORE was,
and NOT with how unusual the months 11 or 13 before were. Those two are the control that could have refuted it.

**3. The corrections** (``compare_candidates``). The list ``CANDIDATES`` and the rule to accept one (``meets_rule``) were written BEFORE any of them was
measured. All are measured with the same nested cross-validation as the diagnosis (same 8 folds, settings chosen again inside each past) and all are
reported, also the ones that fail. The rule: against the current model, (a) lower mean validation RMSE, (b) lower RMSE in at least 5 of the 8 folds and
(c) a gap between training and validation no wider. Choosing among candidates on the same folds is still a choice made looking at 2020-2023: the figure of
the chosen one is somewhat optimistic until it is confirmed on months that took no part.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from data.process import sales_diagnosis as sd
from data.process import sales_forecast as sf
from data.process import sales_model as sm

BRIEFING_MONTHLY_RANGE_PERCENT = 5.0  # section 4 of the briefing: "el resto de los meses fluctúa de forma moderada (±5%)"
CONTROL_LAGS = (11, 12, 13)  # 12 is the month the forecast is multiplied by; 11 and 13 are the control
FOLDS_TO_IMPROVE = 5
CURRENT = "current"
SMOOTHED_ANCHOR = "anchor_two_years"


def relative_rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Root mean squared RELATIVE miss, in percent: the same unit as the chance variation, whatever the size of the month."""
    return float(np.sqrt(np.mean((np.asarray(forecast, dtype=float) / np.asarray(actual, dtype=float) - 1) ** 2)) * 100)


# ---------------------------------------------------------------- 1. how much cannot be predicted


def _structures(series: pd.DataFrame) -> dict[str, np.ndarray]:
    month, year = series["month"].dt.month.to_numpy(), series["month"].dt.year.to_numpy()
    seasons = np.column_stack([(month == number).astype(float) for number in range(1, 13)])
    later_years = sorted(set(year))[1:]
    time = np.arange(len(series), dtype=float)
    return {
        "a level for each year": np.column_stack([seasons] + [(year == each).astype(float) for each in later_years]),
        "a growth rate for each year": np.column_stack([seasons, time] + [np.clip(time - 12 * k, 0, None) for k in range(1, len(later_years) + 1)]),
    }


def _residuals(series: pd.DataFrame) -> dict[str, tuple[pd.Series, int]]:
    """For each structure: what it does not explain of log(revenue), by month, and how many parameters it used."""
    logarithm = np.log(series[sf.TARGET].to_numpy(dtype=float))
    out = {}
    for name, design in _structures(series).items():
        weights, *_ = np.linalg.lstsq(design, logarithm, rcond=None)
        out[name] = (pd.Series(logarithm - design @ weights, index=series["month"]), int(np.linalg.matrix_rank(design)))
    return out


def noise_estimate(series: pd.DataFrame) -> dict:
    series = sd.only_training(series)
    fits = {}
    for name, (left, parameters) in _residuals(series).items():
        fits[name] = {"parameters": parameters, "months": int(len(left)),
                      "std_percent": float(np.sqrt(np.sum(left.to_numpy() ** 2) / (len(left) - parameters)) * 100),
                      "in_sample_percent": float(np.sqrt(np.mean(left.to_numpy() ** 2)) * 100)}  # what this fit itself misses on the months it saw
    deviations = [fit["std_percent"] for fit in fits.values()]
    return {"fits": fits, "lowest_percent": min(deviations), "highest_percent": max(deviations),
            "from_the_briefing_percent": BRIEFING_MONTHLY_RANGE_PERCENT / float(np.sqrt(3))}


# ---------------------------------------------------------------- 2. where the error comes from


def error_against_noise(folds: list[dict], series: pd.DataFrame, lags=CONTROL_LAGS) -> dict:
    """Correlation of the relative validation error (forecast/real - 1) with how unusual the month ``lag`` months BEFORE the forecast one was."""
    series = sd.only_training(series)
    rows = [row for fold in folds for row in fold["monthly"]]
    months = pd.to_datetime([f"{row['month']}-01" for row in rows])
    error = np.array([row["forecast_usd"] / row["revenue_usd"] - 1 for row in rows])
    out = {}
    for name, (left, _) in _residuals(series).items():
        out[name] = {}
        for lag in lags:
            before = left.loc[months - pd.DateOffset(months=lag)].to_numpy()
            correlation = float(np.corrcoef(error, before)[0, 1])
            out[name][str(lag)] = {"correlation": correlation, "share_of_variance": correlation**2, "slope": float(np.polyfit(before, error, 1)[0])}
    return out


# ---------------------------------------------------------------- 3. the corrections


def add_two_year_anchor(frame: pd.DataFrame) -> pd.DataFrame:
    """The features of the model plus ``anchor_two_years``: the same month one AND two years before, each brought to today's level, averaged.

    growth = mean revenue of the last 12 months / mean of the 12 before; anchor = (lag 12 x growth + lag 24 x growth²) / 2. Two months of chance instead of
    one: their variations partly cancel. Everything ends at the month BEFORE and nothing reaches further back than 24 months, the history the 16 features
    already need, so no training row is lost.
    """
    out = sf.add_features(frame)
    revenue = out[sf.TARGET]
    growth = revenue.shift(1).rolling(12).mean() / revenue.shift(13).rolling(12).mean()
    out[SMOOTHED_ANCHOR] = (revenue.shift(12) * growth + revenue.shift(24) * growth**2) / 2
    return out


@dataclass(frozen=True)
class Candidate:
    description: str
    anchor: str = "revenue_lag_12"
    grid: tuple = sm.PARAM_GRID
    build: Callable = sf.add_features


# Written before any of them was measured. The first is the model as delivered. ("shallower_trees" is not blind: the complexity curve of the diagnosis had
# already shown how depth 2 does on these folds.)
CANDIDATES = {
    CURRENT: Candidate("the model as it is"),
    "shallower_trees": Candidate(
        "less complexity: trees of depth 2",
        grid=tuple({"max_depth": 2, "min_samples_leaf": leaf, "max_features": share} for leaf, share in product((1, 2, 4), (0.5, 1.0))),
    ),
    "bigger_leaves": Candidate(
        "more regularisation: at least 6 months in every leaf",
        grid=tuple({"max_depth": 3, "min_samples_leaf": 6, "max_features": share} for share in (0.5, 1.0)),
    ),
    SMOOTHED_ANCHOR: Candidate("the cause: multiply by two years of the same month instead of one", anchor=SMOOTHED_ANCHOR, build=add_two_year_anchor),
}


def fit(past: pd.DataFrame, params: dict, anchor: str):
    """The pipeline of the model fitted on ``past``, and the function that turns its answers into dollars: ratio x ``anchor``."""
    pipeline = sm.make_pipeline(sm.random_forest(params)).fit(past[list(sf.FEATURES)], past[sf.TARGET] / past[anchor])
    return lambda frame: pipeline.predict(frame[list(sf.FEATURES)]) * frame[anchor].to_numpy()


def _choose(past: pd.DataFrame, candidate: Candidate) -> dict:
    """The same choice as ``sales_diagnosis.choose_settings`` (smallest mean RMSE on later blocks of the past), for any anchor."""
    folds = list(TimeSeriesSplit(n_splits=sd.INNER_SPLITS, test_size=sd.INNER_MONTHS).split(past))
    if len(candidate.grid) == 1:
        return candidate.grid[0]

    def score(params: dict) -> float:
        return float(np.mean([sd.errors(past.iloc[b][sf.TARGET], fit(past.iloc[a], params, candidate.anchor)(past.iloc[b]))["rmse_usd"] for a, b in folds]))

    return min(candidate.grid, key=score)


def _from_boundary(predict, history: pd.DataFrame, months: int, build) -> np.ndarray:
    """``months`` months after ``history``, each one forecast from the forecasts before it: no real value after the boundary is used."""
    series, made = history[["month", sf.TARGET]].reset_index(drop=True), []
    for _ in range(months):
        series = pd.concat([series, pd.DataFrame({"month": [series["month"].iloc[-1] + pd.DateOffset(months=1)], sf.TARGET: [np.nan]})], ignore_index=True)
        made.append(float(predict(build(series).tail(1))[0]))
        series.loc[series.index[-1], sf.TARGET] = made[-1]
    return np.array(made)


def evaluate_candidate(series: pd.DataFrame, candidate: Candidate) -> list[dict]:
    """The nested cross-validation of the diagnosis, for one candidate. ``series``: every training month from the start of the data."""
    series = sd.only_training(series)
    train = candidate.build(series).dropna(subset=[*sf.FEATURES, candidate.anchor]).reset_index(drop=True)
    folds = sd.outer_folds(train)
    sd.check_chronological_order(train, folds)
    results = []
    for number, (learn, validate) in enumerate(folds, start=1):
        past, future = train.iloc[learn], train.iloc[validate]
        params = _choose(past, candidate)
        predict = fit(past, params, candidate.anchor)
        on_past, forecast = predict(past), predict(future)
        actual = future[sf.TARGET].to_numpy()
        history = series[series["month"] <= past["month"].max()]
        results.append({
            "fold": number,
            "validated_months": f"{future['month'].min():%Y-%m} to {future['month'].max():%Y-%m}",
            "training_months": int(len(past)),
            "params": dict(params),
            "training": sd.errors(past[sf.TARGET], on_past),
            "validation": sd.errors(actual, forecast),
            "validation_from_boundary": sd.errors(actual, _from_boundary(predict, history, len(future), candidate.build)),
            "no_model": sd.errors(actual, future["revenue_lag_12"].to_numpy()),
            "training_relative_rmse_percent": relative_rmse(past[sf.TARGET], on_past),
            "validation_relative_rmse_percent": relative_rmse(actual, forecast),
            "anchor_alone": sd.errors(actual, future[candidate.anchor].to_numpy()),  # what the number it multiplies by does on its own
            "monthly": [{"month": f"{m:%Y-%m}", "revenue_usd": float(a), "forecast_usd": float(f)} for m, a, f in zip(future["month"], actual, forecast, strict=True)],
        })
    return results


def meets_rule(current: list[dict], other: list[dict]) -> dict:
    """The rule written before measuring: lower mean validation RMSE, lower in at least 5 of the 8 folds, and a gap no wider."""
    before = np.array([fold["validation"]["rmse_usd"] for fold in current])
    after = np.array([fold["validation"]["rmse_usd"] for fold in other])
    gap = {name: float(np.mean([f["validation"]["rmse_usd"] - f["training"]["rmse_usd"] for f in folds])) for name, folds in (("before", current), ("after", other))}
    change = after - before
    checks = {
        "lower_mean_validation_rmse": bool(after.mean() < before.mean()),
        "folds_improved": int((change < 0).sum()),
        "improves_enough_folds": bool((change < 0).sum() >= FOLDS_TO_IMPROVE),
        "gap_not_wider": bool(gap["after"] <= gap["before"]),
    }
    return {
        **checks,
        "mean_change_usd": float(change.mean()),
        "standard_error_of_change_usd": float(change.std(ddof=1) / np.sqrt(len(change))),  # folds are few: a change smaller than about twice this is weak
        "mean_change_without_best_fold_usd": float(np.delete(change, change.argmin()).mean()),  # a sensitivity check, NOT part of the rule
        "change_by_fold_usd": [float(value) for value in change],
        "gap_before_usd": gap["before"],
        "gap_after_usd": gap["after"],
        "accepted": checks["lower_mean_validation_rmse"] and checks["improves_enough_folds"] and checks["gap_not_wider"],
    }


def compare_candidates(series: pd.DataFrame, candidates: dict = CANDIDATES) -> dict:
    """Every candidate, also the ones that fail. ``candidates`` must include ``CURRENT``."""
    measured = {name: evaluate_candidate(series, candidate) for name, candidate in candidates.items()}
    out = {}
    for name, folds in measured.items():
        out[name] = {"description": candidates[name].description, "folds": folds, "summary": sd.summarize(folds)}
        for key in ("training_relative_rmse_percent", "validation_relative_rmse_percent"):
            values = np.array([fold[key] for fold in folds])
            out[name][key] = {"mean": float(values.mean()), "std": float(values.std(ddof=1))}
        alone = np.array([fold["anchor_alone"]["rmse_usd"] for fold in folds])
        out[name]["anchor_alone_rmse_usd"] = {"mean": float(alone.mean()), "std": float(alone.std(ddof=1))}
        if name != CURRENT:
            out[name]["against_current"] = meets_rule(measured[CURRENT], folds)
    return out


def anchor_profile(series: pd.DataFrame, validated: list[str]) -> dict:
    """What each number the forecast may multiply by is like on the validated months: anchor / real - 1.

    The mean of each year is a shift shared by its 12 months, which a model can learn if it follows a pattern. What changes from month to month WITHIN a
    year is the part that is harder to correct.
    """
    series = sd.only_training(series)
    frame = add_two_year_anchor(series)
    frame = frame[frame["month"].dt.strftime("%Y-%m").isin(validated)]
    out = {}
    for anchor in ("revenue_lag_12", SMOOTHED_ANCHOR):
        offset = frame[anchor] / frame[sf.TARGET] - 1
        by_year = offset.groupby(frame["month"].dt.year)
        out[anchor] = {
            "mean_offset_by_year_percent": {str(year): float(value * 100) for year, value in by_year.mean().items()},
            "spread_within_the_year_percent": float((offset - by_year.transform("mean")).std() * 100),
        }
    totals = series.groupby(series["month"].dt.year)[sf.TARGET].sum()
    out["real_growth_by_year_percent"] = {str(year): float(value * 100) for year, value in totals.pct_change().dropna().items()}
    return out


def root_cause_report(series: pd.DataFrame, candidates: dict = CANDIDATES) -> dict:
    series = sd.only_training(series)
    compared = compare_candidates(series, candidates)
    return {
        "months_used": f"{series['month'].min():%Y-%m} to {series['month'].max():%Y-%m}",
        "noise": noise_estimate(series),
        "error_against_noise": {name: error_against_noise(item["folds"], series) for name, item in compared.items()},
        "anchor_profile": anchor_profile(series, [row["month"] for fold in compared[CURRENT]["folds"] for row in fold["monthly"]]),
        "candidates": compared,
    }
