import { listAssets } from "../../lib/inventory";
import { describeInventoryError } from "../../lib/inventoryRules";
import { useAsyncResource } from "../../lib/useAsyncResource";
import type { Section } from "../../lib/telemetry/events";
import type { Asset } from "../../types/inventory";

const NO_ASSETS: Asset[] = [];
const describeLoadError = (err: unknown) => describeInventoryError(err, "No se pudo cargar el inventario.");

/**
 * The assets with their current stock, loaded on mount (reported as the load of `section`, for the pages that
 * are a section of their own: the stock list, the entry and the exit form). `reload` reads them again without touching the screen (after
 * registering an order); `retry` is for the "Reintentar" button after a failure (see `useAsyncResource`).
 */
export function useAssets(section?: Section) {
  const { data, loading, error, reload, retry } = useAsyncResource(listAssets, NO_ASSETS, describeLoadError, section);
  return { assets: data, loading, error, reload, retry };
}
