# Formal evaluation of Nexova's sales forecast

_Versión en español: [README.es.md](./README.es.md)._

Evaluation of the Random Forest that forecasts `revenue_usd` of the `consolidated` business line ([`data/raw/nexova_sales.csv`](../../raw/nexova_sales.csv)), before it is approved for staging.
**Only the training years (2016-2023) are used**; 2024-2025 take no part.

**The diagnosis and the corrective action are in the [technical report](../evaluation_report.md).** The analysis of where the error comes from is saved in [`root_cause.json`](./root_cause.json).

```bash
uv run python scripts/evaluate_sales_model.py     # a few minutes: writes diagnosis.json and the pictures
uv run pytest tests/pipelines/test_sales_diagnosis.py
```

## Metrics: MAE and RMSE, on training and on validation

Nested time-series cross-validation: `TimeSeriesSplit` with 8 folds of 6 months (2020-2023), one month ahead. **Mean ± standard deviation across the 8 folds.**
The percentage is of the mean monthly revenue of the months measured, as the [briefing](../../../BRIEFING_NEXOVA_SALES.md) asks, so that it is read without translation and folds of different years can be compared.

| | RMSE (USD) | RMSE (% of mean month) | MAE (USD) | MAE (% of mean month) |
| --- | ---: | ---: | ---: | ---: |
| Training | 19,055 ± 3,514 | 2.45 ± 0.44 % | 15,799 ± 2,736 | 2.03 ± 0.34 % |
| **Validation** | **39,141 ± 9,120** | **4.69 ± 1.27 %** | 33,262 ± 7,432 | 3.98 ± 1.01 % |
| No model (same month a year before) | 52,353 ± 18,494 | 6.15 ± 2.02 % | 44,817 ± 17,949 | 5.26 ± 1.96 % |
| Gap validation − training | 20,086 | | 17,463 | |

Every fold, with both metrics on training and validation, is in [`diagnosis.json`](./diagnosis.json) and in the output of the script. The [learning curve](../learning_curve.png) uses the chosen metric.

## Which one reflects better what an error costs Nexova: **RMSE**

**What the briefing says, and what it does not.** It gives no cost function, and it does not say whether forecasting too much or too little costs more. It says this (quoted in the original Spanish):

> «Un **Gini** alto es especialmente importante para Nexova: Laura necesita distinguir con confianza entre un mes flojo (típico en agosto) y una caída anómala que merezca atención inmediata.» (section 3)
> — A high **Gini** matters especially to Nexova: Laura must tell with confidence a weak month (typical of August) from an abnormal fall that deserves immediate attention.

> «Laura (CEO) necesita saber si el equipo puede predecir los ingresos de los próximos meses antes de comprometer presupuesto en un dashboard ejecutivo completo. El negocio de Nexova (…) tiene ciclos de contratación muy marcados por el calendario laboral en España y en Miami, algo que Javier (Operaciones) y Marcos (Ventas) sienten en carne propia cada agosto y cada enero.» (section 1)
> — Before committing budget to an executive dashboard; hiring cycles marked by the working calendar of Spain and Miami, felt by Javier (Operations) and Marcos (Sales) every August and January.

> «El **MSE** repórtalo en USD² y también como porcentaje del ingreso mensual promedio, para que Marcos y Laura puedan interpretarlo sin traducción adicional.» (section 3)
> — Report the MSE in USD² and as a percentage of the mean monthly revenue, so that Marcos and Laura read it without translation.

**Careful with the first one:** the briefing writes it to explain why a high **Gini** matters (that the forecast ranks the months well from low to high), not to choose between MAE and RMSE. We take from it only what Laura needs. The most direct support for the choice is the third one: the briefing asks for the MSE, and RMSE is its square root (point 3).

**The choice is our reading of those sentences**, not something the briefing states:

1. **The error that matters is the big one.** To tell a normal weak August from an abnormal fall, the forecast is the yardstick. As an example of ours (the figures are not from the briefing): a miss of 15,000 USD hardly changes how a month is read, while one of 90,000 USD can raise a false alarm or hide a real fall. RMSE squares the errors, so one big miss weighs much more than several small ones; in MAE every dollar weighs the same.
   Measured on the 48 validated months, **the 5 worst months (10 % of them) are 42 % of the squared error** but only **25 % of the absolute error**.
2. **The big errors are where the briefing looks.** **August** has the model's largest errors: RMSE 58,358 USD against 40,060 on the 48 months (MAE: 45,621 against 33,262). January and February are the easiest (RMSE 22,834). There are only **4 Augusts** validated: an indication, not a precise measure.
3. **It is consistent with what the briefing already asks and with the model.** RMSE is the square root of the **MSE** the briefing asks for: it ranks forecasts the same way and is back in USD. It is also given as a percentage of the mean monthly revenue, for Marcos and Laura. And the settings of the model are already chosen by RMSE.

**What speaks for MAE, which is why both are reported.** It is explained in one sentence ("on average the forecast misses by 33,262 USD"). It would be the better measure of cost **if every dollar of error cost the same**, whether in one big miss or in many small ones; the briefing says neither that nor the opposite. It is also steadier: with only 48 months, 5 of them weighing 42 % means that one odd month can move the RMSE a lot.

**Does the conclusion change?** Not in what matters: with both metrics the model is better on average than no model, learning from all the past is better than from the last 24 months, and the tree depth with the smallest validation error is 2. One difference: the model loses to the no-model rule in **2 of the 8 folds** with RMSE (1 and 6) and in **3** with MAE (1, 5 and 6).

**What neither of them says: the direction.** Neither MAE nor RMSE tells a high forecast from a low one. On the 48 validated months the model forecast **too much in 25** (35,676 USD on average) and **too little in 23** (30,639 USD), with a mean error of +3,900 USD. As the briefing does not say which direction costs more, **no asymmetric metric has been made up**: the bias is reported next to the RMSE. If Nexova said one direction is more expensive, the errors would have to be weighted differently.
