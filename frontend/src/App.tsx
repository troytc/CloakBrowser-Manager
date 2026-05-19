import { useState, useCallback, useEffect } from "react";
import { Lock, PanelLeftClose, PanelLeft } from "lucide-react";
import { useSessions } from "./hooks/useSessions";
import { useTemplates } from "./hooks/useTemplates";
import { api, setOnUnauthorized, type VendorTemplateCreateData } from "./lib/api";
import type { AdminSessionListItem } from "./lib/api";
import { ProfileViewer } from "./components/ProfileViewer";
import { StatusIndicator } from "./components/StatusIndicator";
import { LoginPage } from "./components/LoginPage";
import { TemplateList } from "./components/TemplateList";
import { TemplateForm } from "./components/TemplateForm";
import { DeleteBlockedModal } from "./components/DeleteBlockedModal";
import { SessionList } from "./components/SessionList";

type AuthState = "checking" | "required" | "ok" | "error";
type Surface = "sessions" | "templates";
type SessionView = "empty" | "view" | "detail";
type TemplateView = "empty" | "create" | "edit";

export default function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    setOnUnauthorized(() => setAuthState("required"));

    api.authStatus()
      .then(({ auth_required, authenticated }) => {
        setAuthRequired(auth_required);
        if (!auth_required || authenticated) {
          setAuthState("ok");
        } else {
          setAuthState("required");
        }
      })
      .catch((err) => {
        console.warn("[auth] status check failed:", err);
        setAuthState("error");
      });

    return () => setOnUnauthorized(null);
  }, []);

  if (authState === "checking") {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (authState === "error") {
    return (
      <div className="h-screen flex items-center justify-center bg-surface-0">
        <div className="text-center">
          <p className="text-red-400 text-sm mb-2">Unable to reach the server</p>
          <button
            onClick={() => {
              setAuthState("checking");
              api.authStatus()
                .then(({ auth_required, authenticated }) => {
                  setAuthRequired(auth_required);
                  setAuthState(!auth_required || authenticated ? "ok" : "required");
                })
                .catch(() => setAuthState("error"));
            }}
            className="text-xs text-gray-400 hover:text-gray-200 underline"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (authState === "required") {
    return <LoginPage onSuccess={() => setAuthState("ok")} />;
  }

  return (
    <AppContent
      authRequired={authRequired}
      onLogout={async () => {
        await api.logout();
        setAuthState("required");
      }}
    />
  );
}

interface AppContentProps {
  authRequired: boolean;
  onLogout: () => void;
}

function AppContent({ authRequired, onLogout }: AppContentProps) {
  const { sessions, loading: sessionsLoading, error: sessionsError } = useSessions();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionView, setSessionView] = useState<SessionView>("empty");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [surface, setSurface] = useState<Surface>("sessions");

  const [templateView, setTemplateView] = useState<TemplateView>("empty");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);

  const {
    templates,
    loading: templatesLoading,
    error: templatesError,
    create: createTemplate,
    update: updateTemplate,
    remove: removeTemplate,
    deleteBlocked,
    dismissDeleteBlocked,
  } = useTemplates();

  const selectedSession: AdminSessionListItem | null =
    selectedSessionId
      ? sessions.find((s) => s.profile_id === selectedSessionId) ?? null
      : null;

  const selectedTemplate = selectedTemplateId
    ? templates.find((t) => t.id === selectedTemplateId) ?? null
    : null;

  const handleSelectSession = useCallback((profileId: string) => {
    setSelectedSessionId(profileId);
    const row = sessions.find((s) => s.profile_id === profileId);
    if (row?.state === "running" || row?.state === "idle") {
      setSessionView("view");
    } else {
      setSessionView("detail");
    }
  }, [sessions]);

  const handleCreateTemplate = async (data: VendorTemplateCreateData) => {
    const result = await createTemplate(data);
    if (result) {
      setSelectedTemplateId(null);
      setTemplateView("empty");
    }
    return result;
  };

  const handleUpdateTemplate = async (data: VendorTemplateCreateData) => {
    if (!selectedTemplateId) return undefined;
    const result = await updateTemplate(selectedTemplateId, data);
    if (result) {
      setSelectedTemplateId(null);
      setTemplateView("empty");
    }
    return result;
  };

  const handleDeleteTemplateFromForm = async () => {
    if (!selectedTemplateId) return;
    const result = await removeTemplate(selectedTemplateId);
    if (!result.blocked) {
      setSelectedTemplateId(null);
      setTemplateView("empty");
    }
  };

  if (sessionsLoading && surface === "sessions" && sessions.length === 0) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex">
      {sidebarOpen && (
        <div className="w-72 border-r border-border bg-surface-1 flex-shrink-0 flex flex-col">
          {surface === "sessions" ? (
            <SessionList
              sessions={sessions}
              loading={sessionsLoading}
              selectedId={selectedSessionId}
              onSelect={handleSelectSession}
            />
          ) : (
            <TemplateList
              templates={templates}
              loading={templatesLoading}
              onCreate={() => {
                setSelectedTemplateId(null);
                setTemplateView("create");
              }}
              onEdit={(id) => {
                setSelectedTemplateId(id);
                setTemplateView("edit");
              }}
              onDelete={(id) => removeTemplate(id)}
            />
          )}
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface-1">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="text-gray-500 hover:text-gray-300 p-1"
              title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            >
              {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
            </button>
            <div className="flex items-center gap-1 bg-surface-2 rounded-md p-0.5">
              <button
                type="button"
                onClick={() => {
                  setSurface("sessions");
                  setSessionView("empty");
                }}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${surface === "sessions"
                  ? "bg-surface-3 text-gray-100"
                  : "text-gray-400 hover:text-gray-200"
                  }`}
              >
                Sessions
              </button>
              <button
                type="button"
                onClick={() => {
                  setSurface("templates");
                  setSelectedTemplateId(null);
                  setTemplateView("empty");
                }}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${surface === "templates"
                  ? "bg-surface-3 text-gray-100"
                  : "text-gray-400 hover:text-gray-200"
                  }`}
              >
                Templates
              </button>
            </div>
            {surface === "sessions" && selectedSession && (
              <div className="flex items-center gap-2">
                <StatusIndicator
                  status={selectedSession.state === "stopped" ? "stopped" : "running"}
                  size="md"
                />
                <span className="text-sm font-medium text-gray-200">
                  {selectedSession.vendor_type}
                </span>
                <span className="text-xs text-gray-500">
                  {selectedSession.vendor_connection_id}
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {authRequired && (
              <button
                onClick={onLogout}
                className="text-gray-500 hover:text-gray-300 p-1"
                title="Log out"
              >
                <Lock className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {(surface === "sessions" ? sessionsError : templatesError) && (
          <div className="px-4 py-2 bg-red-600/15 border-b border-red-600/30 text-red-400 text-sm">
            {surface === "sessions" ? sessionsError : templatesError}
          </div>
        )}

        <div className="flex-1 overflow-y-auto overscroll-contain">
          {surface === "sessions" && (
            <>
              {sessionView === "empty" && (
                <div className="flex items-center justify-center h-full">
                  <p className="text-gray-500 text-sm">Select a session</p>
                </div>
              )}
              {sessionView === "detail" && selectedSession && (
                <div className="max-w-lg mx-auto p-8 space-y-4">
                  <h2 className="text-lg font-semibold text-gray-100">Session stopped</h2>
                  <p className="text-sm text-gray-400">
                    Wake this profile via the Main App <code className="text-gray-300">POST /sessions</code>{" "}
                    with vendor <strong>{selectedSession.vendor_type}</strong> and connection{" "}
                    <strong>{selectedSession.vendor_connection_id}</strong>.
                  </p>
                  <dl className="text-sm grid grid-cols-2 gap-2 text-gray-400">
                    <dt>State</dt>
                    <dd className="capitalize text-gray-200">{selectedSession.state}</dd>
                    <dt>CDP attaches</dt>
                    <dd>{selectedSession.cdp_attach_count}</dd>
                    <dt>Viewer attaches</dt>
                    <dd>{selectedSession.viewer_attach_count}</dd>
                  </dl>
                </div>
              )}
              {sessionView === "view" && selectedSession && (selectedSession.state === "running" || selectedSession.state === "idle") && (
                <ProfileViewer
                  key={selectedSession.profile_id}
                  profileId={selectedSession.profile_id}
                  cdpUrl={null}
                  clipboardSync={selectedSession.clipboard_sync}
                  onDisconnect={() => setSessionView("detail")}
                />
              )}
            </>
          )}

          {surface === "templates" && (
            <>
              {templateView === "empty" && (
                <div className="h-full">
                  <TemplateList
                    templates={templates}
                    loading={templatesLoading}
                    onCreate={() => {
                      setSelectedTemplateId(null);
                      setTemplateView("create");
                    }}
                    onEdit={(id) => {
                      setSelectedTemplateId(id);
                      setTemplateView("edit");
                    }}
                    onDelete={(id) => removeTemplate(id)}
                  />
                </div>
              )}
              {templateView === "create" && (
                <TemplateForm
                  template={null}
                  onSave={handleCreateTemplate}
                  onCancel={() => setTemplateView("empty")}
                />
              )}
              {templateView === "edit" && selectedTemplate && (
                <TemplateForm
                  template={selectedTemplate}
                  onSave={handleUpdateTemplate}
                  onDelete={handleDeleteTemplateFromForm}
                  onCancel={() => {
                    setSelectedTemplateId(null);
                    setTemplateView("empty");
                  }}
                />
              )}
            </>
          )}

          {deleteBlocked && (
            <DeleteBlockedModal
              vendorType={deleteBlocked.vendorType}
              blockingIds={deleteBlocked.blockingIds}
              onClose={dismissDeleteBlocked}
            />
          )}
        </div>
      </div>
    </div>
  );
}
