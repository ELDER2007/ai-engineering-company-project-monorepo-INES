import PropTypes from "prop-types";

// Reusable card for one item of the "Por qué Nexova" 2-column section.
export const StatCard = ({ text }) => (
	<div className="rounded-lg bg-brand-50 p-6">
		<p className="font-medium text-slate-800">{text}</p>
	</div>
);

StatCard.propTypes = {
	text: PropTypes.node.isRequired,
};
