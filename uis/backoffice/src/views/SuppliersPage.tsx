"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { ErrorNotice, LoadingNote, SuccessNotice } from "../components/feedback";
import SupplierForm from "../components/suppliers/SupplierForm";
import SupplierRow from "../components/suppliers/SupplierRow";
import { listSuppliers, setSupplierStatus, updateSupplierRate } from "../lib/api";
import { describeError } from "../lib/errors";
import { CATEGORIES, CATEGORY_LABELS, type Category, type Country, type Supplier } from "../types/suppliers";

const selectClass =
  "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-cyan-400 focus:outline-none";

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [country, setCountry] = useState<Country | "">("");
  const [category, setCategory] = useState<Category | "">("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setSuppliers(await listSuppliers());
    } catch (err) {
      setLoadError(describeError(err, "No se pudo cargar el directorio de proveedores."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (updated: Supplier) =>
    setSuppliers((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));

  const handleRateChange = async (id: number, rate: number) => {
    setError(null);
    setNotice(null);
    try {
      replace(await updateSupplierRate(id, rate));
      setNotice("Tarifa actualizada.");
    } catch (err) {
      setError(describeError(err, "No se pudo actualizar la tarifa. Revisa el importe e inténtalo de nuevo."));
      throw err;
    }
  };

  const handleToggleStatus = async (supplier: Supplier) => {
    setError(null);
    setNotice(null);
    try {
      replace(await setSupplierStatus(supplier.id, supplier.status === "active" ? "suspended" : "active"));
      setNotice("Estado actualizado.");
    } catch (err) {
      setError(describeError(err, "No se pudo cambiar el estado del proveedor. Inténtalo de nuevo."));
      throw err;
    }
  };

  const visible = useMemo(
    () =>
      suppliers.filter(
        (s) => (!country || s.country === country) && (!category || s.categories.includes(category)),
      ),
    [suppliers, country, category],
  );

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Directorio de proveedores</h1>
          <p className="mt-2 text-slate-400">Registro único de servicios externos contratados por Nexova.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
        >
          <Plus size={16} />
          Nuevo proveedor
        </button>
      </header>

      {showForm && (
        <div className="mt-6">
          <SupplierForm
            onCancel={() => setShowForm(false)}
            onCreated={(created) => {
              setSuppliers((prev) => [...prev, created]);
              setShowForm(false);
              setError(null);
              setNotice("Proveedor creado.");
            }}
          />
        </div>
      )}

      <div className="mt-8 flex flex-wrap gap-3">
        <select aria-label="Filtrar por país" value={country} onChange={(e) => setCountry(e.target.value as Country | "")} className={selectClass}>
          <option value="">Todos los países</option>
          <option value="Spain">Spain</option>
          <option value="USA">USA</option>
        </select>
        <select aria-label="Filtrar por categoría" value={category} onChange={(e) => setCategory(e.target.value as Category | "")} className={selectClass}>
          <option value="">Todas las categorías</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABELS[c]}
            </option>
          ))}
        </select>
        <p className="self-center text-sm text-slate-500">{visible.length} proveedores</p>
      </div>

      {error && (
        <div className="mt-6">
          <ErrorNotice message={error} />
        </div>
      )}
      {notice && !error && (
        <div className="mt-6">
          <SuccessNotice message={notice} />
        </div>
      )}

      {loading ? (
        <div className="mt-8">
          <LoadingNote label="Cargando proveedores…" />
        </div>
      ) : loadError ? (
        <div className="mt-8">
          <ErrorNotice message={loadError} onRetry={() => void load()} home />
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900">
          <table className="w-full text-left">
            <thead className="text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-3">Proveedor</th>
                <th className="px-4 py-3">País</th>
                <th className="px-4 py-3">Categorías</th>
                <th className="px-4 py-3">Tarifa mensual</th>
                <th className="px-4 py-3">Renovación</th>
                <th className="px-4 py-3">Estado</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <SupplierRow key={s.id} supplier={s} onRateChange={handleRateChange} onToggleStatus={handleToggleStatus} />
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">
                    No hay proveedores con esos filtros.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
