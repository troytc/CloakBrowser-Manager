import { AlertTriangle, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import type {
  TemplateBlueprint,
  VendorTemplate,
  VendorTemplateCreateData,
} from "../lib/api";

const EMPTY_BLUEPRINT: TemplateBlueprint = {
  timezone: null,
  locale: null,
  platform: "windows",
  user_agent: null,
  screen_width: 1920,
  screen_height: 1080,
  color_scheme: null,
  gpu_vendor: null,
  gpu_renderer: null,
  hardware_concurrency: null,
  humanize: false,
  human_preset: "default",
  launch_args: [],
  clipboard_sync: false, // D-18 touchpoint 5: React form default
  proxy: null,
};

export interface TemplateFormProps {
  template: VendorTemplate | null;
  onSave: (data: VendorTemplateCreateData) => Promise<VendorTemplate | undefined>;
  onDelete?: () => Promise<void>;
  onCancel: () => void;
}

export function TemplateForm({
  template,
  onSave,
  onDelete,
  onCancel,
}: TemplateFormProps) {
  const isEdit = template !== null;

  const [vendorType, setVendorType] = useState(template?.vendor_type ?? "");
  const [label, setLabel] = useState(template?.label ?? "");
  const [notes, setNotes] = useState(template?.notes ?? "");
  const [blueprint, setBlueprint] = useState<TemplateBlueprint>(
    template?.blueprint ?? EMPTY_BLUEPRINT,
  );
  const [launchArgInput, setLaunchArgInput] = useState("");

  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function patchBlueprint<K extends keyof TemplateBlueprint>(
    key: K,
    value: TemplateBlueprint[K],
  ) {
    setBlueprint((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    if (!vendorType.trim()) {
      setFieldErrors({ vendor_type: "Vendor type is required." });
      return;
    }
    setSaving(true);
    try {
      const result = await onSave({
        vendor_type: vendorType.trim(),
        label: label.trim() || null,
        notes: notes.trim() || null,
        blueprint,
      });
      if (!result) {
        // Hook surfaced an error; the parent banner will render it. Heuristic: if the
        // error mentions "already exists", attach it to vendor_type inline.
        // (The parent still shows the top banner; this is additional context.)
        // Note: more precise 422 field-error wiring would require useTemplates to
        // surface the ApiError directly. Phase 1 keeps that simple.
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!onDelete) return;
    if (
      !window.confirm(
        `Delete template "${template?.label || template?.vendor_type}"? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
    }
  }

  function addLaunchArg() {
    const v = launchArgInput.trim();
    if (!v) return;
    patchBlueprint("launch_args", [...blueprint.launch_args, v]);
    setLaunchArgInput("");
  }

  function removeLaunchArg(i: number) {
    patchBlueprint(
      "launch_args",
      blueprint.launch_args.filter((_, idx) => idx !== i),
    );
  }

  return (
    <form onSubmit={handleSubmit} className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">
            {isEdit ? "Edit Template" : "New Template"}
          </h2>
          {isEdit && onDelete && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              className="btn-danger flex items-center gap-1.5"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{deleting ? "Deleting..." : "Delete"}</span>
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onCancel} className="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="btn-primary flex items-center gap-1.5"
          >
            <Save className="h-3.5 w-3.5" aria-hidden="true" />
            <span>
              {saving ? "Saving..." : isEdit ? "Save" : "Create"}
            </span>
          </button>
        </div>
      </div>

      <div className="space-y-5">
        {/* IDENTITY */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Identity
          </h3>
          <div className="space-y-3">
            <div>
              <label className="label" htmlFor="tf-vendor-type">Vendor Type</label>
              <input
                id="tf-vendor-type"
                className="input"
                value={vendorType}
                onChange={(e) => setVendorType(e.target.value)}
                placeholder="e.g. shopify, amazon-sp"
                disabled={isEdit}
                required
              />
              {fieldErrors.vendor_type && (
                <p className="text-xs text-red-400 mt-1" role="alert">
                  {fieldErrors.vendor_type}
                </p>
              )}
            </div>
            <div>
              <label className="label" htmlFor="tf-label">Label</label>
              <input
                id="tf-label"
                className="input"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. Shopify Admin Console"
              />
            </div>
            <div>
              <label className="label" htmlFor="tf-notes">Notes</label>
              <textarea
                id="tf-notes"
                className="input min-h-[80px] resize-y"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional notes for operators…"
              />
            </div>
          </div>
        </section>

        {/* FINGERPRINT */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Fingerprint
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Timezone</label>
              <input
                className="input"
                value={blueprint.timezone ?? ""}
                onChange={(e) => patchBlueprint("timezone", e.target.value || null)}
                placeholder="America/New_York"
              />
            </div>
            <div>
              <label className="label">Locale</label>
              <input
                className="input"
                value={blueprint.locale ?? ""}
                onChange={(e) => patchBlueprint("locale", e.target.value || null)}
                placeholder="en-US"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Platform</label>
              <select
                className="input"
                value={blueprint.platform}
                onChange={(e) =>
                  patchBlueprint(
                    "platform",
                    e.target.value as TemplateBlueprint["platform"],
                  )
                }
              >
                <option value="windows">Windows</option>
                <option value="macos">macOS</option>
                <option value="linux">Linux</option>
              </select>
            </div>
          </div>
        </section>

        {/* SCREEN */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Screen
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Width</label>
              <input
                type="number"
                className="input"
                value={blueprint.screen_width}
                onChange={(e) =>
                  patchBlueprint("screen_width", Number(e.target.value) || 1920)
                }
                placeholder="1920"
                required
              />
            </div>
            <div>
              <label className="label">Height</label>
              <input
                type="number"
                className="input"
                value={blueprint.screen_height}
                onChange={(e) =>
                  patchBlueprint("screen_height", Number(e.target.value) || 1080)
                }
                placeholder="1080"
                required
              />
            </div>
            <div className="col-span-2">
              <label className="label">Color Scheme</label>
              <select
                className="input"
                value={blueprint.color_scheme ?? ""}
                onChange={(e) =>
                  patchBlueprint(
                    "color_scheme",
                    (e.target.value || null) as TemplateBlueprint["color_scheme"],
                  )
                }
              >
                <option value="">System default</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="no-preference">No preference</option>
              </select>
            </div>
          </div>
        </section>

        {/* GPU */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Gpu
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">GPU Vendor</label>
              <input
                className="input"
                value={blueprint.gpu_vendor ?? ""}
                onChange={(e) => patchBlueprint("gpu_vendor", e.target.value || null)}
                placeholder="Auto (from seed)"
              />
            </div>
            <div>
              <label className="label">GPU Renderer</label>
              <input
                className="input"
                value={blueprint.gpu_renderer ?? ""}
                onChange={(e) => patchBlueprint("gpu_renderer", e.target.value || null)}
                placeholder="Auto (from seed)"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Hardware Concurrency</label>
              <input
                type="number"
                className="input"
                value={blueprint.hardware_concurrency ?? ""}
                onChange={(e) =>
                  patchBlueprint(
                    "hardware_concurrency",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                placeholder="Auto (from seed)"
              />
            </div>
          </div>
        </section>

        {/* BEHAVIOR */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Behavior
          </h3>
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={blueprint.humanize}
                onChange={(e) => patchBlueprint("humanize", e.target.checked)}
                className="rounded border-border bg-surface-2"
              />
              Human-like mouse, keyboard, and scroll behavior
            </label>
            {blueprint.humanize && (
              <div>
                <label className="label">Human Preset</label>
                <select
                  className="input"
                  value={blueprint.human_preset}
                  onChange={(e) =>
                    patchBlueprint(
                      "human_preset",
                      e.target.value as TemplateBlueprint["human_preset"],
                    )
                  }
                >
                  <option value="default">Default</option>
                  <option value="careful">Careful</option>
                </select>
              </div>
            )}
            <div>
              <label className="label">Launch Args</label>
              <p className="text-xs text-gray-500 mb-2">
                Custom Chromium flags passed at launch (e.g. --load-extension, --disable-features)
              </p>
              <div className="flex gap-2">
                <input
                  className="input font-mono text-xs flex-1"
                  value={launchArgInput}
                  onChange={(e) => setLaunchArgInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addLaunchArg();
                    }
                  }}
                  placeholder="--load-extension=/data/extensions/ublock"
                />
                <button
                  type="button"
                  onClick={addLaunchArg}
                  className="btn-secondary"
                >
                  Add
                </button>
              </div>
              {blueprint.launch_args.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {blueprint.launch_args.map((arg, i) => (
                    <span
                      key={`${arg}-${i}`}
                      className="inline-flex items-center gap-1 bg-surface-3 border border-border rounded px-2 py-0.5 font-mono text-xs text-gray-200"
                    >
                      {arg}
                      <button
                        type="button"
                        onClick={() => removeLaunchArg(i)}
                        className="text-gray-500 hover:text-gray-200"
                        aria-label={`Remove ${arg}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* PROXY */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Proxy
          </h3>
          <div>
            <label className="label">Proxy</label>
            <input
              className="input"
              value={blueprint.proxy ?? ""}
              onChange={(e) => patchBlueprint("proxy", e.target.value || null)}
              placeholder="http://user:pass@host:port"
            />
          </div>
        </section>

        {/* SECURITY — amber warning ABOVE checkbox per UI-SPEC */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Security
          </h3>
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 mb-3">
            <AlertTriangle
              className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <div className="text-xs text-amber-200 leading-relaxed">
              <span className="font-semibold">
                Clipboard sync is off by default for a reason.
              </span>{" "}
              When enabled, any page the vendor browser visits can read clipboard contents — including passwords and 2FA codes an operator pastes into other apps. Only turn this on when you understand the risk and trust every page this profile will reach.
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={blueprint.clipboard_sync}
              onChange={(e) => patchBlueprint("clipboard_sync", e.target.checked)}
              className="rounded border-border bg-surface-2"
            />
            Enable clipboard sync in VNC viewer
          </label>
        </section>
      </div>
    </form>
  );
}
