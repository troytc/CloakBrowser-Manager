import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { ApiError } from "../lib/api";
import { useTemplates } from "./useTemplates";

// Mock the api.templates namespace. vitest does not auto-mock; every function
// the hook touches must be declared here.
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      templates: {
        list: vi.fn(),
        get: vi.fn(),
        create: vi.fn(),
        update: vi.fn(),
        remove: vi.fn(),
      },
    },
  };
});

import { api } from "../lib/api";

const mockTemplatesApi = (api as unknown as {
  templates: {
    list: ReturnType<typeof vi.fn>;
    get: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
  };
}).templates;

const fakeTemplate = {
  id: "tpl-1",
  vendor_type: "shopify",
  label: "Shopify",
  notes: null,
  blueprint: {
    timezone: null,
    locale: null,
    platform: "windows" as const,
    user_agent: null,
    screen_width: 1920,
    screen_height: 1080,
    color_scheme: null,
    gpu_vendor: null,
    gpu_renderer: null,
    hardware_concurrency: null,
    humanize: false,
    human_preset: "default" as const,
    launch_args: [],
    clipboard_sync: false,
    proxy: null,
  },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  // Revision 2 (WARNING #3): neutralise the useTemplates polling setInterval(refresh, 3000)
  // so a mid-test poll cannot race the test's assertion that `error` was set by `remove`.
  // vi.useFakeTimers() freezes the fake clock; we then use
  // `await act(async () => { vi.advanceTimersByTime(100); })` to flush initial load
  // microtasks without advancing 3000ms (so the polling interval never fires).
  vi.useFakeTimers();
  mockTemplatesApi.list.mockResolvedValue([fakeTemplate]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Flush the initial mount load: advance fake clock 100ms (< 3000ms poll interval)
 * inside act() so that Promise microtasks for api.templates.list resolve and
 * setLoading(false) is committed to React state before assertions begin.
 */
async function flushInitialLoad(result: { current: { loading: boolean } }) {
  await act(async () => {
    vi.advanceTimersByTime(100);
  });
  // Sanity: if load didn't settle, subsequent assertions will fail with clear messages.
  if (result.current.loading) {
    throw new Error("useTemplates did not finish initial load after 100ms fake-time advance");
  }
}

describe("useTemplates.remove discriminated-union return (BL-02)", () => {
  it("returns { blocked: false } on successful delete and removes the row", async () => {
    mockTemplatesApi.remove.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useTemplates());
    await flushInitialLoad(result);
    expect(result.current.templates).toHaveLength(1);

    let outcome: { blocked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.remove("tpl-1");
    });

    expect(outcome).toEqual({ blocked: false });
    expect(result.current.templates).toHaveLength(0);
    expect(result.current.deleteBlocked).toBeNull();
  });

  it("returns { blocked: true, blockingIds } on 409 with FLAT body and sets deleteBlocked", async () => {
    mockTemplatesApi.remove.mockRejectedValue(
      new ApiError(409, "Template has 2 attached profile(s); delete or reassign them first", {
        detail: "Template has 2 attached profile(s); delete or reassign them first",
        blocking_profile_ids: ["p1", "p2"],
      }),
    );

    const { result } = renderHook(() => useTemplates());
    await flushInitialLoad(result);

    let outcome: { blocked: boolean; blockingIds?: string[] } | undefined;
    await act(async () => {
      outcome = (await result.current.remove("tpl-1")) as {
        blocked: true;
        blockingIds: string[];
      };
    });

    expect(outcome).toEqual({ blocked: true, blockingIds: ["p1", "p2"] });
    expect(result.current.templates).toHaveLength(1); // not removed
    expect(result.current.deleteBlocked).toEqual({
      templateId: "tpl-1",
      vendorType: "shopify",
      blockingIds: ["p1", "p2"],
    });
  });

  it("returns { blocked: true, blockingIds } on 409 with FastAPI NESTED body shape", async () => {
    mockTemplatesApi.remove.mockRejectedValue(
      new ApiError(409, "Template has 1 attached profile(s); delete or reassign them first", {
        detail: {
          detail: "Template has 1 attached profile(s); delete or reassign them first",
          blocking_profile_ids: ["p3"],
        },
      }),
    );

    const { result } = renderHook(() => useTemplates());
    await flushInitialLoad(result);

    let outcome: { blocked: boolean; blockingIds?: string[] } | undefined;
    await act(async () => {
      outcome = (await result.current.remove("tpl-1")) as {
        blocked: true;
        blockingIds: string[];
      };
    });

    expect(outcome).toEqual({ blocked: true, blockingIds: ["p3"] });
    expect(result.current.deleteBlocked?.blockingIds).toEqual(["p3"]);
  });

  it("returns { blocked: false } on non-409 error and surfaces error message", async () => {
    mockTemplatesApi.remove.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useTemplates());
    await flushInitialLoad(result);

    let outcome: { blocked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.remove("tpl-1");
    });

    expect(outcome).toEqual({ blocked: false });
    expect(result.current.templates).toHaveLength(1); // not removed
    expect(result.current.deleteBlocked).toBeNull();
    expect(result.current.error).toBe("Network error");
  });
});
