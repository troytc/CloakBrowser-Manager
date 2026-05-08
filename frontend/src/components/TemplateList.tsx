import { Pencil, Plus, Trash2 } from "lucide-react";
import type { VendorTemplate } from "../lib/api";

export interface TemplateListProps {
  templates: VendorTemplate[];
  loading: boolean;
  onCreate: () => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function TemplateList({
  templates,
  loading,
  onCreate,
  onEdit,
  onDelete,
}: TemplateListProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-6 text-center">
        <h2 className="text-lg font-semibold text-gray-200 mb-2">
          No templates yet
        </h2>
        <p className="text-sm text-gray-500 max-w-md mb-4">
          Create your first vendor template to start provisioning profiles.
        </p>
        <button
          onClick={onCreate}
          className="btn-primary flex items-center gap-1.5"
          type="button"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          <span>New Template</span>
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b border-border">
        <h2 className="text-lg font-semibold text-gray-100">Templates</h2>
        <button
          onClick={onCreate}
          className="btn-primary flex items-center gap-1.5"
          type="button"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          <span>New Template</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <table className="w-full">
          <thead className="bg-surface-1 sticky top-0">
            <tr className="border-b border-border">
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Vendor Type
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Label
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Created
              </th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr
                key={t.id}
                className="border-b border-border hover:bg-surface-2 transition-colors"
              >
                <td className="px-4 py-2.5 font-mono text-sm text-gray-100">
                  {t.vendor_type}
                </td>
                <td className="px-4 py-2.5 text-sm text-gray-200">
                  {t.label || "—"}
                </td>
                <td className="px-4 py-2.5 text-xs text-gray-500">
                  {formatRelative(t.created_at)}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => onEdit(t.id)}
                      className="btn-secondary flex items-center gap-1.5"
                      type="button"
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>Edit</span>
                    </button>
                    <button
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete template "${t.label || t.vendor_type}"? This cannot be undone.`,
                          )
                        ) {
                          onDelete(t.id);
                        }
                      }}
                      className="btn-danger flex items-center gap-1.5"
                      type="button"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>Delete</span>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
