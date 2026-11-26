"""The picture of the forecast: the prediction WITH its range of variability against the real revenue of the two test years.

It draws the numbers of the evaluation report (``report["range"]``), the same that ``metrics.json`` holds, so the picture cannot say anything else.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draws to a file, with no window: it works in a server and in the tests

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

FILES = {"en": "forecast_test.png", "es": "forecast_test.es.png"}
TEXTS = {
    "en": {
        "title": "Nexova: monthly revenue forecast against reality, test years 2024-2025",
        "subtitle": "One month ahead. {inside} of {months} real months fall inside the {level} range (±{half:.1f} %, measured on 2020-2023 only).",
        "range": "{level} range of the forecast",
        "forecast": "Forecast",
        "actual": "Real revenue",
        "outside": "Real month outside the range",
        "above": "above",
        "below": "below",
        "august": "August",
        "revenue": "Revenue (thousand USD)",
        "error": "Real against forecast (%)",
        "limit": "limits of the range",
    },
    "es": {
        "title": "Nexova: pronóstico de ingresos mensuales frente a la realidad, años de prueba 2024-2025",
        "subtitle": "Un mes por delante. {inside} de {months} meses reales caen dentro del rango del {level} (±{half:.1f} %, medido solo con 2020-2023).",
        "range": "Rango del {level} del pronóstico",
        "forecast": "Pronóstico",
        "actual": "Ingresos reales",
        "outside": "Mes real fuera del rango",
        "above": "por encima",
        "below": "por debajo",
        "august": "Agosto",
        "revenue": "Ingresos (miles de USD)",
        "error": "Real frente al pronóstico (%)",
        "limit": "límites del rango",
    },
}
ACTUAL, FORECAST, BAND, OUTSIDE = "#111111", "#1f5f99", "#a8cbea", "#c2410c"  # readable without telling red from green: the outliers also change shape


def plot_forecast(report: dict, path: str | Path, language: str = "en") -> Path:
    """Draw ``report["range"]`` into the PNG ``path`` and return it."""
    text, interval = TEXTS[language], report["range"]
    rows = pd.DataFrame(interval["monthly"])
    months = pd.to_datetime(rows["month"], format="%Y-%m")
    level = f"{interval['level']:.0%}" if language == "en" else f"{interval['level'] * 100:.0f} %"
    thousands = rows[["actual_usd", "forecast_usd", "low_usd", "high_usd"]] / 1000
    outside = ~rows["inside"]

    figure, (top, bottom) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
    for axis in (top, bottom):
        for month in months[months.dt.month == 8]:
            axis.axvspan(month - pd.Timedelta(days=15), month + pd.Timedelta(days=15), color="#eeeeee", zorder=0)
        axis.grid(axis="y", color="#dddddd", linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)

    top.fill_between(months, thousands["low_usd"], thousands["high_usd"], color=BAND, alpha=0.75, linewidth=0, label=text["range"].format(level=level))
    top.plot(months, thousands["forecast_usd"], color=FORECAST, linestyle="--", linewidth=2, marker="o", markersize=4, label=text["forecast"])
    top.plot(months, thousands["actual_usd"], color=ACTUAL, linewidth=2, marker="o", markersize=5, label=text["actual"])
    if outside.any():
        top.scatter(months[outside], thousands.loc[outside, "actual_usd"], marker="X", s=190, color=OUTSIDE, edgecolor="white", zorder=5, label=text["outside"])
        for item in interval["outside"]:
            row = rows.index[rows["month"] == item["month"]][0]
            sign = 1 if item["side"] == "above" else -1
            top.annotate(f"{item['month']}: {text[item['side']]} ({item['beyond_percent']:.1f} %)", (months[row], thousands.loc[row, "actual_usd"]),
                         textcoords="offset points", xytext=(-78, 30 * sign), ha="center", fontsize=9, color=OUTSIDE, zorder=6,
                         bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": OUTSIDE}, arrowprops={"arrowstyle": "-", "color": OUTSIDE})
    for month in months[months.dt.month == 8]:
        top.text(month, 0.02, text["august"], transform=top.get_xaxis_transform(), ha="center", va="bottom", fontsize=9, color="#555555")
    top.set_ylabel(text["revenue"])
    top.legend(loc="upper left", frameon=False, ncol=2)
    figure.suptitle(text["title"], x=0.065, ha="left", fontsize=14, fontweight="bold")
    top.set_title(text["subtitle"].format(inside=interval["inside"], months=interval["test_months"], level=level, half=interval["half_width_percent"]),
                  loc="left", fontsize=10.5)

    deviation = (rows["actual_usd"] / rows["forecast_usd"] - 1) * 100
    half = interval["half_width_percent"]
    bottom.bar(months, deviation, width=20, color=[OUTSIDE if out else FORECAST for out in outside], zorder=2)
    for value in (half, -half):
        bottom.axhline(value, color=FORECAST, linestyle=":", linewidth=1.5)
    bottom.axhline(0, color="#555555", linewidth=0.8)
    bottom.text(months.iloc[0], -half - 0.8, text["limit"], fontsize=9, color=FORECAST, va="top")
    bottom.set_ylim(-half * 1.55, half * 1.55)
    bottom.set_ylabel(text["error"], fontsize=9)
    bottom.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 3, 5, 7, 9, 11)))
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(bottom.get_xticklabels(), rotation=0, fontsize=9)

    figure.tight_layout()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, dpi=130, metadata={"Software": None})  # nothing that changes from one run to the next inside the file
    plt.close(figure)
    return target
