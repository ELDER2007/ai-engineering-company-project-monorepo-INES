import {
    createBrowserRouter,
    createRoutesFromElements,
    Route,
} from "react-router-dom";
import { Layout } from "./pages/Layout";
import { Dashboard } from "./pages/Dashboard";

// Only "/" exists today — the dashboard shell. Future modules (candidatos,
// vacantes, autenticación, comunicación interna — see uis/README.md) get
// their own nested routes here as they're built.
export const router = createBrowserRouter(
    createRoutesFromElements(
      <Route path="/" element={<Layout />} errorElement={<h1>Not found!</h1>}>
        <Route path="/" element={<Dashboard />} />
      </Route>
    )
);
