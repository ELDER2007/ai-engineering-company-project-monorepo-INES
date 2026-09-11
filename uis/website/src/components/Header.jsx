import { useState } from "react";
import { Link } from "react-router-dom";
import PropTypes from "prop-types";

// Header section from CONTEXT.md: logo/name "Nexova" + nav
// Inicio | Servicios | Talento | Contacto.
const NAV_LINKS = [
	{ label: "Inicio", to: "/" },
	{ label: "Servicios", href: "#servicios" },
	{ label: "Talento", to: "/talento" },
	{ label: "Contacto", href: "#contacto" },
];

const NavLink = ({ link, onClick }) =>
	link.href ? (
		<a
			href={link.href}
			onClick={onClick}
			className="text-sm font-medium text-slate-600 hover:text-brand-700"
		>
			{link.label}
		</a>
	) : (
		<Link
			to={link.to}
			onClick={onClick}
			className="text-sm font-medium text-slate-600 hover:text-brand-700"
		>
			{link.label}
		</Link>
	);

NavLink.propTypes = {
	link: PropTypes.shape({
		label: PropTypes.string.isRequired,
		to: PropTypes.string,
		href: PropTypes.string,
	}).isRequired,
	onClick: PropTypes.func,
};

export const Header = () => {
	const [open, setOpen] = useState(false);

	return (
		<header className="sticky top-0 z-50 border-b border-slate-200 bg-white/90 backdrop-blur">
			<nav
				aria-label="Principal"
				className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4"
			>
				<Link to="/" className="text-xl font-bold tracking-tight text-brand-800">
					Nexova
				</Link>

				<ul className="hidden items-center gap-8 md:flex">
					{NAV_LINKS.map((link) => (
						<li key={link.label}>
							<NavLink link={link} />
						</li>
					))}
				</ul>

				<button
					type="button"
					className="rounded-md p-2 text-slate-600 hover:bg-slate-100 md:hidden"
					aria-label={open ? "Cerrar menú" : "Abrir menú"}
					aria-expanded={open}
					onClick={() => setOpen((v) => !v)}
				>
					<span className="sr-only">Menú</span>
					<svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
						{open ? (
							<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
						) : (
							<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
						)}
					</svg>
				</button>
			</nav>

			{open && (
				<ul className="flex flex-col gap-1 border-t border-slate-200 bg-white px-6 py-4 md:hidden">
					{NAV_LINKS.map((link) => (
						<li key={link.label}>
							<NavLink link={link} onClick={() => setOpen(false)} />
						</li>
					))}
				</ul>
			)}
		</header>
	);
};
