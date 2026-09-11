import { Outlet } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { Topbar } from "../components/Topbar";

// Backoffice shell: a sidebar + topbar admin layout — distinct from
// uis/website's Layout (public Header + Footer). Kept in its own file so
// the two apps never share a layout component.
export const Layout = () => (
	<div className="flex min-h-screen bg-slate-50">
		<Sidebar />
		<div className="flex flex-1 flex-col">
			<Topbar />
			<main className="flex-1 p-6">
				<Outlet />
			</main>
		</div>
	</div>
);
