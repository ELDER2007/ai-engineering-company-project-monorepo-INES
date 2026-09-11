import { NavLink } from "react-router-dom";

// Sidebar navigation. Only "Dashboard" is a real route today; the other
// items map to the future backoffice modules described in
// ../../../README.md (people/candidate management, vacancies, training) —
// shown disabled so the intended structure is visible without overbuilding.
const NAV_ITEMS = [
	{ label: "Dashboard", to: "/", enabled: true },
	{ label: "Candidatos", enabled: false },
	{ label: "Vacantes", enabled: false },
	{ label: "Formación", enabled: false },
];

export const Sidebar = () => (
	<aside className="flex w-60 shrink-0 flex-col bg-ink-950 text-slate-300">
		<div className="px-6 py-5 text-lg font-bold text-white">Nexova</div>
		<nav aria-label="Secciones del backoffice" className="flex-1 px-3">
			<ul className="space-y-1">
				{NAV_ITEMS.map((item) =>
					item.enabled ? (
						<li key={item.label}>
							<NavLink
								to={item.to}
								end
								className={({ isActive }) =>
									`block rounded-md px-3 py-2 text-sm font-medium ${
										isActive
											? "bg-accent-600 text-white"
											: "text-slate-300 hover:bg-ink-800 hover:text-white"
									}`
								}
							>
								{item.label}
							</NavLink>
						</li>
					) : (
						<li key={item.label}>
							<span
								className="flex cursor-not-allowed items-center justify-between rounded-md px-3 py-2 text-sm text-slate-500"
								title="Próximamente"
							>
								{item.label}
								<span className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
									Próx.
								</span>
							</span>
						</li>
					)
				)}
			</ul>
		</nav>
	</aside>
);
