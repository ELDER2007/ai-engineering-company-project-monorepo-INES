// Small derived-data logic over ../data/company.js — real computation, not
// a second copy of literal text, so it stays correct as time passes.

/** Years Nexova has been operating, computed from its founding year. */
export function getYearsInOperation(foundingYear, today = new Date()) {
	return today.getFullYear() - foundingYear;
}

/** Compact currency formatting, e.g. 8_000_000 -> "$8M". */
export function formatCompactUSD(amount) {
	return new Intl.NumberFormat("es-ES", {
		style: "currency",
		currency: "USD",
		notation: "compact",
		maximumFractionDigits: 1,
	}).format(amount);
}

/** Compact thousands formatting, e.g. 120 -> "120". */
export function formatCount(amount) {
	return new Intl.NumberFormat("es-ES").format(amount);
}
