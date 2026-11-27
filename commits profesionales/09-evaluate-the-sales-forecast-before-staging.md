Evaluate the sales forecast before staging (bias, variance and stability)

Before the sales forecast moves to staging, answer three questions: is it
under-fitted, over-fitted or reasonably well fitted, how stable is it when
the data it learns from changes, and what specific action would correct it.
Answer: moderate over-fitting. Only the 8 training years (2016-2023) are
used; 2024-2025 take no part. The delivered model is not changed.

Cross-validation
- TimeSeriesSplit with 8 folds of 6 months, nested: the settings are chosen
  again inside each fold with its past only. Eight folds, because five of a
  year would leave the first model too few months to choose its settings
- Check every fold for chronological order, and compute each lag and rolling
  feature again from the series cut at the boundary: they are identical
- Report each block one month ahead and, as the strict reading, from the
  boundary with no real value after it (RMSE 39,141 and 38,820 USD)
- Mean and standard deviation: RMSE 19,055 +/- 3,514 USD on training and
  39,141 +/- 9,120 on validation; without a model 52,353 +/- 18,494. The
  model loses to the no-model rule in 2 of the 8 folds

Curves and metrics
- Learning curve from 12 to 48 months on the same five validation blocks,
  saved in data/eval/learning_curve.png: the gap goes from 33,253 to 18,569
  USD and the two curves never meet. It is computed here because the
  learning_curve of scikit-learn takes the oldest months for small sizes
- Complexity curve: past depth 2, deeper trees only lower training error
- MAE and RMSE on training and validation. RMSE is the main one: the
  briefing asks for the MSE, and RMSE weighs a big miss more. The briefing
  gives no cost function, so the choice is stated as our reading
- Draw both pictures with headlines computed from the numbers, text in ink
  and a blue and orange pair checked for colour blindness

Root cause
- The unpredictable variation of a month is estimated at 3.00-3.24 %; the
  forest misses 2.45 % on the months it learnt
- The forecast multiplies by one month, the same one a year before. The
  validation error follows the chance of that month (correlation +0.50 and
  +0.56) and not that of 11 or 13 months before, the control that could have
  refuted it. It explains a quarter to a third of the error variance

Corrective action (proposed, not applied)
- List the candidates and the rule to accept one before measuring them:
  lower validation RMSE, in 5 of 8 folds or more, with a gap no wider
- Only trees of depth 2 meet it: validation 37,272 USD (-1,868), gap 20,086
  to 15,141. Bigger leaves and a base of two years do not, and are reported
- To apply it: set the depths of PARAM_GRID to (2,), update the test that
  expects 18 settings, retrain and run the evaluation again

Report and documents
- data/eval/evaluation_report.md and .es.md: verdict, pattern of the
  learning curve, stability, metrics, root cause, action, advice for
  staging and limits
- Document the script in scripts/ and the work in memory-bank/

Verification
- uv run pytest tests/pipelines: 249 passed
- The test of the chronological order of the folds has 12 cases. Five faults
  injected into the cross-validation of a copy are all caught
- Seven faults injected into the analysis and the report are all caught, and
  four into the leakage checks
- Tests compare the tables of the report, and the results quoted in its
  text, with the saved results
- Running the evaluation again gives the same numbers and pictures
- ruff (rules E4, E7, E9, F and B) passes on the new code

Known limits
- The gain of depth 2 cannot be safely told from chance: standard error
  1,325 USD, and 68 % of the gain comes from one fold
- Depth 2 had been seen on the complexity curve, and choosing among
  candidates on the same folds makes its figure somewhat optimistic
- The learning curve uses settings chosen on the same years, and its
  validation blocks overlap
- The unpredictable variation is an estimate made with a model, and it
  includes the validated months
- The briefing does not say whether forecasting too much or too little costs
  more, so no asymmetric metric is used
- The dataset is generated: the conclusions are about this series
- The five test files of the weekly pipeline need the services/api
  environment
