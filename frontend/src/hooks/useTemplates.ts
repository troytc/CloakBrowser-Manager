import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  api,
  type TemplateDeleteBlockedError,
  type VendorTemplate,
  type VendorTemplateCreateData,
} from "../lib/api";

export interface DeleteBlockedState {
  templateId: string;
  vendorType: string;
  blockingIds: string[];
}

/**
 * Runtime type guard for the 409 delete-blocked response body.
 *
 * Backend (backend/routers/templates.py) raises:
 *   HTTPException(status_code=409, detail={
 *     "detail": "Template has N attached profile(s); ...",
 *     "blocking_profile_ids": [...]
 *   })
 *
 * FastAPI serializes that as the wire body
 *   {"detail": {"detail": "...", "blocking_profile_ids": [...]}}
 *
 * We accept the flat shape too (Plan 04's <interfaces> contract describes
 * a flat body) so the modal works under either convention.
 */
function isDeleteBlockedBody(body: unknown): body is TemplateDeleteBlockedError {
  if (typeof body !== "object" || body === null) {
    return false;
  }
  // Flat shape: { detail: "...", blocking_profile_ids: [...] }
  if (
    "blocking_profile_ids" in body &&
    Array.isArray((body as { blocking_profile_ids: unknown }).blocking_profile_ids)
  ) {
    return true;
  }
  // FastAPI HTTPException(detail=dict) shape:
  // { detail: { detail: "...", blocking_profile_ids: [...] } }
  const inner = (body as { detail?: unknown }).detail;
  if (
    typeof inner === "object" &&
    inner !== null &&
    "blocking_profile_ids" in inner &&
    Array.isArray((inner as { blocking_profile_ids: unknown }).blocking_profile_ids)
  ) {
    return true;
  }
  return false;
}

/**
 * Result of useTemplates.remove. The caller branches on `blocked` to decide
 * whether to unmount the Edit-Template form. This sidesteps the stale-closure
 * hazard from reading `deleteBlocked` after `await remove(id)` resolves
 * (BL-02 / 01-VERIFICATION.md gap[0]).
 */
export type RemoveTemplateResult =
  | { blocked: true; blockingIds: string[] }
  | { blocked: false };

/** Pull the blocking_profile_ids array out of either supported 409 body shape. */
function readBlockingIds(body: unknown): string[] {
  if (typeof body !== "object" || body === null) {
    return [];
  }
  const flat = (body as { blocking_profile_ids?: unknown }).blocking_profile_ids;
  if (Array.isArray(flat)) {
    return flat.filter((x): x is string => typeof x === "string");
  }
  const inner = (body as { detail?: unknown }).detail;
  if (typeof inner === "object" && inner !== null) {
    const nested = (inner as { blocking_profile_ids?: unknown }).blocking_profile_ids;
    if (Array.isArray(nested)) {
      return nested.filter((x): x is string => typeof x === "string");
    }
  }
  return [];
}

export function useTemplates() {
  const [templates, setTemplates] = useState<VendorTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteBlocked, setDeleteBlocked] = useState<DeleteBlockedState | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.templates.list();
      setTemplates(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    // Poll every 3 seconds (matches useProfiles.ts)
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  const create = useCallback(
    async (data: VendorTemplateCreateData): Promise<VendorTemplate | undefined> => {
      try {
        const t = await api.templates.create(data);
        setTemplates((prev) => [t, ...prev]);
        setError(null);
        return t;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create template");
        return undefined;
      }
    },
    [],
  );

  const update = useCallback(
    async (
      id: string,
      data: Partial<VendorTemplateCreateData>,
    ): Promise<VendorTemplate | undefined> => {
      try {
        const t = await api.templates.update(id, data);
        setTemplates((prev) => prev.map((x) => (x.id === id ? t : x)));
        setError(null);
        return t;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update template");
        return undefined;
      }
    },
    [],
  );

  const remove = useCallback(
    async (id: string): Promise<RemoveTemplateResult> => {
      const existing = templates.find((t) => t.id === id);
      try {
        await api.templates.remove(id);
        setTemplates((prev) => prev.filter((x) => x.id !== id));
        setError(null);
        return { blocked: false };
      } catch (err) {
        // 409 delete-blocked with structured body → populate deleteBlocked AND
        // signal the caller via the return value so it does not unmount the form.
        if (err instanceof ApiError && err.status === 409 && isDeleteBlockedBody(err.body)) {
          const blockingIds = readBlockingIds(err.body);
          setDeleteBlocked({
            templateId: id,
            vendorType: existing?.vendor_type ?? "?",
            blockingIds,
          });
          return { blocked: true, blockingIds };
        }
        setError(err instanceof Error ? err.message : "Failed to delete template");
        // Non-409 errors are NOT delete-blocked. The caller is free to unmount;
        // the error banner surfaces the failure separately.
        return { blocked: false };
      }
    },
    [templates],
  );

  const dismissDeleteBlocked = useCallback(() => setDeleteBlocked(null), []);

  return {
    templates,
    loading,
    error,
    refresh,
    create,
    update,
    remove,
    deleteBlocked,
    dismissDeleteBlocked,
  };
}
