import { CompanySnapshot } from "../components/CompanySnapshot";

// "/" — entry view. Just a welcome header plus the one populated widget for
// now; every other module (candidatos, vacantes, ...) is still an empty
// slot in the sidebar.
export const Dashboard = () => (
	<div className="space-y-6">
		<div>
			<h2 className="text-2xl font-bold text-slate-900">Bienvenido al backoffice de Nexova</h2>
			<p className="mt-1 text-slate-600">
				Este panel está en construcción — por ahora solo muestra un resumen de la empresa.
			</p>
		</div>

		<CompanySnapshot />
	</div>
);
