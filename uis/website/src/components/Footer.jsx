// Footer section from CONTEXT.md: literal copyright line + social links.
export const Footer = () => (
	<footer className="border-t border-slate-200 bg-slate-900 py-8 text-center text-sm text-slate-300">
		<p>&copy; 2025 Nexova. Todos los derechos reservados.</p>
		<div className="mt-3 flex justify-center gap-6">
			<a
				href="https://linkedin.com/company/nexova"
				target="_blank"
				rel="noreferrer"
				className="hover:text-white"
			>
				LinkedIn
			</a>
			<a
				href="https://instagram.com/nexova"
				target="_blank"
				rel="noreferrer"
				className="hover:text-white"
			>
				Instagram
			</a>
		</div>
	</footer>
);
