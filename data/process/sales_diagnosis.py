"""Bias and variance of the sales forecast: time-aware cross-validation, learning curve and complexity curve.

This is the measuring part of the formal evaluation of the model (is it under-fitted, over-fitted or reasonably fitted? how stable is it when the data it
learns from changes?). It evaluates the Random Forest of the previous project (``sales_model``); it changes nothing of it.

**Only the training years (2016-2023) are used.** The two test years are the final exam: a diagnosis made by looking at them, and the correction that
follows from it, would turn them into one more training signal. Every function refuses rows from the test period.

* **Cross-validation** (``cross_validate``): ``TimeSeriesSplit`` of scikit-learn, which never shuffles. EIGHT validation blocks of 6 months (the two halves
  of 2020, 2021, 2022 and 2023), each forecast by a model that only saw earlier months. Why 8 blocks of 6 months and not 5 of a year: with the 72 rows that
  have features, five yearly blocks would leave the first model only 12 months, too few to choose its settings. It is NESTED: inside each fold the settings
  of the forest are chosen again, using only that fold's past. The settings of the previous project were chosen by looking at these same four years, so
  measuring them on those years again would flatter the model. ``window`` keeps only the most recent months of the past: "what if it learns from another
  portion of the data?".
* **The checks of every fold** (``check_chronological_order`` and ``check_features_at_fold_boundaries``): that each fold keeps the order of time, and that no
  lag or rolling feature reaches past the boundary. A feature computed on the whole series before splitting can still look into a later fold, so it is not
  assumed: each one is computed AGAIN from a series cut at the boundary, and it must come out identical.

**The metrics: MAE and RMSE**, for the training and for the validation months, both in USD (the unit of ``revenue_usd``) and as a percentage of the mean
monthly revenue of the months measured, as ``BRIEFING_NEXOVA_SALES.md`` asks, so that they are read without translation and folds of different years can be
compared (the company grows). **The chosen one is RMSE**, reported as MEAN ± STANDARD DEVIATION across the folds. Why it reflects better what an error costs
Nexova is argued, with the sentences of the briefing and the errors measured, in ``data/eval/regression_eval/README.md``. The bias goes with both: neither
MAE nor RMSE says whether a forecast fell short or went over. MAPE is kept as an extra column.

**Two ways of forecasting each validation block.** *One month ahead* (how the model is used every month): a month of the block is forecast knowing the real
months before it, also those of its own block; that is its past, never its future. *From the boundary* (the strictest reading): the whole block is forecast
with NO real value after the last training month, each month from the forecasts before it.

* **Learning curve** (``learning_curve``, saved as ``data/eval/learning_curve.png``): error on the months learnt and on the months to come, as the training grows. Every size is measured on the SAME
  validation blocks, and always trains on the months right before them, so the only thing that changes along the curve is how much history there is.
  (scikit-learn's ``learning_curve`` takes the OLDEST months of each fold for the small sizes, which leaves a hole between what is learnt and what is asked.)
* **Complexity curve** (``complexity_curve``): the same two errors as the trees are allowed to grow deeper. It is what tells whether making the model
  simpler or more complex would help, which is what a corrective action has to rest on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from data.process import sales_forecast as sf
from data.process import sales_metrics as metrics
from data.process import sales_model as sm
from data.process.sales_evaluation import forecast_ahead

TEST_STARTS = pd.Timestamp("2024-01-01")
OUTER_SPLITS, OUTER_MONTHS = 8, 6  # validate 2020, 2021, 2022 and 2023, half a year at a time
PRIMARY_METRIC = "rmse_usd"  # justified in data/eval/regression_eval/README.md
METRIC_NAMES = ("rmse_usd", "mae_usd", "rmse_percent_of_mean_revenue", "mae_percent_of_mean_revenue", "mape_percent", "bias_percent")
BUSINESS_LINE = sf.MAIN_BUSINESS_LINE  # "consolidated": the row the briefing says to model
INNER_SPLITS, INNER_MONTHS = 3, 6  # inside a fold, the settings are chosen on three half-years of its past
MIN_PAST = (INNER_SPLITS + 1) * INNER_MONTHS  # the shortest past in which the settings can still be chosen
SLIDING_WINDOW = 24

CURVE_SIZES = (12, 18, 24, 30, 36, 42, 48)
CURVE_HORIZON = 12
CURVE_ORIGINS = (48, 51, 54, 57, 60)  # where each validation block starts (row of the training frame): the same five blocks for every size
DEPTHS = (1, 2, 3, 4, 5, 7, None)


def only_training(frame: pd.DataFrame) -> pd.DataFrame:
    """The rows in chronological order, refusing any month of the test period."""
    if (frame["month"] >= TEST_STARTS).any():
        raise ValueError("the diagnosis uses the training years only: rows from 2024 or later were given")
    return frame.sort_values("month").reset_index(drop=True)


def errors(actual: np.ndarray, forecast: np.ndarray) -> dict:
    """MAE and RMSE of ``revenue_usd``, in USD and as a percentage of the mean monthly revenue of these months; MAPE and the bias.

    MAE: the average miss, every dollar of error weighs the same. RMSE: the square root of the average squared miss, so one big miss weighs much more
    than several small ones. Bias above zero: it forecasts MORE than what is sold.
    """
    actual, forecast = np.asarray(actual, dtype=float), np.asarray(forecast, dtype=float)
    rmse = float(np.sqrt(metrics.mse(actual, forecast)))
    mae = float(np.mean(np.abs(forecast - actual)))
    return {
        "rmse_usd": rmse,
        "mae_usd": mae,
        "rmse_percent_of_mean_revenue": rmse / float(actual.mean()) * 100,
        "mae_percent_of_mean_revenue": mae / float(actual.mean()) * 100,
        "mape_percent": metrics.mape(actual, forecast),
        "bias_percent": metrics.bias_percent(actual, forecast),
    }


def outer_folds(train: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """The (training rows, validation rows) of every fold. ``TimeSeriesSplit`` has no shuffle: each fold trains on a past and validates what comes next."""
    return list(TimeSeriesSplit(n_splits=OUTER_SPLITS, test_size=OUTER_MONTHS).split(train))


def check_chronological_order(train: pd.DataFrame, folds) -> list[dict]:
    """EXPLICIT verification that no fold mixes or shuffles the data. Raises ``ValueError`` naming the first fold that breaks a rule."""
    month_number = train["month"].dt.year.to_numpy() * 12 + train["month"].dt.month.to_numpy()
    report, validated_until = [], None
    for number, (learn, validate) in enumerate(folds, start=1):
        for name, rows in (("training", learn), ("validation", validate)):
            if not len(rows) or (np.diff(month_number[rows]) != 1).any():
                raise ValueError(f"fold {number}: the {name} months are not consecutive months in chronological order")
        if month_number[learn].max() + 1 != month_number[validate].min():
            raise ValueError(f"fold {number}: the validation must start the month after the training ends")
        if validated_until is not None and month_number[validate].min() <= validated_until:
            raise ValueError(f"fold {number}: its validation months are not later than those of the fold before")
        validated_until = month_number[validate].max()
        report.append({
            "fold": number,
            "training": f"{train['month'].iloc[learn[0]]:%Y-%m} to {train['month'].iloc[learn[-1]]:%Y-%m}",
            "validation": f"{train['month'].iloc[validate[0]]:%Y-%m} to {train['month'].iloc[validate[-1]]:%Y-%m}",
            "consecutive_and_in_order": True,
        })
    return report


def _same(first: pd.DataFrame, second: pd.DataFrame) -> bool:
    a, b = first[list(sf.FEATURES)].to_numpy(dtype=float), second[list(sf.FEATURES)].to_numpy(dtype=float)
    return a.shape == b.shape and bool(np.allclose(a, b, rtol=0, atol=1e-9, equal_nan=True))


def check_features_at_fold_boundaries(series: pd.DataFrame, train: pd.DataFrame, folds, build=sf.add_features) -> list[dict]:
    """EXPLICIT verification that no lag or rolling feature looks across a boundary of a fold.

    ``series``: every month (month, revenue_usd) from the first one of the data. ``train`` holds the features computed on that whole series, which is what
    the folds are cut from. For every fold:

    * the features of its TRAINING rows are computed again from the series CUT at the last training month: what comes later does not exist;
    * the features of EACH validation month are computed again from the series cut at that month, with the revenue of the month itself erased.

    Both must be identical to the ones used. A feature that took anything from its own month or from later would differ. Raises ``ValueError``.
    """
    series = only_training(series)[["month", sf.TARGET]]
    used = train.set_index("month")
    report = []
    for number, (learn, validate) in enumerate(folds, start=1):
        training_months, validation_months = train["month"].iloc[learn], train["month"].iloc[validate]
        cut = build(series[series["month"] <= training_months.max()]).set_index("month")
        if not _same(cut.loc[training_months], used.loc[training_months]):
            raise ValueError(f"fold {number}: a feature of a training month changes when the later months are removed: it looks past the boundary")
        for month in validation_months:
            known = series[series["month"] <= month].copy()
            known.loc[known["month"] == month, sf.TARGET] = np.nan  # the value to be forecast does not exist yet
            if not _same(build(known).set_index("month").loc[[month]], used.loc[[month]]):
                raise ValueError(f"fold {number}: a feature of {month:%Y-%m} uses that month or a later one")
        report.append({"fold": number, "training_rows_recomputed": int(len(learn)), "validation_rows_recomputed": int(len(validate)), "identical": True})
    return report


def _fit_and_measure(past: pd.DataFrame, future: pd.DataFrame, params: dict) -> tuple[dict, dict]:
    forecaster = sm.train_forecaster(past, params)
    return errors(past[sf.TARGET].to_numpy(), forecaster.predict(past)), errors(future[sf.TARGET].to_numpy(), forecaster.predict(future))


def choose_settings(past: pd.DataFrame, grid=sm.PARAM_GRID) -> dict:
    """The setting with the smallest mean RMSE on ``INNER_SPLITS`` later blocks of ``past``. It sees nothing after ``past``."""
    if len(past) < MIN_PAST:
        raise ValueError(f"at least {MIN_PAST} months are needed to choose the settings")
    folds = list(TimeSeriesSplit(n_splits=INNER_SPLITS, test_size=INNER_MONTHS).split(past))

    def score(params: dict) -> float:
        return float(np.mean([_fit_and_measure(past.iloc[a], past.iloc[b], params)[1]["rmse_usd"] for a, b in folds]))

    return min(grid, key=score)


def cross_validate(train: pd.DataFrame, series: pd.DataFrame, window: int | None = None, grid=sm.PARAM_GRID) -> list[dict]:
    """Nested time-series cross-validation. ``window=None``: each fold learns from ALL its past (expanding); a number: only from that many latest months.
    ``series`` is every month from the start of the data (the forecast from the boundary needs the history behind the features)."""
    train, series = only_training(train), only_training(series)
    if window is not None and window < MIN_PAST:
        raise ValueError(f"a window shorter than {MIN_PAST} months does not allow the settings to be chosen")
    folds = outer_folds(train)
    check_chronological_order(train, folds)
    results = []
    for number, (learn, validate) in enumerate(folds, start=1):
        past, future = train.iloc[learn], train.iloc[validate]
        if window is not None:
            past = past.tail(window)
        params = choose_settings(past, grid)
        forecaster = sm.train_forecaster(past, params)
        on_training, on_validation = _fit_and_measure(past, future, params)
        actual = future[sf.TARGET].to_numpy()
        forecast = forecaster.predict(future)
        from_boundary = forecast_ahead(forecaster, series[series["month"] <= past["month"].max()], len(future))
        results.append({
            "fold": number,
            "validated_months": f"{future['month'].min():%Y-%m} to {future['month'].max():%Y-%m}",
            "training_months": int(len(past)),
            "params": dict(params),
            "training": on_training,
            "validation": on_validation,
            "validation_from_boundary": errors(actual, from_boundary.to_numpy()),
            "no_model": errors(actual, future["revenue_lag_12"].to_numpy()),  # the same month a year before: always before the boundary
            "monthly": [{"month": f"{m:%Y-%m}", "revenue_usd": float(a), "forecast_usd": float(f)} for m, a, f in zip(future["month"], actual, forecast, strict=True)],
        })
    return results


def summarize(folds: list[dict]) -> dict:
    """Mean and spread across the folds. The spread is the answer to "how stable is it?"."""
    out = {}
    for part in ("training", "validation", "validation_from_boundary", "no_model"):
        out[part] = {}
        for name in METRIC_NAMES:
            values = np.array([fold[part][name] for fold in folds])
            out[part][name] = {"mean": float(values.mean()), "std": float(values.std(ddof=1)), "min": float(values.min()), "max": float(values.max())}
    for name in ("rmse_usd", "mae_usd", "rmse_percent_of_mean_revenue", "mae_percent_of_mean_revenue", "mape_percent"):
        out[f"gap_{name}"] = out["validation"][name]["mean"] - out["training"][name]["mean"]
    return out


KINDS_OF_MONTH = {"August": (8,), "January and February": (1, 2), "the other months": (3, 4, 5, 6, 7, 9, 10, 11, 12)}  # the seasons of the briefing
WORST_MONTHS = 5


def error_profile(folds: list[dict]) -> dict:
    """What tells MAE and RMSE apart on the errors really made: every validated month of the folds, forecast one month ahead by a model that had not seen it."""
    rows = [row for fold in folds for row in fold["monthly"]]
    actual = np.array([row["revenue_usd"] for row in rows])
    error = np.array([row["forecast_usd"] for row in rows]) - actual
    month = np.array([int(row["month"][5:7]) for row in rows])
    worst = np.argsort(-np.abs(error))[:WORST_MONTHS]
    overall = errors(actual, actual + error)
    return {
        "months": int(len(rows)),
        "overall": overall,
        "rmse_over_mae": overall["rmse_usd"] / overall["mae_usd"],  # about 1.25 for errors with a normal shape; far above it: a few huge ones
        "worst_months": [{"month": rows[i]["month"], "error_usd": float(error[i])} for i in worst],
        "worst_months_share_of_squared_error": float(np.sum(error[worst] ** 2) / np.sum(error ** 2)),
        "worst_months_share_of_absolute_error": float(np.sum(np.abs(error[worst])) / np.sum(np.abs(error))),
        "by_kind_of_month": {
            name: {"months": int(np.isin(month, numbers).sum()), **errors(actual[np.isin(month, numbers)], (actual + error)[np.isin(month, numbers)])}
            for name, numbers in KINDS_OF_MONTH.items()
        },
        "over_forecast": {"months": int((error > 0).sum()), "mean_usd": float(error[error > 0].mean()) if (error > 0).any() else 0.0},
        "under_forecast": {"months": int((error < 0).sum()), "mean_usd": float(error[error < 0].mean()) if (error < 0).any() else 0.0},
        "mean_error_usd": float(error.mean()),
    }


def _curve_point(pairs: list[tuple[dict, dict]]) -> dict:
    point = {}
    for index, part in enumerate(("training", "validation")):
        for name in ("rmse_usd", "mae_usd", "mape_percent"):
            values = np.array([pair[index][name] for pair in pairs])
            spread = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            point[f"{part}_{name}"] = {"mean": float(values.mean()), "std": spread, "min": float(values.min()), "max": float(values.max())}
    return point


def learning_curve(train: pd.DataFrame, params: dict, sizes=CURVE_SIZES, origins=CURVE_ORIGINS, horizon: int = CURVE_HORIZON) -> list[dict]:
    """For each training size ``n``: the model learns the ``n`` months right before each validation block and is asked about the ``horizon`` months of the block."""
    train = only_training(train)
    if max(sizes) > min(origins) or max(origins) + horizon > len(train):
        raise ValueError("a training size or a validation block does not fit in the training rows")
    curve = []
    for size in sizes:
        pairs = [_fit_and_measure(train.iloc[start - size:start], train.iloc[start:start + horizon], params) for start in origins]
        curve.append({"training_months": int(size), "blocks": len(origins), **_curve_point(pairs)})
    return curve


def learning_curve_blocks(train: pd.DataFrame, origins=CURVE_ORIGINS, horizon: int = CURVE_HORIZON) -> dict:
    """What every point of the learning curve is measured on: the validation blocks, and how far a forecast WITHOUT a model falls on them. That is the
    reference that says whether an error of the curve is high or low. The blocks overlap (each starts 3 months after the one before): they are not
    independent samples, so their deviation understates the uncertainty."""
    train = only_training(train)
    blocks = [train.iloc[start:start + horizon] for start in origins]
    rival = [errors(block[sf.TARGET].to_numpy(), block["revenue_lag_12"].to_numpy()) for block in blocks]
    out = {"blocks": [f"{block['month'].min():%Y-%m} to {block['month'].max():%Y-%m}" for block in blocks],
           "mean_monthly_revenue_usd": float(np.mean([block[sf.TARGET].mean() for block in blocks]))}
    for name in ("rmse_usd", "mae_usd", "mape_percent"):
        values = np.array([item[name] for item in rival])
        out[f"no_model_{name}"] = {"mean": float(values.mean()), "std": float(values.std(ddof=1))}
    return out


def complexity_curve(train: pd.DataFrame, params: dict, depths=DEPTHS) -> list[dict]:
    """The same two errors, on the folds of the cross-validation, as the trees may grow deeper (the other settings stay as they are)."""
    train = only_training(train)
    folds = outer_folds(train)
    curve = []
    for depth in depths:
        pairs = [_fit_and_measure(train.iloc[a], train.iloc[b], {**params, "max_depth": depth}) for a, b in folds]
        curve.append({"max_depth": depth, **_curve_point(pairs)})
    return curve


def diagnose_data(train: pd.DataFrame, series: pd.DataFrame) -> dict:
    """Every measurement, as plain data. The settings of the curves are the ones of the model being evaluated (chosen on these training rows)."""
    train, series = only_training(train), only_training(series)
    folds = outer_folds(train)
    checks = {
        "chronological_order": check_chronological_order(train, folds),
        "features_at_fold_boundaries": check_features_at_fold_boundaries(series, train, folds),
    }
    params = sm.tune(train)[0].params
    expanding, sliding = cross_validate(train, series), cross_validate(train, series, window=SLIDING_WINDOW)
    return {
        "company": "Nexova",
        "dataset": "data/raw/nexova_sales.csv",
        "date_column": "month",
        "target": sf.TARGET,
        "business_line": BUSINESS_LINE,
        "months_used": f"{train['month'].min():%Y-%m} to {train['month'].max():%Y-%m}",
        "rows": int(len(train)),
        "mean_monthly_revenue_usd": float(train[sf.TARGET].mean()),
        "primary_metric": PRIMARY_METRIC,
        "fold_checks": checks,
        "model_settings": dict(params),
        "cross_validation_all_past": {"folds": expanding, "summary": summarize(expanding)},
        "validation_error_profile": error_profile(expanding),
        f"cross_validation_last_{SLIDING_WINDOW}_months": {"folds": sliding, "summary": summarize(sliding)},
        "learning_curve": learning_curve(train, params),
        "learning_curve_measured_on": learning_curve_blocks(train),
        "complexity_curve": complexity_curve(train, params),
    }
