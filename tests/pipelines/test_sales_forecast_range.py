"""The picture of the forecast: the prediction WITH its range of variability (``data/process/sales_range.py`` and ``sales_plot.py``).

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_range.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("matplotlib")

from data.process import sales_evaluation as ev  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_model as sm  # noqa: E402
from data.process import sales_plot as sp  # noqa: E402  (selects the backend that draws to files)
from data.process import sales_range as sr  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FOLDER = REPO / "data" / "eval" / "sales_forecast"
PARAMS = {"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.0}


@pytest.fixture(scope="module")
def evaluated():
    sales = sf.load_sales()
    train, test = sf.build_model_frames(sales)
    forecaster = sm.train_forecaster(train, sm.tune(train)[0].params)
    return sales, train, test, forecaster, ev.evaluate(sales, train, test, forecaster)


# ---------------------------------------------------------------- how wide the range is


def test_the_half_width_is_the_split_conformal_quantile():
    errors = [0.09, 0.01, 0.05, 0.03, 0.07, 0.02, 0.08, 0.04, 0.06]  # nine errors
    assert sr.half_width(errors, 0.9) == 0.09  # ceil(10 x 0.9) = 9th smallest
    assert sr.half_width(errors, 0.5) == 0.05  # ceil(10 x 0.5) = 5th
    assert sr.half_width(np.arange(1, 49) / 1000, 0.9) == 0.045  # 48 errors: the 45th


@pytest.mark.parametrize("errors, level", [([0.1] * 8, 0.9), ([0.1] * 48, 0), ([0.1] * 48, 1), ([0.1] * 48, 1.5)])
def test_a_range_that_cannot_be_built_is_refused(errors, level):
    with pytest.raises(ValueError):
        sr.half_width(errors, level)


def test_the_width_comes_from_the_48_validated_months_of_the_training_years(evaluated):
    _, train, _, forecaster, report = evaluated
    errors = sr.validation_errors(train, forecaster.params)
    assert len(errors) == 48 and (errors >= 0).all()
    assert report["range"]["calibration_years"] == [2020, 2021, 2022, 2023] and report["range"]["calibrated_on_validation_months"] == 48
    assert report["range"]["half_width_percent"] == pytest.approx(sr.half_width(errors) * 100)


def test_the_test_years_take_no_part_in_the_range(evaluated):
    sales, train, _, forecaster, _ = evaluated
    changed = sales.copy()
    changed.loc[96:, "revenue_usd"] *= 4
    other_train, _ = sf.build_model_frames(changed)
    assert sr.half_width(sr.validation_errors(other_train, forecaster.params)) == sr.half_width(sr.validation_errors(train, forecaster.params))


# ---------------------------------------------------------------- the range of every test month, and what falls inside


def test_every_test_month_has_a_forecast_inside_a_range_that_has_a_width(evaluated):
    _, _, test, forecaster, report = evaluated
    rows = pd.DataFrame(report["range"]["monthly"])
    assert rows["month"].tolist() == [f"{m:%Y-%m}" for m in test["month"]] and len(rows) == 24
    assert (rows["low_usd"] < rows["forecast_usd"]).all() and (rows["forecast_usd"] < rows["high_usd"]).all()
    np.testing.assert_allclose(rows["forecast_usd"], forecaster.predict(test))
    half = report["range"]["half_width_percent"] / 100
    np.testing.assert_allclose(rows["low_usd"], rows["forecast_usd"] * (1 - half))
    np.testing.assert_allclose(rows["high_usd"], rows["forecast_usd"] * (1 + half))
    np.testing.assert_allclose(rows["actual_usd"], test["revenue_usd"])


def test_the_count_of_months_inside_is_the_true_one_and_the_ones_outside_are_named(evaluated):
    interval = evaluated[-1]["range"]
    rows = pd.DataFrame(interval["monthly"])
    inside = (rows["actual_usd"] >= rows["low_usd"]) & (rows["actual_usd"] <= rows["high_usd"])
    assert interval["inside"] == int(inside.sum()) and (rows["inside"] == inside).all()
    assert [item["month"] for item in interval["outside"]] == rows.loc[~inside, "month"].tolist()
    assert interval["inside"] / 24 >= 0.8  # a 90 % range that held fewer than 8 months in 10 would not deserve its name


def test_the_spread_of_the_trees_is_narrower_and_holds_fewer_months_which_is_why_it_is_not_the_range(evaluated):
    interval = evaluated[-1]["range"]
    assert interval["tree_spread_mean_width_percent"] < 2 * interval["half_width_percent"]
    assert interval["tree_spread_inside"] < interval["inside"] and interval["tree_spread_inside"] / 24 < interval["level"]


# ---------------------------------------------------------------- the picture shows the range, not just a line


def drawn(report, tmp_path, monkeypatch, language="en"):
    """Draw the picture and keep the figure, to look at what is really in it."""
    kept = {}
    monkeypatch.setattr(sp.plt, "close", lambda figure: kept.setdefault("figure", figure))
    path = sp.plot_forecast(report, tmp_path / f"{language}.png", language)
    return path, kept["figure"]


def test_the_picture_has_the_range_the_forecast_and_the_real_revenue_of_the_24_months(evaluated, tmp_path, monkeypatch):
    report = evaluated[-1]
    _, figure = drawn(report, tmp_path, monkeypatch)
    top = figure.axes[0]
    rows = pd.DataFrame(report["range"]["monthly"])
    (band,) = [item for item in top.collections if item.get_label() == "90% range of the forecast"]
    heights = band.get_paths()[0].vertices[:, 1]
    assert heights.min() == pytest.approx(rows["low_usd"].min() / 1000) and heights.max() == pytest.approx(rows["high_usd"].max() / 1000)
    lines = {line.get_label(): line.get_ydata() for line in top.lines}
    np.testing.assert_allclose(lines["Forecast"], rows["forecast_usd"] / 1000)
    np.testing.assert_allclose(lines["Real revenue"], rows["actual_usd"] / 1000)
    labels = [text.get_text() for text in top.get_legend().get_texts()]
    assert {"90% range of the forecast", "Forecast", "Real revenue", "Real month outside the range"} <= set(labels)
    assert any("2025-08" in text.get_text() for text in top.texts)  # the month outside is named
    assert f"{report['range']['inside']} of 24" in top.get_title(loc="left")


def test_both_languages_are_drawn_and_drawing_twice_gives_the_same_file(evaluated, tmp_path):
    report = evaluated[-1]
    for language in sp.FILES:
        first = sp.plot_forecast(report, tmp_path / f"a-{language}.png", language).read_bytes()
        second = sp.plot_forecast(report, tmp_path / f"b-{language}.png", language).read_bytes()
        assert first[:8] == b"\x89PNG\r\n\x1a\n" and len(first) > 50_000 and first == second


@pytest.mark.parametrize("readme, picture", [("README.md", "forecast_test.png"), ("README.es.md", "forecast_test.es.png")])
def test_the_readme_shows_the_picture_and_says_the_computed_numbers(evaluated, readme, picture):
    interval = evaluated[-1]["range"]
    text = (FOLDER / readme).read_text(encoding="utf-8")
    assert f"](./{picture})" in text and (FOLDER / picture).stat().st_size > 50_000
    assert f"±{interval['half_width_percent']:.1f} %" in text
    inside = f"{interval['inside']} of the 24" if readme == "README.md" else f"{interval['inside']} de los 24"
    assert inside in text
    assert f"{interval['tree_spread_inside']} of the 24" in text or f"{interval['tree_spread_inside']} de los 24" in text
    assert f"{interval['tree_spread_mean_width_percent']:.1f} %" in text and f"{2 * interval['half_width_percent']:.1f} %" in text
