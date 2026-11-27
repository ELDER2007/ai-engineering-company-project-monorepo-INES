"""The time-series cross-validation of Nexova's sales forecast keeps the chronological order of the data in every fold.

The rule: **no index of a later fold appears before one of an earlier fold.** Spelled out:

1. inside a fold, the indices go forward in time and every training index comes BEFORE every validation index;
2. between folds, every validation index of a later fold comes AFTER every validation index of an earlier one;
3. between folds, the last training index only moves forward. (A later fold does learn again the months of the earlier ones: that is its past.)

It is checked on the strategy the code really uses: the 8 folds of the evaluation, the folds inside each of them where the settings are chosen, and the
months the models are actually fitted on. Splits that break the order are fed to the same check, to show that it does fail.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_cv_chronological_order.py
"""

from __future__ import annotations

from itertools import combinations

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from sklearn.model_selection import KFold  # noqa: E402

from data.process import sales_diagnosis as sd  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402

SETTINGS = {"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}


@pytest.fixture(scope="module")
def sales():
    return sf.load_sales()


@pytest.fixture(scope="module")
def train(sales):
    return sf.build_model_frames(sales)[0]  # the training rows with features: 2018-01 to 2023-12


@pytest.fixture(scope="module")
def series(sales):
    return sales[sales["month"] < sd.TEST_STARTS].reset_index(drop=True)


def assert_chronological(folds, months: pd.Series) -> None:
    """``folds``: (training indices, validation indices) in the order they are used. ``months``: the date of every index."""
    for number, (learn, validate) in enumerate(folds, start=1):
        assert len(learn) and len(validate), f"fold {number} is empty"
        assert (np.diff(learn) > 0).all(), f"fold {number}: the training indices do not go forward"
        assert (np.diff(validate) > 0).all(), f"fold {number}: the validation indices do not go forward"
        assert max(learn) < min(validate), f"fold {number}: a training index is not before the validation"
        # the same with the dates, because an index only means "earlier" if the rows are in order of time
        assert months.loc[list(learn)].is_monotonic_increasing and months.loc[list(validate)].is_monotonic_increasing, f"fold {number}: dates out of order"
        assert months.loc[list(learn)].max() < months.loc[list(validate)].min(), f"fold {number}: it learns from a date that is not before the validated ones"
    for (first, (learn, validate)), (second, (later_learn, later_validate)) in combinations(enumerate(folds, start=1), 2):
        assert max(validate) < min(later_validate), f"an index validated in fold {second} appears before one of fold {first}"
        assert months.loc[list(validate)].max() < months.loc[list(later_validate)].min(), f"fold {second} validates a date before one of fold {first}"
        assert max(learn) < max(later_learn), f"the training of fold {second} does not end later than that of fold {first}"


# ---------------------------------------------------------------- the strategy of the evaluation


def test_the_rows_are_in_chronological_order_before_splitting(train):
    assert list(train.index) == list(range(len(train)))
    assert train["month"].is_monotonic_increasing and train["month"].is_unique


def test_every_fold_of_the_cross_validation_preserves_the_chronological_order(train):
    folds = sd.outer_folds(train)
    assert len(folds) >= 5
    assert_chronological(folds, train["month"])


def test_the_folds_that_choose_the_settings_inside_each_fold_preserve_it_too(train, monkeypatch):
    used = []

    def record(past, future, params):  # stands in for the fit: only which rows are used matters here
        used.append((past.index.to_numpy(), future.index.to_numpy()))
        return {}, {"rmse_usd": 0.0}

    monkeypatch.setattr(sd, "_fit_and_measure", record)
    for learn, validate in sd.outer_folds(train):
        used.clear()
        sd.choose_settings(train.iloc[learn], grid=(SETTINGS,))
        assert len(used) == sd.INNER_SPLITS
        assert_chronological(used, train["month"])
        assert max(future.max() for _, future in used) < min(validate)  # nothing of what the outer fold validates, or later


@pytest.mark.parametrize("window", [None, sd.SLIDING_WINDOW])
def test_the_models_are_really_fitted_in_that_order(train, series, monkeypatch, window):
    """Not only what the splitter answers: the months each model of ``cross_validate`` learns from and is asked about."""
    fitted_on, real = [], sd.sm.train_forecaster

    def record(past, params):
        fitted_on.append(past.index.to_numpy())
        return real(past, params)

    monkeypatch.setattr(sd, "choose_settings", lambda past, grid: SETTINGS)  # checked above
    monkeypatch.setattr(sd.sm, "train_forecaster", record)
    results = sd.cross_validate(train, series, window=window)
    index_of = {f"{month:%Y-%m}": index for index, month in train["month"].items()}
    validated = [np.array([index_of[row["month"]] for row in fold["monthly"]]) for fold in results]
    # cross_validate fits each fold twice on the same rows (to forecast and to measure): both must be those rows
    learnt = fitted_on[::2]
    assert len(fitted_on) == 2 * len(results) and all((a == b).all() for a, b in zip(learnt, fitted_on[1::2], strict=True))
    assert_chronological(list(zip(learnt, validated, strict=True)), train["month"])


# ---------------------------------------------------------------- the check does fail when the order is broken


def broken(kind: str, train: pd.DataFrame) -> list:
    good = sd.outer_folds(train)
    if kind == "shuffled k-fold":
        return list(KFold(n_splits=8, shuffle=True, random_state=42).split(train))
    if kind == "k-fold that learns from the future":
        return list(KFold(n_splits=8).split(train))
    if kind == "later folds first":
        return good[::-1]
    if kind == "two folds swapped":
        return [good[1], good[0], *good[2:]]
    if kind == "indices shuffled inside a block":
        return [(good[0][0], good[0][1][::-1]), *good[1:]]
    if kind == "one month of the validation in the training":
        learn, validate = good[0]
        return [(np.append(learn, validate[0]), validate), *good[1:]]
    raise ValueError(kind)


@pytest.mark.parametrize("kind", ["shuffled k-fold", "k-fold that learns from the future", "later folds first", "two folds swapped",
                                  "indices shuffled inside a block", "one month of the validation in the training"])
def test_a_split_that_breaks_the_order_is_caught(train, kind):
    with pytest.raises(AssertionError):
        assert_chronological(broken(kind, train), train["month"])


def test_rows_out_of_order_are_caught_even_if_the_indices_look_right(train):
    shuffled = train.sample(frac=1, random_state=42).reset_index(drop=True)
    with pytest.raises(AssertionError):
        assert_chronological(sd.outer_folds(shuffled), shuffled["month"])
