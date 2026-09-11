import { Link } from "react-router-dom";

// Hero section — literal copy from CONTEXT.md.
export const Hero = () => (
	<section className="bg-gradient-to-b from-brand-50 to-white">
		<div className="mx-auto max-w-4xl px-6 py-24 text-center">
			<h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
				Construimos equipos excepcionales para empresas en crecimiento
			</h1>
			<p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
				Consultora de recursos humanos y adquisición de talento con más de 10
				años ayudando a empresas de tecnología, retail y servicios financieros
				a encontrar y desarrollar el mejor talento.
			</p>
			<div className="mt-10">
				<Link
					to="/talento"
					className="inline-block rounded-md bg-brand-700 px-6 py-3 text-base font-semibold text-white shadow-sm hover:bg-brand-800"
				>
					Únete a nuestro banco de talento
				</Link>
			</div>
		</div>
	</section>
);
