import { useState, useCallback, useEffect } from "react";
import { Lock, PanelLeftClose, PanelLeft } from "lucide-react";
import { useProfiles } from "./hooks/useProfiles";
import { useTemplates } from "./hooks/useTemplates";
import { api, setOnUnauthorized, type ProfileCreateData } from "./lib/api";
import type { VendorTemplateCreateData } from "./lib/api";
import { ProfileList } from "./components/ProfileList";
import { ProfileForm } from "./components/ProfileForm";
import { ProfileViewer } from "./components/ProfileViewer";
import { LaunchButton } from "./components/LaunchButton";
import { StatusIndicator } from "./components/StatusIndicator";
import { LoginPage } from "./components/LoginPage";
import { TemplateList } from "./components/TemplateList";
import { TemplateForm } from "./components/TemplateForm";
import { DeleteBlockedModal } from "./components/DeleteBlockedModal";

type AuthState = "checking" | "required" | "ok" | "error";
type View = "empty" | "create" | "edit" | "view";
type Surface = "profiles" | "templates";
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
  const { profiles, loading, error, create, update, remove, launch, stop } = useProfiles();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<View>("empty");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [surface, setSurface] = useState<Surface>("profiles");
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

  const selectedTemplate = selectedTemplateId
    ? templates.find((t) => t.id === selectedTemplateId) ?? null
    : null;

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
    // BL-02 fix: branch on the returned discriminated union, not on the
    // `deleteBlocked` closure (which reads the prior render's value).
    // When blocked, leave selectedTemplateId/templateView unchanged so the
    // form stays mounted under DeleteBlockedModal.
    if (!result.blocked) {
      setSelectedTemplateId(null);
      setTemplateView("empty");
    }
  };

  const selected = profiles.find((p) => p.id === selectedId) ?? null;

  const handleSelect = useCallback((id: string) => {
    setSelectedId(id);
    const profile = profiles.find((p) => p.id === id);
    setView(profile?.status === "running" ? "view" : "edit");
  }, [profiles]);

  const handleNew = useCallback(() => {
    setSelectedId(null);
    setView("create");
  }, []);

  const handleCreate = useCallback(async (data: ProfileCreateData) => {
    const profile = await create(data);
    if (profile) {
      setSelectedId(profile.id);
      setView("edit");
    }
  }, [create]);

  const handleUpdate = useCallback(async (data: ProfileCreateData) => {
    if (!selectedId) return;
    await update(selectedId, data);
  }, [selectedId, update]);

  const handleDelete = useCallback(async () => {
    if (!selectedId) return;
    await remove(selectedId);
    setSelectedId(null);
    setView("empty");
  }, [selectedId, remove]);

  const handleLaunch = useCallback(async () => {
    if (!selectedId) return;
    const result = await launch(selectedId);
    if (result) setView("view");
  }, [selectedId, launch]);

  const handleStop = useCallback(async () => {
    if (!selectedId) return;
    await stop(selectedId);
    setView("edit");
  }, [selectedId, stop]);

  const handleVncDisconnect = useCallback(() => {
    setView("edit");
  }, []);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex">
      {/* Sidebar */}
      {sidebarOpen && (
        <div className="w-64 border-r border-border bg-surface-1 flex-shrink-0">
          <ProfileList
            profiles={profiles}
            selectedId={selectedId}
            onSelect={handleSelect}
            onNew={handleNew}
          />
        </div>
      )}

      {/* Main panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
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
                onClick={() => setSurface("profiles")}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  surface === "profiles"
                    ? "bg-surface-3 text-gray-100"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                Profiles
              </button>
              <button
                type="button"
                onClick={() => {
                  setSurface("templates");
                  setSelectedTemplateId(null);
                  setTemplateView("empty");
                }}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  surface === "templates"
                    ? "bg-surface-3 text-gray-100"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                Templates
              </button>
            </div>
            {selected && (
              <div className="flex items-center gap-2">
                <StatusIndicator status={selected.status} size="md" />
                <span className="text-sm font-medium">{selected.name}</span>
                <span className="text-xs text-gray-500 capitalize">{selected.platform}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {selected && (
              <LaunchButton
                status={selected.status}
                onLaunch={handleLaunch}
                onStop={handleStop}
              />
            )}
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

        {/* Error banner */}
        {(surface === "profiles" ? error : templatesError) && (
          <div className="px-4 py-2 bg-red-600/15 border-b border-red-600/30 text-red-400 text-sm">
            {surface === "profiles" ? error : templatesError}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {surface === "profiles" && (
            <>
              {view === "empty" && (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <p className="text-gray-500 text-sm">Select a profile or create a new one</p>
                  </div>
                </div>
              )}

              {view === "create" && (
                <ProfileForm
                  profile={null}
                  onSave={handleCreate}
                  onCancel={() => setView("empty")}
                />
              )}

              {view === "edit" && selected && (
                <ProfileForm
                  profile={selected}
                  onSave={handleUpdate}
                  onDelete={handleDelete}
                  onCancel={() => {
                    setSelectedId(null);
                    setView("empty");
                  }}
                />
              )}

              {view === "view" && selected && selected.status === "running" && (
                <ProfileViewer
                  key={selected.id}
                  profileId={selected.id}
                  cdpUrl={selected.cdp_url}
                  clipboardSync={selected.clipboard_sync}
                  onDisconnect={handleVncDisconnect}
                />
              )}
            </>
          )}

          {surface === "templates" && (
            <>
              {templateView === "empty" && (
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
