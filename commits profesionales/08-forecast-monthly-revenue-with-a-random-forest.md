Forecast Nexova's monthly revenue with a Random Forest (sales forecasting)

Before committing budget to an executive dashboard, the CEO needs to know
whether the revenue of the coming months can be forecast. Train a model on
8 years of consolidated monthly revenue (2016-2023), measure it once on the
2 most recent (2024-2025) and show every forecast with the range in which
the real figure is expected to fall.

Data preparation
- Load data/raw/nexova_sales.csv, the dataset given with the project, and
  require exactly the columns and types of BRIEFING_NEXOVA_SALES.md
- Rebuild an empty value from the other two columns of its row; failing
  that, take it from the past (same month a year before, else the month
  before), never from a later month. Refuse a test month whose revenue
  could only be made up
- Split by time: 96 months to train, 24 to test
- Build 16 causal features: lags, rolling mean and deviation, calendar, and
  the year-on-year growth of the last month and of a year ago. 72 training
  rows have enough past for all of them
- Leave out active_contracts and avg_contract_value_usd: multiplied, they
  are the revenue of the same month
- Scale inside the model pipeline, so the scaler only learns from the rows
  the model is fitted on, in every validation fold too

Model
- Random Forest (scikit-learn), seed 42. It forecasts the change against
  the same month a year before: a tree cannot answer above what it saw,
  and two test months are above every training month. A forest on dollars
  did worse than using no model (5.71 % against 5.25 %)
- Choose the settings by time validation on 2020-2023, inside the training
  years: RMSE 37,274 USD, against 38,836 for XGBoost and 52,574 for the
  same month a year before
- The two models are tied in accuracy: XGBoost is better in 3 of the 4
  years. Random Forest is chosen for the size of the data, explainability
  and how little a poorly chosen setting costs; the code says so

Evaluation on the test set, one month ahead
- MSE 1,072,373,288 USD²; its square root is 3.41 % of the mean month
  (without a model: 5.89 %)
- Normalized Gini 0.898 (without a model: 0.797)
- K² Score (D'Agostino-Pearson on the errors) 1.06, p = 0.59
- PSI 1.769 on revenue, because the company grew, and 0.055 on what the
  model forecasts. With 72 and 24 values chance alone reaches 0.527
- Forecasting the 24 months at once, the error is 3.76 %

Range and report
- 90 % split-conformal range, forecast ±8.6 %, built only from the errors
  on 48 validated months of 2020-2023: 23 of the 24 real months fall
  inside. The spread of the trees is not used: it holds only 20
- Write metrics.json and the chart in English and Spanish to
  data/eval/sales_forecast/, with a README that starts with a summary for
  management, shows the process, explains each metric and why a low MSE is
  not enough on its own
- Check features and forecast against the briefing: August 21-23 % below
  the normal months, January and February 15.5-19 % above

Tooling
- Add a uv project at the repository root (Python 3.12); services/api keeps
  its own environment
- Where prefect or sqlalchemy are missing, do not collect the weekly
  pipeline's tests in tests/pipelines, and say so on screen
- Document the script in scripts/ and the work in memory-bank/; add the
  Spanish text of the nightly_export.py section that was only in English

Verification
- uv run pytest tests/pipelines: 132 passed, among them the 8/2 split and
  the absence of leakage from the rows to the trained model
- Inject five different leaks into the code, one at a time: the split tests
  catch all five
- Train with a completely different 2024-2025: the training rows, the
  chosen settings, the scaler and the model are identical
- Run the script twice in separate processes: metrics.json and both charts
  are identical byte for byte
- Install a clean copy from uv.lock: it reproduces metrics.json
- ruff (rules E4, E7, E9, F and B) passes on the new code
- Check on GitHub that the pull request has no conflicts and that the chart
  and the process diagram are displayed

Known limits
- The change of the mix of business lines cannot be measured: the dataset
  only has the consolidated row, and no figure is invented
- The brief does not define "K2 Score"; D'Agostino-Pearson K² is used
- August is the weakest month (5.1 %, short both times) and the test set
  has only two
- The test period was looked at once while exploring the data, before the
  evaluation; no feature or setting was chosen with an error measured on it
- No range is given for the 24-month forecast
- The data is synthetic and very regular: expect larger errors on real
  revenue
- The five test files of the weekly pipeline need the services/api
  environment

Pull request: #41
