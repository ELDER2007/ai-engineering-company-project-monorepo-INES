import PropTypes from "prop-types";

// Reusable card for one item of the "Servicios" 3-column section.
export const ServiceCard = ({ title, bullets }) => (
	<div className="rounded-lg border border-slate-200 p-6">
		<h3 className="text-lg font-semibold text-slate-900">{title}</h3>
		<ul className="mt-3 space-y-2 text-sm text-slate-600">
			{bullets.map((bullet) => (
				<li key={bullet} className="flex gap-2">
					<span aria-hidden="true" className="text-brand-600">•</span>
					<span>{bullet}</span>
				</li>
			))}
		</ul>
	</div>
);

ServiceCard.propTypes = {
	title: PropTypes.string.isRequired,
	bullets: PropTypes.arrayOf(PropTypes.string).isRequired,
};
