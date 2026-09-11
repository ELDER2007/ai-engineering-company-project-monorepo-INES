// "Contacto" section — literal contact details from CONTEXT.md.
const CONTACT_ITEMS = [
	{ label: "Email", value: "contacto@nexova.com", href: "mailto:contacto@nexova.com" },
	{ label: "Valencia", value: "+34 960 123 456", href: "tel:+34960123456" },
	{ label: "Miami", value: "+1 305 555 0191", href: "tel:+13055550191" },
];

export const Contact = () => (
	<section id="contacto" className="mx-auto max-w-4xl px-6 py-20 text-center">
		<h2 className="text-3xl font-bold text-slate-900">Contacto</h2>
		<dl className="mt-10 grid gap-8 sm:grid-cols-3">
			{CONTACT_ITEMS.map((item) => (
				<div key={item.label}>
					<dt className="text-sm font-medium uppercase tracking-wide text-slate-500">
						{item.label}
					</dt>
					<dd className="mt-2">
						<a href={item.href} className="font-medium text-brand-700 hover:text-brand-900">
							{item.value}
						</a>
					</dd>
				</div>
			))}
		</dl>
	</section>
);
