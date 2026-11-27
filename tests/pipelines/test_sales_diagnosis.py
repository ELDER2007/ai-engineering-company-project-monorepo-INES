"""The measuring part of the formal evaluation (``data/process/sales_diagnosis.py``): cross-validation, learning curve and complexity curve.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_diagnosis.py
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("matplotlib")

from data.process import sales_diagnosis as sd  # noqa: E402
from data.process import sales_diagnosis_plot as sdp  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_model as sm  # noqa: E402

SMALL_GRID = ({"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}, {"max_depth": 5, "min_samples_leaf": 4, "max_features": 0.5})
PARAMS = SMALL_GRID[0]


@pytest.fixture(scope="module")
def sales():
    return sf.load_sales()


@pytest.fixture(scope="module")
def train(sales):
    return sf.build_model_frames(sales)[0]


@pytest.fixture(scope="module")
def series(sales):
    return sales[sales["month"] < sd.TEST_STARTS].reset_index(drop=True)  # every month of 2016-2023: the history behind the features


@pytest.fixture(scope="module")
def folds(train, series):
    return sd.cross_validate(train, series, grid=SMALL_GRID)


def spy_on_fits(monkeypatch) -> list:
    """Record which months each fit learns from and which it is asked about."""
    seen = []
    real = sd._fit_and_measure

    def spy(past, future, params):
        seen.append((past["month"].min(), past["month"].max(), len(past), future["month"].min(), future["month"].max()))
        return real(past, future, params)

    monkeypatch.setattr(sd, "_fit_and_measure", spy)
    return seen


# ---------------------------------------------------------------- only the training years


def test_every_measurement_refuses_a_month_of_the_test_years(sales):
    everything = sf.add_features(sales).dropna(subset=list(sf.FEATURES))
    training = everything[everything["month"] < sd.TEST_STARTS]
    for measure in (
        lambda: sd.cross_validate(everything, sales, grid=SMALL_GRID),
        lambda: sd.cross_validate(training, sales, grid=SMALL_GRID),  # the history must not carry them either
        lambda: sd.learning_curve(everything, PARAMS),
        lambda: sd.complexity_curve(everything, PARAMS),
        lambda: sd.diagnose_data(everything, sales),
        lambda: sd.check_features_at_fold_boundaries(sales, training, sd.outer_folds(training)),
    ):
        with pytest.raises(ValueError, match="training years only"):
            measure()


def test_the_test_years_cannot_change_the_diagnosis(sales, train, series, folds):
    changed = sales.copy()
    changed.loc[96:, "revenue_usd"] *= 6
    other = sf.build_model_frames(changed)[0]
    assert sd.cross_validate(other, changed[changed["month"] < sd.TEST_STARTS], grid=SMALL_GRID) == folds
    assert sd.learning_curve(other, PARAMS, sizes=(24, 48)) == sd.learning_curve(train, PARAMS, sizes=(24, 48))


# ---------------------------------------------------------------- time-series cross-validation: at least 5 folds


BLOCKS = [f"{year}-{first} to {year}-{last}" for year in (2020, 2021, 2022, 2023) for first, last in (("01", "06"), ("07", "12"))]


def test_there_are_at_least_five_folds_of_time_series_split_over_the_training_set(train, folds):
    assert sd.OUTER_SPLITS >= 5 and len(sd.outer_folds(train)) == 8 == len(folds)
    assert [r["validated_months"] for r in folds] == BLOCKS
    assert [r["training_months"] for r in folds] == [24, 30, 36, 42, 48, 54, 60, 66]  # all the past, which grows


def test_every_model_only_saw_months_earlier_than_the_ones_it_is_asked_about(train, series, monkeypatch):
    seen = spy_on_fits(monkeypatch)
    sd.cross_validate(train, series, grid=SMALL_GRID)
    assert seen and all(learnt_until < asked_from for _, learnt_until, _, asked_from, _ in seen)  # in the inner folds too


def test_with_a_window_every_fold_learns_from_the_latest_24_months_only(train, series):
    results = sd.cross_validate(train, series, window=24, grid=SMALL_GRID)
    assert [r["training_months"] for r in results] == [24] * 8 and [r["validated_months"] for r in results] == BLOCKS


def test_a_window_too_short_to_choose_the_settings_is_refused(train, series):
    with pytest.raises(ValueError, match="24 months"):
        sd.cross_validate(train, series, window=12, grid=SMALL_GRID)
    with pytest.raises(ValueError):
        sd.choose_settings(train.iloc[:23], SMALL_GRID)


# ---------------------------------------------------------------- explicit check: no fold shuffles or mixes the data


def test_every_fold_keeps_the_chronological_order(train):
    report = sd.check_chronological_order(train, sd.outer_folds(train))
    assert len(report) == 8 and all(fold["consecutive_and_in_order"] for fold in report)
    assert report[0] == {"fold": 1, "training": "2018-01 to 2019-12", "validation": "2020-01 to 2020-06", "consecutive_and_in_order": True}
    for learn, validate in sd.outer_folds(train):  # and the same, said directly on the dates
        assert train["month"].iloc[learn].is_monotonic_increasing and train["month"].iloc[validate].is_monotonic_increasing
        assert train["month"].iloc[learn].max() < train["month"].iloc[validate].min()


def broken_folds(train, how):
    from sklearn.model_selection import KFold

    good = sd.outer_folds(train)
    if how == "shuffled k-fold":
        return list(KFold(n_splits=5, shuffle=True, random_state=1).split(train))
    if how == "k-fold without shuffling (trains on the future)":
        return list(KFold(n_splits=5).split(train))
    if how == "training rows in another order":
        learn, validate = good[0]
        return [(learn[::-1], validate)]
    if how == "validation overlaps the training":
        learn, validate = good[0]
        return [(np.append(learn, validate[0]), validate)]
    if how == "a hole between training and validation":
        learn, validate = good[0]
        return [(learn[:-1], validate)]
    return [good[1], good[0]]  # the folds themselves out of order


@pytest.mark.parametrize("how", ["shuffled k-fold", "k-fold without shuffling (trains on the future)", "training rows in another order",
                                 "validation overlaps the training", "a hole between training and validation", "folds out of order"])
def test_the_order_check_rejects_every_way_of_mixing_the_data(train, how):
    with pytest.raises(ValueError, match="fold"):
        sd.check_chronological_order(train, broken_folds(train, how))


def test_shuffled_rows_are_rejected_even_with_the_right_indices(train):
    with pytest.raises(ValueError, match="chronological order"):
        sd.check_chronological_order(train.sample(frac=1, random_state=3).reset_index(drop=True), sd.outer_folds(train))


# ---------------------------------------------------------------- explicit check: lag and rolling features at the boundary of each fold


def test_no_feature_looks_across_the_boundary_of_any_fold(train, series):
    report = sd.check_features_at_fold_boundaries(series, train, sd.outer_folds(train))
    assert [fold["training_rows_recomputed"] for fold in report] == [24, 30, 36, 42, 48, 54, 60, 66]
    assert all(fold["validation_rows_recomputed"] == 6 and fold["identical"] for fold in report)


def leaking(kind):
    """The features of the project with ONE of them replaced by a version that looks ahead, computed on the whole series before splitting."""

    def build(frame):
        out = sf.add_features(frame)
        revenue = out["revenue_usd"]
        if kind == "rolling window that includes the month itself":
            out["revenue_roll_mean_3"] = revenue.rolling(3, min_periods=1).mean()
        if kind == "centred rolling window":
            out["revenue_roll_mean_3"] = revenue.shift(1).rolling(3, center=True, min_periods=1).mean()
        if kind == "lag in the wrong direction":
            out["revenue_lag_1"] = revenue.shift(-1)
        if kind == "normalised with the mean of the whole series":
            out["revenue_lag_2"] = out["revenue_lag_2"] / revenue.mean()
        return out

    return build


@pytest.mark.parametrize("kind", ["rolling window that includes the month itself", "centred rolling window", "lag in the wrong direction",
                                  "normalised with the mean of the whole series"])
def test_the_boundary_check_catches_a_feature_computed_on_the_whole_series_that_looks_ahead(series, kind):
    """The trap of the brief: computed before splitting, such a feature peeks into the following fold. The training frame is built with it, as it would happen."""
    build = leaking(kind)
    full = build(series).dropna(subset=list(sf.FEATURES))
    full = full[full["month"] >= pd.Timestamp("2018-01-01")].reset_index(drop=True)
    with pytest.raises(ValueError, match="past the boundary|that month or a later one"):
        sd.check_features_at_fold_boundaries(series, full, sd.outer_folds(full), build=build)


def test_a_training_value_filled_from_beyond_the_boundary_is_caught_although_no_validation_row_changes(train, series):
    """December 2019, the last training month of the first fold, has a gap in a lag, and it is filled BACKWARDS on the whole series, before splitting: the value
    comes from the row of January 2020, which is on the other side of the boundary. December 2019 is never validated, so ONLY the check of the training rows
    (the series cut at the boundary) can see it."""

    def build(frame):
        out = sf.add_features(frame)
        out.loc[out["month"] == pd.Timestamp("2019-12-01"), "revenue_lag_1"] = np.nan
        out["revenue_lag_1"] = out["revenue_lag_1"].bfill()
        return out

    full = build(series)
    full = full[full["month"] >= pd.Timestamp("2018-01-01")].reset_index(drop=True)
    assert not full["revenue_lag_1"].isna().any()  # on the whole series the gap looks filled: nothing seems wrong
    with pytest.raises(ValueError, match="fold 1: a feature of a training month changes .* looks past the boundary"):
        sd.check_features_at_fold_boundaries(series, full, sd.outer_folds(full), build=build)


# ---------------------------------------------------------------- nothing after the boundary


def test_the_forecast_from_the_boundary_uses_no_real_value_after_the_training(train, series, folds):
    """Change the months of the LAST validation block (all but nothing before): the strict forecast cannot move, only its error against the new reality."""
    changed_train, changed_series = train.copy(), series.copy()
    for frame in (changed_train, changed_series):
        frame.loc[frame["month"] >= pd.Timestamp("2023-07-01"), "revenue_usd"] *= 2
    rebuilt = sf.add_features(changed_series)
    changed_train = rebuilt[rebuilt["month"] >= pd.Timestamp("2018-01-01")].reset_index(drop=True)
    again = sd.cross_validate(changed_train, changed_series, grid=SMALL_GRID)
    assert again[:7] == folds[:7]  # a later block changes nothing of the earlier folds
    before, after = folds[7]["validation_from_boundary"], again[7]["validation_from_boundary"]
    forecast_before = 1 + before["bias_percent"] / 100  # mean of forecast / actual
    forecast_after = 1 + after["bias_percent"] / 100
    assert forecast_after == pytest.approx(forecast_before / 2)  # the same forecast against a reality twice as big


def test_the_settings_of_a_fold_are_chosen_without_its_validation_block_or_anything_later(train, series, folds):
    changed_train, changed_series = train.copy(), series.copy()
    for frame in (changed_train, changed_series):
        frame.loc[frame["month"] >= pd.Timestamp("2022-01-01"), "revenue_usd"] *= 3
    again = sd.cross_validate(changed_train, changed_series, grid=SMALL_GRID)
    assert [(r["params"], r["validation"]) for r in again[:4]] == [(r["params"], r["validation"]) for r in folds[:4]]


def test_the_choice_inside_a_fold_only_looks_at_that_folds_past(train, monkeypatch):
    seen = spy_on_fits(monkeypatch)
    past = train.iloc[:36]
    sd.choose_settings(past, SMALL_GRID)
    assert len(seen) == len(SMALL_GRID) * sd.INNER_SPLITS and max(asked_until for *_, asked_until in seen) == past["month"].max()


# ---------------------------------------------------------------- the metric as MEAN ± STANDARD DEVIATION across the folds


def test_the_summary_gives_the_mean_and_the_standard_deviation_across_the_folds(folds):
    summary = sd.summarize(folds)
    for part in ("training", "validation", "validation_from_boundary", "no_model"):
        for name in sd.METRIC_NAMES:
            values = [fold[part][name] for fold in folds]
            assert summary[part][name] == pytest.approx({"mean": np.mean(values), "std": np.std(values, ddof=1), "min": min(values), "max": max(values)})
    for name in ("rmse_usd", "mae_usd"):
        assert summary[f"gap_{name}"] == pytest.approx(summary["validation"][name]["mean"] - summary["training"][name]["mean"])
    assert sd.PRIMARY_METRIC == "rmse_usd"


def test_the_script_prints_the_mean_and_deviation_and_the_checks_of_each_fold(train, folds):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("evaluate_under_test", Path(__file__).resolve().parents[2] / "scripts" / "evaluate_sales_model.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    block = {"folds": folds, "summary": sd.summarize(folds)}
    order = sd.check_chronological_order(train, sd.outer_folds(train))
    report = {
        "months_used": "x", "rows": 72, "model_settings": PARAMS, "mean_monthly_revenue_usd": 1.0, "validation_error_profile": sd.error_profile(folds),
        "fold_checks": {"chronological_order": order, "features_at_fold_boundaries": [{"fold": i, "training_rows_recomputed": 1, "validation_rows_recomputed": 1} for i in range(1, 9)]},
        "cross_validation_all_past": block, f"cross_validation_last_{sd.SLIDING_WINDOW}_months": block,
        "learning_curve": sd.learning_curve(train, PARAMS, sizes=(24,)), "complexity_curve": sd.complexity_curve(train, PARAMS, depths=(3,)),
    }
    text = script.describe(report)
    assert "MEAN ± STANDARD DEVIATION across the 8 folds" in text
    for part in ("training", "validation"):  # MAE and RMSE, for the training and for the validation
        for short, name in (("RMSE", "rmse_usd"), ("MAE", "mae_usd")):
            value = block["summary"][part][name]
            assert f"{short} {value['mean']:>7,.0f} ± {value['std']:>6,.0f} USD" in text
    assert text.count("months in order: yes") == 8


# ---------------------------------------------------------------- the metrics


def test_the_bias_says_the_direction_of_the_error_over_or_under():
    actual = np.array([100.0, 200.0])
    over, under = sd.errors(actual, actual * 1.1), sd.errors(actual, actual * 0.9)
    assert over["bias_percent"] == pytest.approx(10) and under["bias_percent"] == pytest.approx(-10)
    assert over["mape_percent"] == pytest.approx(10) == pytest.approx(under["mape_percent"])  # the size alone cannot tell them apart
    assert sd.errors(actual, actual)["rmse_usd"] == 0


# ---------------------------------------------------------------- the learning curve


def test_every_size_of_the_learning_curve_is_asked_about_the_same_months_and_learns_the_ones_right_before(train, monkeypatch):
    seen = spy_on_fits(monkeypatch)
    curve = sd.learning_curve(train, PARAMS, sizes=(12, 30, 48))
    blocks = {}
    for first, last, rows, asked_from, asked_until in seen:
        assert rows == (last.year - first.year) * 12 + last.month - first.month + 1  # contiguous months
        assert asked_from == last + pd.DateOffset(months=1)  # no hole between what is learnt and what is asked
        blocks.setdefault(rows, []).append((asked_from, asked_until))
    assert list(blocks) == [12, 30, 48] and blocks[12] == blocks[30] == blocks[48] and len(blocks[12]) == len(sd.CURVE_ORIGINS)
    assert [point["training_months"] for point in curve] == [12, 30, 48]
    for point in curve:
        for key in ("training_mae_usd", "validation_mae_usd", "training_rmse_usd", "validation_rmse_usd"):
            assert point[key]["min"] <= point[key]["mean"] <= point[key]["max"]


@pytest.mark.parametrize("sizes, origins", [((60,), (48,)), ((12,), (61,))])
def test_a_size_or_a_block_that_does_not_fit_is_refused(train, sizes, origins):
    with pytest.raises(ValueError, match="does not fit"):
        sd.learning_curve(train, PARAMS, sizes=sizes, origins=origins)


# ---------------------------------------------------------------- the complexity curve


def test_deeper_trees_fit_the_training_months_better(train):
    curve = sd.complexity_curve(train, PARAMS, depths=(1, 3, None))
    training = [point["training_mape_percent"]["mean"] for point in curve]
    assert [point["max_depth"] for point in curve] == [1, 3, None] and training[0] > training[1] > training[2]


# ---------------------------------------------------------------- the picture


def test_the_curves_are_drawn_in_both_languages_the_same_way_every_time(train, folds, tmp_path):
    report = {
        "model_settings": PARAMS,
        "cross_validation_all_past": {"folds": folds},
        "learning_curve": sd.learning_curve(train, PARAMS, sizes=(24, 48)),
        "complexity_curve": sd.complexity_curve(train, PARAMS, depths=(1, 3)),
    }
    for language in sdp.FILES:
        first = sdp.plot_diagnosis(report, tmp_path / f"a-{language}.png", language).read_bytes()
        second = sdp.plot_diagnosis(report, tmp_path / f"b-{language}.png", language).read_bytes()
        assert first[:8] == b"\x89PNG\r\n\x1a\n" and len(first) > 40_000 and first == second


def test_the_evaluated_model_is_the_one_of_the_previous_project(train):
    """The evaluation measures the model that was delivered; it does not build another one."""
    assert sm.tune(train)[0].params == {"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}


# ================================================================ the learning curve as a deliverable: both errors as the training grows, saved in data/eval/


import json  # noqa: E402
from pathlib import Path  # noqa: E402

EVAL = Path(__file__).resolve().parents[2] / "data" / "eval"


@pytest.fixture(scope="module")
def saved_report():
    return json.loads((EVAL / "regression_eval" / "diagnosis.json").read_text(encoding="utf-8"))


def test_the_training_set_grows_along_the_curve_and_each_size_has_both_errors(saved_report):
    curve = saved_report["learning_curve"]
    sizes = [point["training_months"] for point in curve]
    assert sizes == sorted(set(sizes)) == list(sd.CURVE_SIZES) and len(sizes) >= 5
    for point in curve:
        assert point["training_mape_percent"]["mean"] > 0 and point["validation_mape_percent"]["mean"] > 0
        assert point["blocks"] == 5 and point["validation_mape_percent"]["std"] >= 0


def test_the_saved_numbers_of_the_curve_are_the_ones_the_code_computes_today(train, saved_report):
    computed = sd.learning_curve(train, saved_report["model_settings"])
    assert len(computed) == len(saved_report["learning_curve"])
    for mine, saved in zip(computed, saved_report["learning_curve"], strict=True):
        assert mine["training_months"] == saved["training_months"]
        for key in ("training_mape_percent", "validation_mape_percent", "training_mae_usd", "validation_mae_usd", "training_rmse_usd", "validation_rmse_usd"):
            assert saved[key] == pytest.approx(mine[key], rel=1e-9), key
    assert sd.learning_curve_blocks(train) == saved_report["learning_curve_measured_on"]


def test_the_reference_without_a_model_is_measured_on_the_same_blocks(train, saved_report):
    measured = saved_report["learning_curve_measured_on"]
    assert measured["blocks"][0] == "2022-01 to 2022-12" and measured["blocks"][-1] == "2023-01 to 2023-12" and len(measured["blocks"]) == 5
    blocks = [train.iloc[start:start + 12] for start in sd.CURVE_ORIGINS]
    by_hand = [np.sqrt(np.mean((b["revenue_lag_12"] - b["revenue_usd"]) ** 2)) for b in blocks]
    assert measured["no_model_rmse_usd"]["mean"] == pytest.approx(np.mean(by_hand))
    assert measured["no_model_rmse_usd"]["std"] == pytest.approx(np.std(by_hand, ddof=1))


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_image_draws_the_training_and_the_validation_error_against_the_size(saved_report, tmp_path, monkeypatch, language):
    kept = {}
    monkeypatch.setattr(sdp.plt, "close", lambda figure: kept.setdefault("figure", figure))
    sdp.plot_learning_curve(saved_report, tmp_path / "curve.png", language)
    (axis,) = kept["figure"].axes
    texts = sdp.LEARNING_TEXTS[language]
    lines = {line.get_label(): line for line in axis.lines}
    for part in ("training", "validation"):
        line = lines[texts[part]]
        assert list(line.get_xdata()) == [p["training_months"] for p in saved_report["learning_curve"]]
        np.testing.assert_allclose(line.get_ydata(), [p[f"{part}_rmse_usd"]["mean"] / 1000 for p in saved_report["learning_curve"]])  # the chosen metric
    assert axis.get_xlabel() == texts["x"] and axis.get_ylabel() == texts["y"] and axis.get_ylim()[0] == 0
    labels = [t.get_text() for t in axis.get_legend().get_texts()]
    assert texts["training"] in labels and texts["validation"] in labels and any("5" in label and "±" in label for label in labels)


def drawn(draw, report, tmp_path, monkeypatch, language):
    """The figure as it was drawn, to read what it says."""
    kept = {}
    monkeypatch.setattr(sdp.plt, "close", lambda figure: kept.setdefault("figure", figure))
    draw(report, tmp_path / "picture.png", language)
    figure = kept["figure"]
    return figure, [text.get_text() for text in figure.texts] + [text.get_text() for axis in figure.axes for text in axis.texts]


@pytest.mark.parametrize("language", ["en", "es"])
def test_what_the_learning_curve_picture_states_is_computed_from_its_numbers(saved_report, tmp_path, monkeypatch, language):
    changed = json.loads(json.dumps(saved_report))
    changed["learning_curve"][-1]["validation_rmse_usd"]["mean"] = 3 * changed["learning_curve"][-1]["training_rmse_usd"]["mean"]  # other data, other headline
    for report, ratio in ((saved_report, "2.0"), (changed, "3.0")):
        points = {point["training_months"]: point for point in report["learning_curve"]}
        words = sdp.LEARNING_TEXTS[language]
        _, said = drawn(sdp.plot_learning_curve, report, tmp_path, monkeypatch, language)
        assert words["headline"].format(months=48, ratio=float(ratio)) in said
        fall = (points[24]["validation_rmse_usd"]["mean"] - points[48]["validation_rmse_usd"]["mean"]) / 1000
        assert words["flat"].format(start=24, end=48, fall=fall) in said
        for size in (12, 48):
            gap = (points[size]["validation_rmse_usd"]["mean"] - points[size]["training_rmse_usd"]["mean"]) / 1000
            assert words["gap"].format(value=gap) in said
        assert not any(line.startswith(("overfitting", "Overfitting")) for line in said)  # the verdict belongs to the report, not to a drawing


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_headline_and_the_shaded_blocks_of_the_three_panels_follow_the_folds(saved_report, tmp_path, monkeypatch, language):
    changed = json.loads(json.dumps(saved_report))
    changed["cross_validation_all_past"]["folds"][2]["no_model"]["rmse_usd"] = 1000.0  # now the no-model rule also wins in fold 3
    words = sdp.TEXTS[language]
    for report, lost in ((saved_report, [0, 5]), (changed, [0, 2, 5])):
        values = [fold["validation"]["rmse_usd"] / 1000 for fold in report["cross_validation_all_past"]["folds"]]
        figure, said = drawn(sdp.plot_diagnosis, report, tmp_path, monkeypatch, language)
        assert words["headline"].format(low=min(values), high=max(values), lost=len(lost), folds=8) in said
        third = figure.axes[2]
        shaded = sorted(round(patch.get_x() + patch.get_width() / 2) for patch in third.patches)
        assert shaded == lost


def test_no_text_of_a_picture_wears_the_colour_of_a_line(saved_report, tmp_path, monkeypatch):
    from matplotlib.colors import to_hex
    from matplotlib.text import Text

    for draw in (sdp.plot_learning_curve, sdp.plot_diagnosis):
        figure, _ = drawn(draw, saved_report, tmp_path, monkeypatch, "en")
        colours = {to_hex(text.get_color()) for text in figure.findobj(Text) if text.get_text().strip()}
        assert not colours & {sdp.TRAINING, sdp.VALIDATION}, draw.__name__


@pytest.mark.parametrize("language, name", [("en", "learning_curve.png"), ("es", "learning_curve.es.png")])
def test_the_learning_curve_is_saved_in_data_eval(language, name):
    assert sdp.LEARNING_CURVE_FILES[language] == name
    picture = EVAL / name
    assert picture.is_file() and picture.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and picture.stat().st_size > 50_000


def load_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("evaluate_for_files", EVAL.parents[1] / "scripts" / "evaluate_sales_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_saves_the_curve_in_data_eval_and_a_trial_run_does_not_touch_the_repository(saved_report, tmp_path, monkeypatch):
    script = load_script()
    assert script.DEFAULT_CURVE_FOLDER == EVAL
    monkeypatch.setattr(script.sd, "diagnose_data", lambda train, series: saved_report)  # the measuring takes minutes: not what is tested here
    saved_cause = json.loads((EVAL / "regression_eval" / "root_cause.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(script.rc, "root_cause_report", lambda series: saved_cause)
    # a normal run (the default folders, moved to a temporary place): the curve goes to the parent folder, data/eval
    monkeypatch.setattr(script, "DEFAULT_OUTPUT", tmp_path / "eval" / "regression_eval")
    monkeypatch.setattr(script, "DEFAULT_CURVE_FOLDER", tmp_path / "eval")
    assert script.main(["--output", str(tmp_path / "eval" / "regression_eval")]) == 0
    assert (tmp_path / "eval" / "learning_curve.png").is_file() and (tmp_path / "eval" / "learning_curve.es.png").is_file()
    assert json.loads((tmp_path / "eval" / "regression_eval" / "root_cause.json").read_text(encoding="utf-8")) == saved_cause
    # a trial run into another folder: everything, the curve too, stays there
    before = (EVAL / "learning_curve.png").stat().st_mtime_ns
    assert script.main(["--output", str(tmp_path / "trial")]) == 0
    assert (tmp_path / "trial" / "learning_curve.png").is_file() and (EVAL / "learning_curve.png").stat().st_mtime_ns == before


# ================================================================ metrics: MAE and RMSE, the chosen one, and the names of the briefing


REPOSITORY = EVAL.parents[1]
REPORT_READMES = ("README.md", "README.es.md")


def test_mae_and_rmse_by_hand_and_as_a_share_of_the_mean_month():
    actual, forecast = np.array([100.0, 200.0, 300.0]), np.array([110.0, 180.0, 300.0])
    out = sd.errors(actual, forecast)
    assert out["mae_usd"] == pytest.approx((10 + 20 + 0) / 3) and out["rmse_usd"] == pytest.approx(np.sqrt((100 + 400 + 0) / 3))
    assert out["mae_percent_of_mean_revenue"] == pytest.approx(10 / 200 * 100) and out["rmse_percent_of_mean_revenue"] == pytest.approx(out["rmse_usd"] / 200 * 100)


def test_one_big_miss_moves_the_rmse_much_more_than_the_mae():
    """The difference the choice rests on: the same total miss, spread or in one month."""
    actual = np.full(10, 1000.0)
    spread, one_big = actual + 10, actual + np.eye(10)[0] * 100
    assert sd.errors(actual, spread)["mae_usd"] == pytest.approx(sd.errors(actual, one_big)["mae_usd"])
    assert sd.errors(actual, one_big)["rmse_usd"] > 3 * sd.errors(actual, spread)["rmse_usd"]


def test_every_fold_has_mae_and_rmse_for_the_training_and_for_the_validation(folds):
    for fold in folds:
        for part in ("training", "validation"):
            assert 0 < fold[part]["mae_usd"] <= fold[part]["rmse_usd"]  # always true of these two


def test_the_monthly_forecasts_of_a_fold_give_exactly_its_errors(saved_report):
    for fold in saved_report["cross_validation_all_past"]["folds"]:
        actual = np.array([row["revenue_usd"] for row in fold["monthly"]])
        forecast = np.array([row["forecast_usd"] for row in fold["monthly"]])
        assert len(actual) == 6 and fold["validation"] == pytest.approx(sd.errors(actual, forecast))


def test_the_error_profile_is_computed_on_the_48_validated_months(saved_report):
    folds_saved = saved_report["cross_validation_all_past"]["folds"]
    profile = sd.error_profile(folds_saved)
    assert profile["months"] == 48
    error = np.array([row["forecast_usd"] - row["revenue_usd"] for fold in folds_saved for row in fold["monthly"]])
    assert profile["overall"]["mae_usd"] == pytest.approx(np.abs(error).mean()) and profile["overall"]["rmse_usd"] == pytest.approx(np.sqrt(np.mean(error ** 2)))
    worst = np.sort(np.abs(error))[::-1][:5]
    assert profile["worst_months_share_of_squared_error"] == pytest.approx(np.sum(worst ** 2) / np.sum(error ** 2))
    assert profile["worst_months_share_of_absolute_error"] == pytest.approx(worst.sum() / np.abs(error).sum())
    assert profile["over_forecast"]["months"] + profile["under_forecast"]["months"] == 48
    assert sum(item["months"] for item in profile["by_kind_of_month"].values()) == 48 and profile["by_kind_of_month"]["August"]["months"] == 4
    assert profile["worst_months_share_of_squared_error"] == pytest.approx(saved_report["validation_error_profile"]["worst_months_share_of_squared_error"])


# ---------------- the names and values of domain are those of the briefing


def briefing_columns() -> list[str]:
    text = (REPOSITORY / "BRIEFING_NEXOVA_SALES.md").read_text(encoding="utf-8")
    return [line.split("`")[1] for line in text.split("### 2.")[1].split("###")[0].splitlines() if line.startswith("| `")]


def test_the_report_uses_the_column_names_and_the_business_line_of_the_briefing(saved_report):
    columns = briefing_columns()
    assert saved_report["target"] == "revenue_usd" in columns and saved_report["date_column"] == "month" in columns
    assert saved_report["business_line"] == "consolidated" == sd.BUSINESS_LINE and saved_report["company"] == "Nexova"
    assert saved_report["dataset"] == "data/raw/nexova_sales.csv" and (REPOSITORY / saved_report["dataset"]).is_file()
    for row in saved_report["cross_validation_all_past"]["folds"][0]["monthly"]:
        assert set(row) == {"month", "revenue_usd", "forecast_usd"}
    assert set(saved_report["validation_error_profile"]["by_kind_of_month"]) == {"August", "January and February", "the other months"}


@pytest.mark.parametrize("name", REPORT_READMES)
def test_the_justification_quotes_the_briefing_word_for_word_and_names_its_people_and_fields(name):
    briefing = (REPOSITORY / "BRIEFING_NEXOVA_SALES.md").read_text(encoding="utf-8").replace("**", "")
    text = (EVAL / "regression_eval" / name).read_text(encoding="utf-8")
    quotes = [line[3:].rsplit("»", 1)[0] for line in text.splitlines() if line.startswith("> «")]
    assert len(quotes) == 3
    for quote in quotes:
        for piece in quote.replace("**", "").split("(…)"):
            assert piece.strip() in briefing, piece[:80]
    for word in ("Nexova", "revenue_usd", "consolidated", "Laura", "Marcos", "BRIEFING_NEXOVA_SALES.md", "RMSE", "MAE"):
        assert word in text, word


@pytest.mark.parametrize("name", REPORT_READMES)
def test_the_numbers_of_the_justification_are_the_measured_ones(saved_report, name):
    text = (EVAL / "regression_eval" / name).read_text(encoding="utf-8")
    summary = saved_report["cross_validation_all_past"]["summary"]
    for part in ("training", "validation", "no_model"):
        for metric in ("rmse", "mae"):
            usd, share = summary[part][f"{metric}_usd"], summary[part][f"{metric}_percent_of_mean_revenue"]
            assert f"{usd['mean']:,.0f} ± {usd['std']:,.0f}" in text and f"{share['mean']:.2f} ± {share['std']:.2f} %" in text, (part, metric)
    assert f"{summary['gap_rmse_usd']:,.0f}" in text and f"{summary['gap_mae_usd']:,.0f}" in text
    profile = saved_report["validation_error_profile"]
    for value in (f"{profile['worst_months_share_of_squared_error']:.0%}".replace("%", " %"), f"{profile['worst_months_share_of_absolute_error']:.0%}".replace("%", " %"),
                  f"{profile['by_kind_of_month']['August']['rmse_usd']:,.0f}", f"{profile['by_kind_of_month']['August']['mae_usd']:,.0f}",
                  f"{profile['by_kind_of_month']['January and February']['rmse_usd']:,.0f}", f"{profile['overall']['rmse_usd']:,.0f}",
                  f"{profile['over_forecast']['mean_usd']:,.0f}", f"{abs(profile['under_forecast']['mean_usd']):,.0f}", f"+{profile['mean_error_usd']:,.0f}"):
        assert value in text, value


def test_what_the_justification_says_about_both_metrics_agreeing_is_true(saved_report):
    folds_saved = saved_report["cross_validation_all_past"]["folds"]
    worse = {k: [f["fold"] for f in folds_saved if f["validation"][k] > f["no_model"][k]] for k in ("rmse_usd", "mae_usd")}
    assert worse == {"rmse_usd": [1, 6], "mae_usd": [1, 5, 6]}
    last_24 = saved_report["cross_validation_last_24_months"]["summary"]
    everything = saved_report["cross_validation_all_past"]["summary"]
    for metric in ("rmse_usd", "mae_usd"):
        assert everything["validation"][metric]["mean"] < everything["no_model"][metric]["mean"]
        assert everything["validation"][metric]["mean"] < last_24["validation"][metric]["mean"]
        best = min(saved_report["complexity_curve"], key=lambda point: point[f"validation_{metric}"]["mean"])
        assert best["max_depth"] == 2
