"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Pencil } from "lucide-react";
import { CATEGORY_LABELS, ORIGIN_LABELS, SCORE_LABELS, type Incident, type IncidentFacets } from "@repo/shared-types";
import { ErrorBanner } from "../components/incidents/Field";
import { LoadingNote, SectionBoundary, SuccessNotice } from "../components/feedback";
import HistoryTimeline from "../components/incidents/HistoryTimeline";
import IncidentForm from "../components/incidents/IncidentForm";
import StatusActions from "../components/incidents/StatusActions";
import StatusBadge from "../components/incidents/StatusBadge";
import { getIncident, getIncidentFacets } from "../lib/api";
import { describeError, isNotFound } from "../lib/errors";
import { formatDateTime, labelOf, MISSING } from "../lib/format";

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-200">{children}</dd>
    </div>
  );
}

export default function IncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [facets, setFacets] = useState<IncidentFacets>({ branches: [], clients: [], agents: [] });
  const [facetsFailed, setFacetsFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const loaded = await getIncident(incidentId);
      setIncident(loaded);
      setNotFound(false);
      setError(null);
    } catch (err) {
      if (isNotFound(err)) setNotFound(true);
      else setError(describeError(err, "No se pudo cargar la incidencia."));
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    // Another incident (the address changed): never show the previous one while this one loads.
    setIncident(null);
    setNotFound(false);
    setError(null);
    setEditing(false);
    void load();
    void (async () => {
      try {
        setFacets(await getIncidentFacets());
        setFacetsFailed(false);
      } catch (err) {
        // Only the suggestions of the edit form are missing: the incident itself is shown, and the person is told.
        console.warn("[incidents] the filter options could not be loaded", err);
        setFacetsFailed(true);
      }
    })();
  }, [load]);

  const back = (
    <Link href="/incidents" className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white">
      <ArrowLeft size={16} />
      Volver a incidencias
    </Link>
  );

  if (loading && !incident) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        {back}
        <LoadingNote label="Cargando la incidencia…" />
      </div>
    );
  }
  if (notFound) {
    return (
      <div className="mx-auto max-w-4xl">
        {back}
        <h1 className="mt-6 text-2xl font-bold text-white">Incidencia no encontrada</h1>
        <p className="mt-2 text-slate-400">No existe ninguna incidencia con el identificador {incidentId}.</p>
      </div>
    );
  }
  if (!incident) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        {back}
        <ErrorBanner message={error ?? "No se pudo cargar la incidencia."} onRetry={() => void load()} />
      </div>
    );
  }

  const handleSaved = (updated: Incident, message: string) => {
    setIncident(updated);
    setEditing(false);
    setError(null);
    setNotice(message);
  };

  const handleConflict = async () => {
    setEditing(false);
    await load();
    setError("La incidencia había cambiado de estado; mostramos los datos actuales.");
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {back}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-3xl font-bold text-white">
            {incident.id}
            <StatusBadge status={incident.status} />
          </h1>
          <p className="mt-2 text-lg text-slate-300">{incident.title || MISSING}</p>
        </div>
        {incident.editable && !editing && (
          <button type="button" onClick={() => setEditing(true)} className="flex items-center gap-2 rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:text-white">
            <Pencil size={14} />
            Editar
          </button>
        )}
      </header>

      {notice && <SuccessNotice message={notice} />}
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {loading && <LoadingNote label="Actualizando…" />}
      {!incident.editable && (
        <p className="text-sm text-slate-500">Las incidencias resueltas o descartadas no se pueden editar. Reábrela para modificarla.</p>
      )}

      {editing ? (
        <>
          {facetsFailed && (
            <p role="status" className="text-xs text-amber-300">
              No se pudieron cargar las sugerencias de sucursal, cliente y agente; puedes escribirlos a mano.
            </p>
          )}
          <IncidentForm
            incident={incident}
            agents={facets.agents}
            branches={facets.branches}
            clients={facets.clients}
            onSaved={(updated) => handleSaved(updated, "Cambios guardados.")}
            onCancel={() => setEditing(false)}
          />
        </>
      ) : (
        <SectionBoundary name="los datos de la incidencia">
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <dl className="grid gap-5 sm:grid-cols-2">
              <Detail label="Creada">{formatDateTime(incident.created_at)}</Detail>
              <Detail label="Última modificación">{formatDateTime(incident.updated_at)}</Detail>
              <Detail label="Categoría">{labelOf(CATEGORY_LABELS, incident.category)}</Detail>
              <Detail label="Origen">{labelOf(ORIGIN_LABELS, incident.origin)}</Detail>
              <Detail label="Sucursal">{incident.branch || MISSING}</Detail>
              <Detail label="Empresa cliente">{incident.client_company ?? MISSING}</Detail>
              <Detail label="Agente">{incident.agent_id ?? MISSING}</Detail>
              <Detail label="Email del cliente">{incident.customer_email ?? MISSING}</Detail>
              <div className="sm:col-span-2">
                <Detail label="Descripción">{incident.description || MISSING}</Detail>
              </div>
              {incident.satisfaction_score != null && (
                <Detail label="Satisfacción">
                  {incident.satisfaction_score} / 5 · {labelOf(SCORE_LABELS as Record<string, string>, String(incident.satisfaction_score))}
                </Detail>
              )}
              {incident.discard_reason && <Detail label="Motivo del descarte">{incident.discard_reason}</Detail>}
            </dl>
          </section>
        </SectionBoundary>
      )}

      <SectionBoundary name="las acciones de estado">
        <StatusActions
          incident={incident}
          onChanged={(updated) => handleSaved(updated, "Estado actualizado.")}
          onConflict={() => void handleConflict()}
        />
      </SectionBoundary>
      <SectionBoundary name="el historial">
        <HistoryTimeline history={incident.history} />
      </SectionBoundary>
    </div>
  );
}
