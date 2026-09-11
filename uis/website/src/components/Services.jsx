import { ServiceCard } from "./ServiceCard";

// "Servicios" section — the 3 columns are literal from CONTEXT.md.
const SERVICES = [
	{
		title: "Headhunting Ejecutivo",
		bullets: [
			"Búsqueda y selección de perfiles ejecutivos y mandos medios",
			"Proceso personalizado con garantía de reemplazo",
		],
	},
	{
		title: "Outsourcing de Atención al Cliente",
		bullets: [
			"Equipos especializados para empresas tecnológicas",
			"Formación continua y supervisión dedicada",
		],
	},
	{
		title: "Formación Corporativa",
		bullets: [
			"Programas de soft skills y liderazgo",
			"Cursos presenciales y en línea adaptados a cada organización",
		],
	},
];

export const Services = () => (
	<section id="servicios" className="mx-auto max-w-6xl px-6 py-20">
		<h2 className="text-center text-3xl font-bold text-slate-900">Servicios</h2>
		<div className="mt-12 grid gap-6 md:grid-cols-3">
			{SERVICES.map((service) => (
				<ServiceCard key={service.title} {...service} />
			))}
		</div>
	</section>
);
