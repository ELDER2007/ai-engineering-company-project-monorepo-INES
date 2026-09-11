// Placeholder topbar — no auth wired up yet, just the shell (see
// memory-bank/progress.md for what's pending).
export const Topbar = () => (
	<header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
		<h1 className="text-lg font-semibold text-slate-900">Dashboard</h1>
		<div className="flex items-center gap-2 text-sm text-slate-500">
			<span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 text-xs font-semibold text-white">
				N
			</span>
			<span>Equipo Nexova</span>
		</div>
	</header>
);
