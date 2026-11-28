"""Three things the evaluation of the project looks at: the dataset is the given one, the seed is fixed, and the metrics are those of the TEST set.

Run from the repository root:      uv run pytest tests/pipelines/test_sales_forecast_reproducibility.py

The seasonality and the growth that the briefing describes are checked in ``test_sales_forecast_data.py``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("matplotlib")

from data.process import sales_evaluation as ev  # noqa: E402
from data.process import sales_forecast as sf  # noqa: E402
from data.process import sales_metrics as m  # noqa: E402
from data.process import sales_model as sm  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
# The fingerprint of data/raw/nexova_sales.csv as it was given (line endings normalised, so that a clone on Windows gives the same one).
GIVEN_DATASET_SHA256 = "02e230c221a375b764d84025f282ae1309915eb218ef5e5e7450b47672a886e7"


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()


# ---------------------------------------------------------------- the dataset is the given one, untouched


def test_the_dataset_is_the_one_given_with_the_project_without_a_single_change():
    assert sf.DEFAULT_DATASET == REPO / "data" / "raw" / "nexova_sales.csv"
    assert fingerprint(sf.DEFAULT_DATASET) == GIVEN_DATASET_SHA256


def test_running_the_whole_training_leaves_the_dataset_as_it_was(tmp_path):
    before = sf.DEFAULT_DATASET.read_bytes()
    run_script(tmp_path)
    assert sf.DEFAULT_DATASET.read_bytes() == before


# ---------------------------------------------------------------- the seed is fixed: the experiment can be repeated


def run_script(folder: Path) -> str:
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "train_sales_forecast.py"), "--output", str(folder)], cwd=REPO, capture_output=True, text=True, timeout=300, check=False
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_seed_is_fixed_in_every_random_part():
    assert sm.SEED == 42 and sm.FIXED_PARAMS["random_state"] == 42
    assert sm.random_forest({"max_depth": 3}).random_state == 42


def test_two_separate_runs_of_the_script_give_the_same_numbers_and_the_same_pictures(tmp_path):
    """Two different processes, from the file to the pictures: byte for byte."""
    run_script(tmp_path / "first")
    run_script(tmp_path / "second")
    for name in ("metrics.json", "forecast_test.png", "forecast_test.es.png"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes(), name


def test_without_the_fixed_seed_the_forest_would_change_from_run_to_run():
    """Why the seed matters: the same data with two different seeds gives two different forests."""
    train, test = sf.build_model_frames(sf.load_sales())
    from sklearn.ensemble import RandomForestRegressor

    def answers(seed):
        model = sm.make_pipeline(RandomForestRegressor(n_estimators=50, max_features=0.5, random_state=seed))
        return sm.forecast_dollars(model.fit(train[list(sf.FEATURES)], sm.to_ratio(train)), test)

    assert not np.allclose(answers(1), answers(2))
    np.testing.assert_array_equal(answers(42), answers(42))


# ---------------------------------------------------------------- the metrics are those of the TEST set, not of the training set


@pytest.fixture(scope="module")
def evaluated():
    sales = sf.load_sales()
    train, test = sf.build_model_frames(sales)
    forecaster = sm.train_forecaster(train, sm.tune(train)[0].params)
    return train, test, forecaster, ev.evaluate(sales, train, test, forecaster)


def test_mse_gini_and_k2_are_computed_on_the_24_test_months_and_not_on_the_training(evaluated):
    train, test, forecaster, report = evaluated
    reported = report["model"]
    on_test = m.accuracy_report(test["revenue_usd"].to_numpy(), forecaster.predict(test))
    on_training = m.accuracy_report(train["revenue_usd"].to_numpy(), forecaster.predict(train))
    assert reported == on_test and reported["months"] == 24
    for key in ("mse_usd2", "gini", "k2_statistic"):
        assert reported[key] != pytest.approx(on_training[key]), key
    assert on_training["mse_usd2"] < reported["mse_usd2"]  # the usual: a model looks better on what it learnt from, which is why it is not reported


def test_the_psi_measures_the_test_months_against_the_training_period(evaluated):
    train, test, _, report = evaluated
    psi = report["psi"]
    assert (psi["reference_months"], psi["current_months"]) == (len(train), len(test)) == (72, 24)
    assert psi["values"]["revenue_usd"]["psi"] == pytest.approx(m.psi(train["revenue_usd"], test["revenue_usd"]))


def test_the_metrics_file_says_which_months_it_measured():
    saved = json.loads((REPO / "data" / "eval" / "sales_forecast" / "metrics.json").read_text(encoding="utf-8"))
    assert saved["test_months"] == "2024-01 to 2025-12" and saved["model"]["months"] == 24
    assert {"mse_usd2", "gini", "k2_statistic", "k2_p_value"} <= set(saved["model"]) and "values" in saved["psi"]
