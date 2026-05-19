import type { AdminSessionListItem } from "../lib/api";
import { StatusIndicator } from "./StatusIndicator";

export interface SessionListProps {
  sessions: AdminSessionListItem[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (profileId: string) => void;
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SessionList({
  sessions,
  loading,
  selectedId,
  onSelect,
}: SessionListProps) {
  if (loading && sessions.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500 text-sm">Loading sessions…</div>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <p className="text-sm text-gray-500">
          No profiles yet. The Main App creates sessions via POST /sessions.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Sessions
        </h2>
      </div>
      <ul className="flex-1 overflow-y-auto divide-y divide-border">
        {sessions.map((s) => {
          const active = s.profile_id === selectedId;
          const displayState =
            s.state === "idle" ? "running" : s.state === "stopped" ? "stopped" : "running";
          return (
            <li key={s.profile_id}>
              <button
                type="button"
                onClick={() => onSelect(s.profile_id)}
                className={`w-full text-left px-3 py-2.5 transition-colors ${active ? "bg-surface-3" : "hover:bg-surface-2"
                  }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <StatusIndicator status={displayState} size="sm" />
                  <span className="text-sm font-medium text-gray-200 truncate">
                    {s.vendor_type || s.name}
                  </span>
                </div>
                <p className="text-xs text-gray-500 truncate pl-5">
                  {s.vendor_connection_id || "—"}
                </p>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 pl-5 text-[10px] text-gray-500">
                  <span className="capitalize">{s.state}</span>
                  <span>CDP {s.cdp_attach_count}</span>
                  <span>Viewer {s.viewer_attach_count}</span>
                  <span>{formatUptime(s.uptime_seconds)}</span>
                </div>
                <p className="text-[10px] text-gray-600 pl-5 mt-0.5">
                  {formatWhen(s.last_launched_at)}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
