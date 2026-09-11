import { Hero } from "../components/Hero";
import { Services } from "../components/Services";
import { WhyNexova } from "../components/WhyNexova";
import { Contact } from "../components/Contact";

// Landing page — section order fixed by CONTEXT.md: Header (in Layout) →
// Hero → Servicios → Por qué Nexova → Contacto → Footer (in Layout).
export const Home = () => (
	<>
		<Hero />
		<Services />
		<WhyNexova />
		<Contact />
	</>
);
