"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import {
  EMPTY_FILTERS,
  type Incident,
  type IncidentFacets,
  type IncidentFilters,
  type IncidentPage,
  type IncidentSummary,
} from "@repo/shared-types";
import IncidentFiltersBar from "../components/incidents/IncidentFilters";
import IncidentForm from "../components/incidents/IncidentForm";
import IncidentSummaryPanel from "../components/incidents/IncidentSummaryPanel";
import IncidentTable from "../components/incidents/IncidentTable";
import { ErrorBanner } from "../components/incidents/Field";
import { ErrorNotice, LoadingNote, SectionBoundary, SuccessNotice } from "../components/feedback";
import {
  getIncidentFacets,
  getIncidentSummary,
  listIncidents,
  type SortField,
  type SortOrder,
} from "../lib/api";
import { describeError } from "../lib/errors";

const PAGE_SIZE = 15;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export default function IncidentsPage() {
  const [filters, setFilters] = useState<IncidentFilters>(EMPTY_FILTERS);
  const [sort, setSort] = useState<SortField>("created_at");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);

  const [list, setList] = useState<IncidentPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The summary is loaded on its own: if it fails, the list keeps working (and the other way round).
  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [facets, setFacets] = useState<IncidentFacets>({ branches: [], clients: [], agents: [] });
  const [facetsFailed, setFacetsFailed] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Typing in the search box must not fire a request per keystroke.
  const applied = useDebounced(filters, 300);
  const rangeInvalid = !!applied.date_from && !!applied.date_to && applied.date_from > applied.date_to;
  const hasFilters = JSON.stringify(applied) !== JSON.stringify(EMPTY_FILTERS);

  // Only the latest request may write state: a slow older answer must not overwrite a newer one.
  const latestList = useRef(0);
  const latestSummary = useRef(0);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    if (rangeInvalid) return;
    const request = ++latestList.current;
    setLoading(true);
    void (async () => {
      try {
        const next = await listIncidents(applied, { sort, order, page, pageSize: PAGE_SIZE });
        if (request !== latestList.current) return;
        setList(next);
        setError(null);
        // A page that no longer exists (e.g. after filtering) falls back to the last one.
        if (next.pages > 0 && page > next.pages) setPage(next.pages);
      } catch (err) {
        if (request === latestList.current) setError(describeError(err, "No se pudieron cargar las incidencias."));
      } finally {
        if (request === latestList.current) setLoading(false);
      }
    })();
  }, [applied, sort, order, page, reloadKey, rangeInvalid]);

  useEffect(() => {
    if (rangeInvalid) return;
    const request = ++latestSummary.current;
    setSummaryLoading(true);
    void (async () => {
      try {
        const next = await getIncidentSummary(applied);
        if (request !== latestSummary.current) return;
        setSummary(next);
        setSummaryError(null);
      } catch (err) {
        if (request === latestSummary.current) setSummaryError(describeError(err, "No se pudo cargar el resumen."));
      } finally {
        if (request === latestSummary.current) setSummaryLoading(false);
      }
    })();
  }, [applied, reloadKey, rangeInvalid]);

  useEffect(() => {
    void (async () => {
      try {
        setFacets(await getIncidentFacets());
        setFacetsFailed(false);
      } catch (err) {
        // Only the drop-down suggestions are missing: the list and the filters still work, and the person is told.
        console.warn("[incidents] the filter options could not be loaded", err);
        setFacetsFailed(true);
      }
    })();
  }, [reloadKey]);

  const changeFilters = useCallback((next: IncidentFilters) => {
    setFilters(next);
    setPage(1);
  }, []);

  const handleSort = (field: SortField) => {
    if (field === sort) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(field);
      setOrder(field === "id" ? "asc" : "desc");
    }
    setPage(1);
  };

  const handleCreated = (incident: Incident) => {
    setShowForm(false);
    setNotice(`Incidencia ${incident.id} creada.`);
    setFilters(EMPTY_FILTERS);
    setPage(1);
    setReloadKey((k) => k + 1);
  };

  const pages = list?.pages ?? 0;
  // What the table shows is from before the last attempt, which failed: it must not pass for the current result.
  const stale = error !== null && list !== null;

  return (
    <div className="mx-auto max-w-7xl">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Incidencias</h1>
          <p className="mt-2 text-slate-400">Gestión centralizada de las incidencias de clientes, sucursales y equipos internos de Nexova.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setShowForm((v) => !v);
            setNotice(null);
          }}
          className="flex items-center gap-2 rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
        >
          <Plus size={16} />
          Nueva incidencia
        </button>
      </header>

      {notice && (
        <div className="mt-6">
          <SuccessNotice message={notice} />
        </div>
      )}

      {showForm && (
        <div className="mt-6">
          <IncidentForm branches={facets.branches} agents={facets.agents} clients={facets.clients} onSaved={handleCreated} onCancel={() => setShowForm(false)} />
        </div>
      )}

      <div className="mt-8">
        <SectionBoundary name="el resumen">
          {summaryError ? (
            <ErrorNotice message={summaryError} onRetry={retry}>
              El resto de la pantalla sigue funcionando.
            </ErrorNotice>
          ) : summary ? (
            <div className={summaryLoading ? "opacity-60 transition" : "transition"}>
              <IncidentSummaryPanel summary={summary} />
            </div>
          ) : summaryLoading ? (
            <LoadingNote label="Cargando el resumen…" />
          ) : null}
        </SectionBoundary>
      </div>

      <div className="mt-8">
        <SectionBoundary name="los filtros">
          <IncidentFiltersBar filters={filters} facets={facets} onChange={changeFilters} />
        </SectionBoundary>
        {facetsFailed && (
          <p role="status" className="mt-2 text-xs text-amber-300">
            No se pudieron cargar las sugerencias de los filtros (sucursales, clientes y agentes); el resto sigue funcionando.
          </p>
        )}
      </div>

      {error && (
        <div className="mt-6">
          <ErrorBanner message={error} onRetry={retry} />
        </div>
      )}

      <div className="mt-6" aria-busy={loading}>
        {list === null && loading ? (
          <LoadingNote label="Cargando incidencias…" />
        ) : list && list.total === 0 && !error ? (
          <p className="rounded-2xl border border-slate-800 bg-slate-900 px-4 py-10 text-center text-sm text-slate-400">
            {hasFilters ? "Ninguna incidencia coincide con estos filtros." : "Todavía no hay incidencias. Crea la primera con «Nueva incidencia»."}
          </p>
        ) : list ? (
          <div className={loading || stale ? "opacity-50 transition" : "transition"}>
            {stale && (
              <p role="status" className="mb-3 text-sm text-amber-300">
                Mostrando el resultado anterior: la última carga ha fallado.
              </p>
            )}
            <SectionBoundary name="la tabla de incidencias">
              <IncidentTable items={list.items} sort={sort} order={order} onSort={handleSort} />
            </SectionBoundary>
            <nav aria-label="Paginación" className="mt-4 flex items-center justify-between text-sm text-slate-400">
              <p>
                {list.total} incidencias · página {list.page} de {pages}
              </p>
              <div className="flex gap-2">
                <button type="button" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)} className="flex items-center gap-1 rounded-full border border-slate-700 px-3 py-1.5 enabled:hover:text-white disabled:opacity-40">
                  <ChevronLeft size={14} /> Anterior
                </button>
                <button type="button" disabled={page >= pages || loading} onClick={() => setPage(page + 1)} className="flex items-center gap-1 rounded-full border border-slate-700 px-3 py-1.5 enabled:hover:text-white disabled:opacity-40">
                  Siguiente <ChevronRight size={14} />
                </button>
              </div>
            </nav>
          </div>
        ) : null}
      </div>
    </div>
  );
}
