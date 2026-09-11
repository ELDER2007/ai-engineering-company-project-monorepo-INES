import { company } from "../data/company";
import { getYearsInOperation, formatCompactUSD, formatCount } from "../lib/companyStats";

// The "logic/data from CONTEXT.md, visible in the UI" fragment: company.js
// holds the literal facts from CONTEXT.md § "Tu empresa"; the years-in-
// operation and currency figures below are computed here, not hardcoded.
const yearsInOperation = getYearsInOperation(company.foundingYear);

const STATS = [
	{ label: "Años operando", value: `${yearsInOperation}` },
	{ label: "Empleados", value: `~${formatCount(company.employeeCount)}` },
	{ label: "Facturación anual", value: `~${formatCompactUSD(company.annualRevenueUSD)}` },
	{ label: "Líneas de negocio", value: `${company.businessLines.length}` },
];

export const CompanySnapshot = () => (
	<section className="rounded-lg border border-slate-200 bg-white p-6">
		<div className="flex flex-wrap items-baseline justify-between gap-2">
			<h2 className="text-base font-semibold text-slate-900">Resumen de {company.name}</h2>
			<p className="text-sm text-slate-500">
				Fundada en {company.foundingYear} · {company.headquarters.city}, {company.headquarters.country} +{" "}
				{company.expansionOffice.city}, {company.expansionOffice.country}
			</p>
		</div>

		<dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
			{STATS.map((stat) => (
				<div key={stat.label} className="rounded-md bg-slate-50 p-4">
					<dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{stat.label}</dt>
					<dd className="mt-1 text-2xl font-bold text-ink-900">{stat.value}</dd>
				</div>
			))}
		</dl>

		<div className="mt-6 grid gap-6 sm:grid-cols-2">
			<div>
				<h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Líneas de negocio</h3>
				<ul className="mt-2 space-y-1 text-sm text-slate-700">
					{company.businessLines.map((line) => (
						<li key={line}>• {line}</li>
					))}
				</ul>
			</div>
			<div>
				<h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Sectores de clientes</h3>
				<div className="mt-2 flex flex-wrap gap-2">
					{company.clientSectors.map((sector) => (
						<span
							key={sector}
							className="rounded-full bg-accent-500/10 px-3 py-1 text-xs font-medium text-accent-600"
						>
							{sector}
						</span>
					))}
				</div>
			</div>
		</div>
	</section>
);
