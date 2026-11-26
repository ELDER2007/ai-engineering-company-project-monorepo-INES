import { Component, ErrorInfo, ReactNode } from "react";

/** Last safety net: if anything in the page fails to draw, the visitor sees a message and a way out, not a blank screen. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[website] the page could not be shown", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main role="alert" className="mx-auto max-w-xl px-6 py-24 text-center">
        <h1 className="text-3xl font-bold text-white">Algo no ha salido bien</h1>
        <p className="mt-4 text-slate-300">No hemos podido mostrar esta página. Vuelve a intentarlo; si el problema continúa, escríbenos a <a className="text-cyan-300" href="mailto:contacto@nexova.com">contacto@nexova.com</a>.</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-8 rounded-full bg-cyan-400 px-6 py-3 font-semibold text-slate-950 hover:bg-cyan-300">Recargar la página</button>
      </main>
    );
  }
}
