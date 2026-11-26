"""The model of the sales forecast: a Random Forest (scikit-learn) that forecasts how much a month changes against the same month a year before.

WHY RANDOM FOREST AND NOT XGBOOST
=================================
Both were compared with the SAME features, the same target and TIME validation inside the training years only (validate 2020, 2021, 2022 and 2023, each
time training with the months before). The test years 2024-2025 took no part in the choice. Reproduce it with
``uv run python scripts/train_sales_forecast.py --compare``. Mean error on the validated years, best setting of each:

    Random Forest   RMSE 37 274 USD   3.60 %
    XGBoost         RMSE 38 836 USD   3.82 %
    (no model) same month a year before   RMSE 52 574 USD   5.25 %

**IN ACCURACY THE TWO ARE TIED.** The average favours Random Forest by about 4 %, but XGBoost is better in THREE of the four validated years (2020, 2021 and
2023); the average turns because of 2022 alone (34 202 against 43 548 USD). So the numbers do not show that either one forecasts better, and the choice does
not rest on them. It rests on these three criteria:

1. **Data size.** There are only 72 rows to train on (10 years of months, minus the test and the 24 months of past the features need). A Random Forest
   averages many independent trees, which lowers the variance of a model trained on little data. Boosting adds trees that correct each other and can chase the
   noise of such a short series unless it is tuned with care.
2. **Explainability.** Marcos and Laura have to trust the number. The forest gives the weight of every feature (``feature_importances``) and, because its trees
   are independent, the spread of their answers says how much they disagree about a month. (XGBoost gives importances too; the spread of independent trees it does not.)
3. **Time available for tuning.** There are few settings that matter, and across the 18 tried the middle one is close to the best (38 559 against 37 274 USD):
   a setting chosen carelessly costs little, and the forest varies less from one year to another (standard deviation of the yearly RMSE: 2 338 against 3 278 USD).
   In fairness to XGBoost: it trains FASTER here (its whole grid takes a couple of seconds against about twenty). At this size neither time is a constraint.

If the series grew much longer, or if there were many more explanatory variables, XGBoost would be worth comparing again.

WHY IT DOES NOT FORECAST DOLLARS DIRECTLY
=========================================
A tree cannot answer a value above the ones it saw while training, and revenue grows: January and February of 2025 are above every training month. The model
forecasts the RATIO ``revenue / revenue of the same month a year before`` (which stays inside the range it knows), and the forecast in dollars is that ratio
times the known revenue of a year before. In the time validation, a forest that forecasts dollars (RMSE 54 006 USD, 5.71 %) was worse than not using a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline

from data.process import sales_forecast as sf

SEED = 42  # the same seed as the dataset: the same run gives the same forest
FIXED_PARAMS = {"n_estimators": 300, "random_state": SEED, "n_jobs": 1}
# The settings that matter for a forest on little data: how deep a tree grows, how few months a leaf may hold and how many features each split looks at.
PARAM_GRID = tuple(
    {"max_depth": depth, "min_samples_leaf": leaf, "max_features": share} for depth, leaf, share in product((3, 5, None), (1, 2, 4), (0.5, 1.0))
)
VALIDATION_YEARS = 4  # the last 4 training years are validated, one at a time


def to_ratio(frame: pd.DataFrame) -> pd.Series:
    """The target the model learns: how much the month is against the same month a year before."""
    return frame[sf.TARGET] / frame["revenue_lag_12"]


def make_pipeline(model) -> Pipeline:
    """Scaler and model together: ``fit`` fits both on the rows it is given and nothing else, in the validation folds too."""
    return Pipeline([("scale", sf.build_scaler()), ("model", model)])


def forecast_dollars(pipeline: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    """The ratio the model answers, turned into dollars with the (already known) revenue of a year before."""
    return pipeline.predict(frame[list(sf.FEATURES)]) * frame["revenue_lag_12"].to_numpy()


def time_folds(train: pd.DataFrame, years: int = VALIDATION_YEARS):
    """``(year, rows before it, rows of it)`` for the last ``years`` years of ``train``: the model is always asked about months AFTER the ones it learnt from."""
    present = sorted(train["month"].dt.year.unique())
    if len(present) <= years:
        raise ValueError(f"{years} validation years need more than {years} years of training rows")
    for year in present[-years:]:
        yield int(year), train[train["month"].dt.year < year], train[train["month"].dt.year == year]


@dataclass(frozen=True)
class Validation:
    """Errors in dollars of one setting on the validated years."""

    params: dict
    rmse_by_year: dict
    mape_by_year: dict

    @property
    def rmse(self) -> float:
        return float(np.mean(list(self.rmse_by_year.values())))

    @property
    def mape(self) -> float:
        return float(np.mean(list(self.mape_by_year.values())))


def _errors(actual: np.ndarray, forecast: np.ndarray) -> tuple[float, float]:
    return float(np.sqrt(np.mean((forecast - actual) ** 2))), float(np.mean(np.abs(forecast - actual) / actual) * 100)


def validate(train: pd.DataFrame, make_model, params: dict) -> Validation:
    """Time validation of ``make_model(params)`` inside the training rows."""
    rmse, mape = {}, {}
    for year, past, current in time_folds(train):
        pipeline = make_pipeline(make_model(params)).fit(past[list(sf.FEATURES)], to_ratio(past))
        rmse[year], mape[year] = _errors(current[sf.TARGET].to_numpy(), forecast_dollars(pipeline, current))
    return Validation(dict(params), rmse, mape)


def random_forest(params: dict) -> RandomForestRegressor:
    return RandomForestRegressor(**FIXED_PARAMS, **params)


def tune(train: pd.DataFrame, grid=PARAM_GRID) -> list[Validation]:
    """Every setting of the grid, the best first. It only receives the training rows: the test years cannot influence the choice."""
    return sorted((validate(train, random_forest, params) for params in grid), key=lambda result: result.rmse)


@dataclass
class Forecaster:
    pipeline: Pipeline
    params: dict

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return forecast_dollars(self.pipeline, frame)

    def feature_importances(self) -> pd.Series:
        """How much each feature weighs in the forest's splits (they add up to 1), the heaviest first."""
        scaled_names = self.pipeline.named_steps["scale"].get_feature_names_out()
        weights = pd.Series(self.pipeline.named_steps["model"].feature_importances_, index=scaled_names)
        return weights.sort_values(ascending=False)


def train_forecaster(train: pd.DataFrame, params: dict) -> Forecaster:
    pipeline = make_pipeline(random_forest(params)).fit(train[list(sf.FEATURES)], to_ratio(train))
    return Forecaster(pipeline, dict(params))


# ---------------------------------------------------------------- the comparison behind the choice (evidence, not part of the model)

XGBOOST_GRID = tuple({"max_depth": depth, "learning_rate": rate, "n_estimators": trees} for depth, rate, trees in product((1, 2, 3), (0.03, 0.1), (100, 300)))


def compare_algorithms(train: pd.DataFrame) -> dict[str, Validation]:
    """Best setting of Random Forest and of XGBoost on the same folds, and the rule without a model (the same month a year before)."""
    from xgboost import XGBRegressor

    xgboost = lambda params: XGBRegressor(random_state=SEED, subsample=0.8, n_jobs=1, **params)  # noqa: E731
    rmse, mape = {}, {}
    for year, _, current in time_folds(train):
        rmse[year], mape[year] = _errors(current[sf.TARGET].to_numpy(), current["revenue_lag_12"].to_numpy())
    return {
        "same month a year before (no model)": Validation({}, rmse, mape),
        "Random Forest": tune(train)[0],
        "XGBoost": min((validate(train, xgboost, params) for params in XGBOOST_GRID), key=lambda result: result.rmse),
    }
