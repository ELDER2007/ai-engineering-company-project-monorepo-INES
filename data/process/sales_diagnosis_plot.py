"""The pictures of the diagnosis: learning curve, complexity curve and cross-validation by year. They draw the numbers of the diagnosis report.

Every sentence of a picture that states a result (headlines, panel notes, shaded folds) is built from the numbers given, never typed by hand, so a picture
cannot say something its data does not show. Text is always written in ink, never in the colour of a line; the colours were checked for colour blindness.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

FILES = {"en": "diagnosis_curves.png", "es": "diagnosis_curves.es.png"}
LEARNING_CURVE_FILES = {"en": "learning_curve.png", "es": "learning_curve.es.png"}
LEARNING_TEXTS = {
    "en": {
        "eyebrow": "LEARNING CURVE  ·  NEXOVA'S SALES FORECAST",
        "headline": "With {months} months of history, validation error is still {ratio:.1f} times the training error",
        "subtitle": "RMSE of revenue_usd as the training set grows  ·  Random Forest  ·  training years only (2016-2023)  ·  mean of {blocks} validation blocks",
        "flat": "From {start} to {end} months, validation error falls only {fall:.1f}",
        "short_training": "Training",
        "short_validation": "Validation",
        "short_no_model": "No model",
        "training": "Training error",
        "validation": "Validation error",
        "band": "± 1 standard deviation across the {blocks} validation blocks",
        "no_model": "No model, same blocks: {value:.1f} thousand USD",
        "gap": "gap {value:.1f}",
        "x": "Size of the training set (months)",
        "y": "RMSE of revenue_usd (thousand USD)",
        "source": "Every size is validated on the same {blocks} blocks of 12 months ({first} to {last}, overlapping) and learns the months right before each one.\n"
                  "Same settings at every size. Source: data/raw/nexova_sales.csv. The test years 2024-2025 are not used. Random seed 42.",
    },
    "es": {
        "eyebrow": "CURVA DE APRENDIZAJE  ·  PRONÓSTICO DE VENTAS DE NEXOVA",
        "headline": "Con {months} meses de historia, el error de validación aún es {ratio:.1f} veces el de entrenamiento",
        "subtitle": "RMSE de revenue_usd al crecer el entrenamiento  ·  Random Forest  ·  solo años de entrenamiento (2016-2023)  ·  media de {blocks} bloques de validación",
        "flat": "De {start} a {end} meses, el error de validación solo baja {fall:.1f}",
        "short_training": "Entrenamiento",
        "short_validation": "Validación",
        "short_no_model": "Sin modelo",
        "training": "Error de entrenamiento",
        "validation": "Error de validación",
        "band": "± 1 desviación estándar entre los {blocks} bloques de validación",
        "no_model": "Sin modelo, mismos bloques: {value:.1f} mil USD",
        "gap": "brecha {value:.1f}",
        "x": "Tamaño del conjunto de entrenamiento (meses)",
        "y": "RMSE de revenue_usd (miles de USD)",
        "source": "Cada tamaño se valida en los mismos {blocks} bloques de 12 meses ({first} a {last}, solapados) y aprende los meses justo anteriores a cada uno.\n"
                  "Mismos ajustes en todos los tamaños. Fuente: data/raw/nexova_sales.csv. Los años de prueba 2024-2025 no se usan. Semilla aleatoria 42.",
    },
}
TEXTS = {
    "en": {
        "eyebrow": "BIAS, VARIANCE AND STABILITY  ·  NEXOVA'S SALES FORECAST  ·  TRAINING YEARS ONLY (2016-2023)",
        "headline": "Validation error goes from {low:.1f} to {high:.1f} thousand USD by block; the no-model rule wins in {lost} of {folds}",
        "learning": "1 · More history",
        "complexity": "2 · Deeper trees",
        "years": "3 · Block by block",
        "learning_note": "Gap: {first:.1f} with {first_size} months, {last:.1f} with {last_size}",
        "complexity_note": "Depth {first} to {last}: training {t0:.1f} to {t1:.1f}, validation {v0:.1f} to {v1:.1f}",
        "years_note": "{folds} cross-validation blocks of 6 months",
        "lost": "Shaded: the no-model rule wins",
        "boundary": "Validation, from the boundary (strict)",
        "training": "Training error",
        "validation": "Validation error (one month ahead)",
        "spread": "Lowest to highest of the validation blocks",
        "no_model": "No model (same month a year before)",
        "x_learning": "Months of training",
        "x_complexity": "Maximum depth of each tree",
        "x_years": "Validation block (year and half)",
        "y": "RMSE of revenue_usd (thousand USD)",
        "unlimited": "no limit",
        "chosen": "model's setting",
        "half": "H",
        "source": "Source: data/raw/nexova_sales.csv. The test years 2024-2025 are not used. Random seed 42.",
    },
    "es": {
        "eyebrow": "SESGO, VARIANZA Y ESTABILIDAD  ·  PRONÓSTICO DE VENTAS DE NEXOVA  ·  SOLO AÑOS DE ENTRENAMIENTO (2016-2023)",
        "headline": "El error de validación va de {low:.1f} a {high:.1f} mil USD según el bloque; la regla sin modelo gana en {lost} de {folds}",
        "learning": "1 · Más historia",
        "complexity": "2 · Árboles más profundos",
        "years": "3 · Bloque a bloque",
        "learning_note": "Brecha: {first:.1f} con {first_size} meses, {last:.1f} con {last_size}",
        "complexity_note": "Profundidad {first} a {last}: entrenamiento {t0:.1f} a {t1:.1f}, validación {v0:.1f} a {v1:.1f}",
        "years_note": "{folds} bloques de validación cruzada de 6 meses",
        "lost": "Sombreado: gana la regla sin modelo",
        "boundary": "Validación desde el límite (estricta)",
        "training": "Error de entrenamiento",
        "validation": "Error de validación (un mes por delante)",
        "spread": "Del menor al mayor de los bloques de validación",
        "no_model": "Sin modelo (mismo mes del año anterior)",
        "x_learning": "Meses de entrenamiento",
        "x_complexity": "Profundidad máxima de cada árbol",
        "x_years": "Bloque validado (año y semestre)",
        "y": "RMSE de revenue_usd (miles de USD)",
        "unlimited": "sin límite",
        "chosen": "ajuste del modelo",
        "half": "S",
        "source": "Fuente: data/raw/nexova_sales.csv. Los años de prueba 2024-2025 no se usan. Semilla aleatoria 42.",
    },
}
TRAINING, VALIDATION = "#257de0", "#f47230"  # checked with a colour-blindness validator; also told apart by marker and by a written name
NO_MODEL = "#666666"  # a reference, not a series of the model: grey and dashed
INK, SECONDARY, GRID, BASELINE, SURFACE = "#191919", "#666666", "#e7e7e7", "#c2c2c2", "#ffffff"
METRIC = "rmse_usd"  # the chosen metric (sales_diagnosis.PRIMARY_METRIC)
THOUSAND = 1000.0
STYLE = {  # applied only while drawing: it changes nothing outside this module
    "font.family": "DejaVu Sans",  # ships with matplotlib: the same picture on every machine
    "text.color": INK, "axes.labelcolor": SECONDARY, "axes.edgecolor": BASELINE, "xtick.color": SECONDARY, "ytick.color": SECONDARY,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "axes.labelsize": 10, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
}


def _line(axis, x, y, colour, marker, label, **more):
    """A 2 px line with markers ringed in the background colour, so they stay readable where lines cross."""
    options = {"linewidth": 2.0, "markersize": 7.5, "markeredgecolor": SURFACE, "markeredgewidth": 1.4, "solid_capstyle": "round", "solid_joinstyle": "round", "zorder": 3}
    axis.plot(x, y, color=colour, marker=marker, label=label, **{**options, **more})


def _value(axis, x, y, words, offset=(0, 11), align="center", bold=False, size=9.0):
    """A value next to its point, in ink, on a background patch so that no line crosses it."""
    axis.annotate(words, (x, y), textcoords="offset points", xytext=offset, ha=align, va="center", fontsize=size, color=INK, fontweight="bold" if bold else "normal",
                  zorder=5, bbox={"boxstyle": "round,pad=0.16", "facecolor": SURFACE, "edgecolor": "none", "alpha": 0.92})


def _clean(axis):
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0, pad=4)
    axis.tick_params(axis="x", length=3, color=BASELINE)


def _save(figure, path: str | Path, dpi: int) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, dpi=dpi, metadata={"Software": None})  # no version stamp: the same run gives the same bytes
    plt.close(figure)
    return target


def _two_lines(axis, x, curve, text):
    low = [point[f"validation_{METRIC}"]["min"] / THOUSAND for point in curve]
    high = [point[f"validation_{METRIC}"]["max"] / THOUSAND for point in curve]
    axis.fill_between(x, low, high, color=VALIDATION, alpha=0.10, linewidth=0, label=text["spread"])
    means = {part: [point[f"{part}_{METRIC}"]["mean"] / THOUSAND for point in curve] for part in ("training", "validation")}
    _line(axis, x, means["training"], TRAINING, "o", text["training"])
    _line(axis, x, means["validation"], VALIDATION, "s", text["validation"])
    return means


def plot_diagnosis(report: dict, path: str | Path, language: str = "en") -> Path:
    with plt.rc_context(STYLE):
        return _draw_diagnosis(report, path, TEXTS[language])


def _draw_diagnosis(report: dict, path: str | Path, text: dict) -> Path:
    figure, (first, second, third) = plt.subplots(1, 3, figsize=(17, 7.2), sharey=True)

    learning = report["learning_curve"]
    sizes = [point["training_months"] for point in learning]
    means = _two_lines(first, sizes, learning, text)
    first.set_xticks(sizes)
    first.set_xlabel(text["x_learning"])
    first.set_ylabel(text["y"])
    for at in (0, -1):
        _value(first, sizes[at], means["validation"][at], f"{means['validation'][at]:.1f}", (0, 12))
        _value(first, sizes[at], means["training"][at], f"{means['training'][at]:.1f}", (0, -13))
    gaps = [means["validation"][at] - means["training"][at] for at in (0, -1)]
    note_learning = text["learning_note"].format(first=gaps[0], first_size=sizes[0], last=gaps[1], last_size=sizes[-1])

    complexity = report["complexity_curve"]
    positions = list(range(len(complexity)))
    deep = _two_lines(second, positions, complexity, text)
    names = [text["unlimited"] if point["max_depth"] is None else str(point["max_depth"]) for point in complexity]
    second.set_xticks(positions, names)
    second.set_xlabel(text["x_complexity"])
    chosen = next(i for i, point in enumerate(complexity) if point["max_depth"] == report["model_settings"]["max_depth"])
    second.axvline(chosen, color=BASELINE, linewidth=1.2, zorder=1)
    second.text(chosen + 0.1, 0.035, text["chosen"], transform=second.get_xaxis_transform(), fontsize=9, color=SECONDARY)
    for at in (0, -1):
        _value(second, positions[at], deep["validation"][at], f"{deep['validation'][at]:.1f}", (0, 12))
        _value(second, positions[at], deep["training"][at], f"{deep['training'][at]:.1f}", (0, -13))
    note_complexity = text["complexity_note"].format(first=names[0], last=names[-1], t0=deep["training"][0], t1=deep["training"][-1],
                                                    v0=deep["validation"][0], v1=deep["validation"][-1])

    folds = report["cross_validation_all_past"]["folds"]
    where = list(range(len(folds)))
    labels = [f"{fold['validated_months'][2:4]}-{text['half']}{1 if fold['validated_months'][5:7] <= '06' else 2}" for fold in folds]
    lost = [i for i, fold in enumerate(folds) if fold["validation"][METRIC] > fold["no_model"][METRIC]]  # where using no model would have missed less
    for number, i in enumerate(lost):
        third.axvspan(i - 0.42, i + 0.42, color="#191919", alpha=0.055, linewidth=0, zorder=0, label=text["lost"] if number == 0 else None)
    _line(third, where, [fold["no_model"][METRIC] / THOUSAND for fold in folds], NO_MODEL, "^", text["no_model"], linestyle="--", linewidth=1.5, markersize=7)
    _line(third, where, [fold["training"][METRIC] / THOUSAND for fold in folds], TRAINING, "o", text["training"])
    validation = [fold["validation"][METRIC] / THOUSAND for fold in folds]
    _line(third, where, validation, VALIDATION, "s", text["validation"])
    _line(third, where, [fold["validation_from_boundary"][METRIC] / THOUSAND for fold in folds], VALIDATION, "D", text["boundary"],
          linestyle=(0, (1.2, 1.6)), linewidth=1.4, markersize=4.5, markeredgewidth=0.8, zorder=4)
    for at in (min(where, key=validation.__getitem__), max(where, key=validation.__getitem__)):
        _value(third, where[at], validation[at], f"{validation[at]:.1f}", (15, 8), "left", bold=True)
    third.set_xticks(where, labels)
    third.set_xlim(-0.55, len(folds) - 0.45)
    third.set_xlabel(text["x_years"])

    heights = [fold[part][METRIC] / THOUSAND for fold in folds for part in ("validation", "validation_from_boundary", "no_model")]
    heights += [point[f"validation_{METRIC}"]["max"] / THOUSAND for point in learning + complexity]
    top = max(heights) * 1.08
    panels = ((first, text["learning"], note_learning), (second, text["complexity"], note_complexity),
              (third, text["years"], text["years_note"].format(folds=len(folds))))
    for axis, title, note in panels:
        axis.set_ylim(0, top)
        _clean(axis)
        axis.text(0, 1.085, title, transform=axis.transAxes, fontsize=12, fontweight="bold", color=INK)
        axis.text(0, 1.028, note, transform=axis.transAxes, fontsize=9.5, color=SECONDARY)
    figure.subplots_adjust(left=0.048, right=0.992, top=0.72, bottom=0.135, wspace=0.07)

    figure.text(0.008, 0.968, text["eyebrow"], fontsize=9.5, fontweight="bold", color=SECONDARY, va="center")
    figure.text(0.008, 0.922, text["headline"].format(low=min(validation), high=max(validation), lost=len(lost), folds=len(folds)),
                fontsize=17, fontweight="bold", color=INK, va="center")
    entries = {}  # ONE legend for the three panels, above them, so that it never covers a point
    for axis in (first, second, third):
        for handle, label in zip(*axis.get_legend_handles_labels(), strict=True):
            entries.setdefault(label, handle)
    order = [text[key] for key in ("training", "validation", "boundary", "no_model", "spread", "lost") if text[key] in entries]
    figure.legend([entries[label] for label in order], order, loc="center left", bbox_to_anchor=(0.003, 0.853), ncol=3, frameon=False, fontsize=9.5,
                  handlelength=1.9, handletextpad=0.5, columnspacing=2.6, labelcolor=INK)
    figure.text(0.008, 0.025, text["source"], fontsize=8.8, color=SECONDARY)
    return _save(figure, path, dpi=170)


def plot_learning_curve(report: dict, path: str | Path, language: str = "en") -> Path:
    """The learning curve on its own: training and validation error against the size of the training set."""
    with plt.rc_context(STYLE):
        return _draw_learning_curve(report, path, LEARNING_TEXTS[language])


def _draw_learning_curve(report: dict, path: str | Path, text: dict) -> Path:
    curve, measured = report["learning_curve"], report["learning_curve_measured_on"]
    sizes = [point["training_months"] for point in curve]
    blocks = len(measured["blocks"])
    figure, axis = plt.subplots(figsize=(11.6, 7.4))
    means = {}
    for part, colour, marker in (("training", TRAINING, "o"), ("validation", VALIDATION, "s")):
        stats = [point[f"{part}_{METRIC}"] for point in curve]
        means[part] = [item["mean"] / THOUSAND for item in stats]
        axis.fill_between(sizes, [(m["mean"] - m["std"]) / THOUSAND for m in stats], [(m["mean"] + m["std"]) / THOUSAND for m in stats], color=colour, alpha=0.11, linewidth=0)
        _line(axis, sizes, means[part], colour, marker, text[part], linewidth=2.4, markersize=8.5)
    reference = measured[f"no_model_{METRIC}"]["mean"] / THOUSAND
    axis.axhline(reference, color=NO_MODEL, linestyle="--", linewidth=1.4, label=text["no_model"].format(value=reference), zorder=2)
    axis.fill_between([], [], [], color="#999999", alpha=0.22, label=text["band"].format(blocks=blocks))

    # selective values: where it starts, where the improvement slows down (24 months, if measured) and where it ends
    middle = sizes.index(24) if 24 in sizes[1:-1] else None
    for at in [0, *([middle] if middle is not None else []), len(sizes) - 1]:
        if at != len(sizes) - 1:
            _value(axis, sizes[at], means["validation"][at], f"{means['validation'][at]:.1f}", (0, 14), bold=True, size=10)
            _value(axis, sizes[at], means["training"][at], f"{means['training'][at]:.1f}", (0, -16), bold=True, size=10)
    step = sizes[1] - sizes[0] if len(sizes) > 1 else 6
    for part in ("training", "validation"):  # the two series are named at the end of their line, with their last value
        _value(axis, sizes[-1], means[part][-1], f"{text[f'short_{part}']}\n{means[part][-1]:.1f}", (13, 0), "left", bold=True, size=10)
    _value(axis, sizes[-1], reference, f"{text['short_no_model']}\n{reference:.1f}", (13, 0), "left", size=10)

    for at, side in ((0, 1), (len(sizes) - 1, -1)):  # the gap at the two ends: how much it closes
        low, high = means["training"][at], means["validation"][at]
        axis.annotate("", (sizes[at], high - 1.4), (sizes[at], low + 1.4), arrowprops={"arrowstyle": "<->", "color": SECONDARY, "linewidth": 1.0}, zorder=2)
        axis.text(sizes[at] + side * 0.55, (low + high) / 2, text["gap"].format(value=high - low), fontsize=10, color=INK, ha="left" if side > 0 else "right", va="center")

    top = max([reference] + [(p[f"validation_{METRIC}"]["mean"] + p[f"validation_{METRIC}"]["std"]) / THOUSAND for p in curve]) * 1.1
    if middle is not None:  # the bracket over the part of the curve where more history changes little
        height = (reference + max(means["validation"][middle:]) ) / 2 + 2.2
        axis.plot([sizes[middle], sizes[middle], sizes[-1], sizes[-1]], [height - 0.9, height, height, height - 0.9], color=SECONDARY, linewidth=1.0, zorder=2)
        axis.text((sizes[middle] + sizes[-1]) / 2, height + 2.0,
                  text["flat"].format(start=sizes[middle], end=sizes[-1], fall=means["validation"][middle] - means["validation"][-1]),
                  ha="center", va="center", fontsize=10, color=INK, zorder=5, bbox={"boxstyle": "round,pad=0.2", "facecolor": SURFACE, "edgecolor": "none", "alpha": 0.92})
    axis.set_xticks(sizes)
    axis.set_xlim(sizes[0] - 0.4 * step, sizes[-1] + 0.12 * step)
    axis.set_ylim(0, top)
    axis.set_xlabel(text["x"], labelpad=7)
    axis.set_ylabel(text["y"], labelpad=7)
    _clean(axis)
    figure.subplots_adjust(left=0.068, right=0.865, top=0.775, bottom=0.158)

    figure.text(0.012, 0.968, text["eyebrow"], fontsize=9.5, fontweight="bold", color=SECONDARY, va="center")
    figure.text(0.012, 0.924, text["headline"].format(months=sizes[-1], ratio=means["validation"][-1] / means["training"][-1]),
                fontsize=15.5, fontweight="bold", color=INK, va="center")
    figure.text(0.012, 0.882, text["subtitle"].format(blocks=blocks), fontsize=9.4, color=SECONDARY, va="center")
    axis.legend(loc="lower left", bbox_to_anchor=(-0.068, 1.025), bbox_transform=axis.transAxes, ncol=2, frameon=False, fontsize=9.5, labelcolor=INK,
                handlelength=1.9, handletextpad=0.5, columnspacing=2.2)
    first, last = measured["blocks"][0].split(" to ")[0], measured["blocks"][-1].split(" to ")[1]
    figure.text(0.012, 0.027, text["source"].format(blocks=blocks, first=first, last=last), fontsize=8.8, color=SECONDARY, linespacing=1.5)
    return _save(figure, path, dpi=200)
