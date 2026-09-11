import { StatCard } from "./StatCard";

// "Por qué Nexova" section — literal from CONTEXT.md. Note: the brief itself
// says "mercado latinoamericano" while the company profile places Nexova in
// Valencia/Miami — kept verbatim per CONTEXT.md, see memory-bank/techContext.md.
const REASONS = [
	<>
		<strong>12 años de experiencia</strong> en el mercado latinoamericano
	</>,
	<>
		<strong>Presencia regional:</strong> España y Estados Unidos
	</>,
	<>
		<strong>+500 procesos exitosos</strong> de selección completados
	</>,
	<>
		<strong>Especialización sectorial</strong> en tecnología, retail y finanzas
	</>,
];

export const WhyNexova = () => (
	<section id="por-que-nexova" className="bg-slate-50 py-20">
		<div className="mx-auto max-w-4xl px-6">
			<h2 className="text-center text-3xl font-bold text-slate-900">Por qué Nexova</h2>
			<div className="mt-12 grid gap-4 sm:grid-cols-2">
				{REASONS.map((reason, index) => (
					<StatCard key={index} text={reason} />
				))}
			</div>
		</div>
	</section>
);
