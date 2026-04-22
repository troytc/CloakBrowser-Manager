---
phase: 1
slug: schema-templates-and-security-foundations
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-22
---

# Phase 1 — UI Design Contract

> Visual and interaction contract for the Templates admin surface added in Phase 1. Locked decisions inherit from `01-CONTEXT.md` (D-10..D-13) and mirror the existing `ProfileForm`/`ProfileList`/`useProfiles` patterns. No new design tokens; the contract is an extraction-and-extension of what `frontend/src/styles/globals.css` and `frontend/tailwind.config.ts` already ship.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (project-native Tailwind + globals.css) |
| Preset | not applicable (brownfield — shadcn not introduced this phase) |
| Component library | none (raw HTML + Tailwind utility classes + `@layer components` helpers) |
| Icon library | `lucide-react` (already a project dep; used throughout `frontend/src/components/`) |
| Font | System stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", system-ui, sans-serif` (verbatim from `globals.css` L12-13) |

**Rationale for no shadcn:** Brownfield project. Existing admin UI (`ProfileForm.tsx`, `ProfileList.tsx`, `ProfileViewer.tsx`) is built on a small, consistent palette via Tailwind config + 6 `@layer components` helpers (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.input`, `.label`). CONTEXT.md D-11 Claude's Discretion locks "no new colors"; introducing shadcn would double the design system. Phase 4 may revisit when the admin dashboard is pivoted.

---

## Spacing Scale

Tailwind's default 4px scale is used verbatim. No overrides in `tailwind.config.ts`. Declared tokens for this phase (all multiples of 4):

| Token | Value | Tailwind class | Usage in Phase 1 UI |
|-------|-------|----------------|---------------------|
| xs | 4px | `gap-1`, `p-1` | Icon-to-label gaps inside badges/buttons |
| sm | 8px | `gap-2`, `p-2`, `space-y-2` | Compact row gaps in table cells, form field pairs |
| md | 12px | `gap-3`, `space-y-3` | Default stacking between inputs within a form section |
| lg | 16px | `p-4`, `gap-4`, `space-y-4` | Sidebar/list padding (matches existing `ProfileList` header) |
| xl | 20px | `space-y-5` | Gap between form sections (matches `ProfileForm` L202) |
| 2xl | 24px | `p-6` | Form page outer padding (matches `ProfileForm` L173) |

**Exceptions:** none. The existing ProfileForm uses this scale end-to-end; TemplateForm MUST match it line-for-line.

**Line-item spacing rules locked for Phase 1:**

1. Form sections separated by `space-y-5` (20px). `TemplateForm.tsx` top-level: `<div className="space-y-5">...sections...</div>` exactly like `ProfileForm.tsx:L202`.
2. Fields within a section: `space-y-3` (12px) for single-column, `grid grid-cols-2 gap-3` for two-column field pairs.
3. Section heading to first field: `mb-3` (12px).
4. Form container padding: `p-6 max-w-2xl mx-auto` (matches `ProfileForm.tsx:L173`).
5. Table row vertical padding: `py-2.5` (10px — matches `ProfileList.tsx:L59` row padding).

---

## Typography

System font stack, single family. No new type declarations — all sizes are existing Tailwind utilities in use elsewhere.

| Role | Size | Tailwind | Weight | Line Height | Usage in Phase 1 |
|------|------|----------|--------|-------------|------------------|
| Body | 14px | `text-sm` | 400 (normal) | 1.5 (`leading-normal`, Tailwind default) | Form field text, button labels, table cell content |
| Label | 12px | `text-xs` | 500 (medium) | 1.5 | Form field labels (uses `.label` helper from `globals.css:L64`: `text-xs font-medium text-gray-400 mb-1`) |
| Section Heading | 12px | `text-xs` | 600 (semibold) | 1.5 | Form section titles — `text-xs font-semibold text-gray-400 uppercase tracking-wider` (matches `ProfileForm.tsx:L205`) |
| Page Heading | 18px | `text-lg` | 600 (semibold) | 1.2 | "New Template" / "Edit Template" page title (matches `ProfileForm.tsx:L177`) |

**Monospace (launch args only):** `font-mono` at `text-xs` — reused from `ProfileForm.tsx:L532,L548` for launch args input and pill display.

**Weight discipline:** Only 3 weights ship: 400 (body), 500 (labels), 600 (headings). No 700/bold usage. This is an extraction of what exists in `ProfileForm.tsx`; no new weights are introduced.

**Table-specific rules locked:**

1. Table header: `text-xs font-semibold text-gray-400 uppercase tracking-wider` (reuse the section-heading pattern so the list reads as a single visual family with forms).
2. Table cell body: `text-sm` (14px, weight 400) with `text-gray-100` for primary content and `text-gray-500` for secondary (created_at, counts).
3. Empty state copy: `text-sm text-gray-500` (matches existing `App.tsx:L220` empty-state pattern).

---

## Color

**60/30/10 split extracted from `tailwind.config.ts` and `globals.css`.** No new colors are declared; this phase consumes the existing palette only.

| Role | Value | Token | Usage |
|------|-------|-------|-------|
| Dominant (60%) | `#0a0a0a` | `surface-0` | Viewport background, main content area |
| Dominant variant | `#111111` | `surface-1` | Top bar, sidebar chrome (matches `App.tsx:L158,L171`) |
| Secondary (30%) | `#1a1a1a` | `surface-2` | Input backgrounds (`.input` class uses `bg-surface-2`) |
| Secondary variant | `#222222` | `surface-3` | Selected row / button-secondary background (`.btn-secondary` uses `bg-surface-3`) |
| Secondary deepest | `#2a2a2a` | `surface-4` | Tag pill background, button-secondary hover |
| Border | `#2a2a2a` | `border-DEFAULT` | All section/panel borders (`border-border`) |
| Border hover | `#3a3a3a` | `border-hover` | Selected card / focus ring reference (`border-border-hover`) |
| Accent (10%) | `#6366f1` (indigo) | `accent-DEFAULT` | Primary CTAs, focus rings, "Monitor" brand icon |
| Accent hover | `#818cf8` | `accent-hover` | `.btn-primary` hover state |
| Destructive | `rgb(220 38 38)` (Tailwind `red-600`) | `red-600/20` fill, `red-400` text | Delete button (`.btn-danger`), error banner, delete confirmation copy |
| Warning (amber) | Tailwind `amber-500/10` fill, `amber-500/30` border, `amber-300` text | — | **Reserved for `clipboard_sync` warning badge only** (see Specialized Patterns below). |
| Text primary | `#e5e7eb` | Tailwind `text-gray-200`/`text-gray-100` | Body text, strong labels |
| Text muted | `#9ca3af` | Tailwind `text-gray-400` | Form labels, secondary metadata |
| Text disabled | `#6b7280` | Tailwind `text-gray-500` | Empty-state copy, timestamps, placeholder text |

**Accent reserved for:**

1. Primary CTA button backgrounds (`Create`, `Save` — via `.btn-primary`)
2. Form focus rings (via `.input` focus state — `focus:border-accent focus:ring-1 focus:ring-accent/50`)
3. Brand icon in sidebar header (the Monitor icon in `ProfileList.tsx:L27`)
4. Active nav entry (see Nav Pattern below)

**Accent MUST NOT be used for:**

- Hover states on non-primary controls (use `surface-4` or `border-hover`)
- Selected-row backgrounds in the templates table (use `surface-3` like `ProfileList.tsx:L60`)
- Info/success chips (Phase 1 has no success states to display; avoid introducing new accent usages)
- The `clipboard_sync` toggle itself (that's the warning badge's job — see below)

**Warning (amber) is reserved strictly for `clipboard_sync = true` risk signaling.** Do not extend amber to any other phase-1 UI surface. If a future phase needs amber for something else, it should be re-specified, not silently reused.

---

## Copywriting Contract

All copy below is **LOCKED**. Executor MUST copy strings verbatim. Each decision has a rationale block so the planner/executor/auditor can trust it wasn't picked arbitrarily.

### Page / Nav

| Element | Copy | Notes |
|---------|------|-------|
| Top-bar nav button (Profiles) | `Profiles` | Existing surface label — do not change |
| Top-bar nav button (Templates) | `Templates` | New |
| Templates page empty-state heading | `No templates yet` | Mirrors existing `ProfileList.tsx:L52` pattern ("No profiles yet") for consistency |
| Templates page empty-state body | `Create your first vendor template to start provisioning profiles.` | Rationale: names the operator's next actionable step (create) and connects templates to profiles so operators understand the causal chain |
| Templates page empty-state CTA | `New Template` | Mirrors `ProfileList.tsx:L99` ("New Profile") |

### Form — create/edit

| Element | Copy |
|---------|------|
| Page heading — create mode | `New Template` |
| Page heading — edit mode | `Edit Template` |
| Primary submit CTA — create mode | `Create` |
| Primary submit CTA — edit mode | `Save` |
| Secondary CTA | `Cancel` |
| Destructive CTA (edit only) | `Delete` |
| Saving state label | `Saving...` (while `POST`/`PUT` in flight — matches `ProfileForm.tsx:L197`) |
| Deleting state label | `Deleting...` (matches `ProfileForm.tsx:L187`) |

### Form — section headings (uppercase, exactly)

| Section | Heading | Fields |
|---------|---------|--------|
| Identity | `IDENTITY` | `vendor_type`, `label`, `notes` |
| Fingerprint | `FINGERPRINT` | `timezone`, `locale`, `platform` |
| Screen | `SCREEN` | `screen_width`, `screen_height`, `color_scheme` |
| GPU | `GPU` | `gpu_vendor`, `gpu_renderer`, `hardware_concurrency` |
| Behavior | `BEHAVIOR` | `humanize` (checkbox), `human_preset` (select, shown when humanize=true), `launch_args` (pill list) |
| Proxy | `PROXY` | `proxy` |
| Security | `SECURITY` | `clipboard_sync` (toggle) + amber warning badge |

Section headings use the existing ProfileForm convention: `text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3`. Do not change the capitalization — Tailwind's `uppercase` utility renders the heading regardless of source casing; source text in JSX should remain Title Case (`Identity`, `Fingerprint`, etc.) so grep/search still works.

### Field labels and placeholders

| Field | Label | Placeholder | Required |
|-------|-------|-------------|----------|
| `vendor_type` | `Vendor Type` | `e.g. shopify, amazon-sp` | Yes (enforced client + server) |
| `label` | `Label` | `e.g. Shopify Admin Console` | No |
| `notes` | `Notes` | `Optional notes for operators…` | No (textarea, `min-h-[80px] resize-y`) |
| `timezone` | `Timezone` | `America/New_York` | No |
| `locale` | `Locale` | `en-US` | No |
| `platform` | `Platform` | — (select: Windows / macOS / Linux) | Yes, defaults `windows` |
| `screen_width` | `Width` | `1920` | Yes |
| `screen_height` | `Height` | `1080` | Yes |
| `color_scheme` | `Color Scheme` | — (select: System default / Light / Dark / No preference) | No |
| `gpu_vendor` | `GPU Vendor` | `Auto (from seed)` | No |
| `gpu_renderer` | `GPU Renderer` | `Auto (from seed)` | No |
| `hardware_concurrency` | `Hardware Concurrency` | `Auto (from seed)` | No (number) |
| `humanize` | `Human-like mouse, keyboard, and scroll behavior` | — (checkbox) | No, defaults `false` |
| `human_preset` | `Human Preset` | — (select: Default / Careful) | No, shown only when humanize=true |
| `launch_args` | `Launch Args` (caption: `Custom Chromium flags passed at launch (e.g. --load-extension, --disable-features)`) | `--load-extension=/data/extensions/ublock` | No (pill list) |
| `proxy` | `Proxy` | `http://user:pass@host:port` | No |
| `clipboard_sync` | `Enable clipboard sync in VNC viewer` (paired with amber warning badge, see below) | — (checkbox/toggle) | No, defaults `false` |

### Amber `clipboard_sync` Warning Badge — LOCKED

This is the critical phase-1 surface that maps to **Pitfall 11** and **SEC-06**. The warning MUST be unmissable when the operator considers flipping the toggle on.

**Placement:** Inside the Security section, positioned **directly above** the `clipboard_sync` checkbox row (not inline beside it — the warning needs to be read before the toggle is used, not discovered after).

**Markup (LOCKED — executor copies verbatim):**

```tsx
<div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 mb-3">
  <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
  <div className="text-xs text-amber-200 leading-relaxed">
    <span className="font-semibold">Clipboard sync is off by default for a reason.</span>
    {" "}
    When enabled, any page the vendor browser visits can read clipboard contents — including passwords and 2FA codes an operator pastes into other apps. Only turn this on when you understand the risk and trust every page this profile will reach.
  </div>
</div>
```

**Rationale for this copy:**

- Opens with "off by default for a reason" — affirms that the safer default is intentional, so flipping it feels like a deliberate override.
- Names the concrete attack surface (`any page … can read clipboard contents`) rather than abstract "security risk."
- Names specific real-world secrets at risk (`passwords and 2FA codes`) — operators often paste these during setup, making the risk concrete.
- Closes with the pre-condition for safe enablement (`understand the risk and trust every page`) rather than a generic warning.
- 3-sentence length chosen to fit two lines at `text-xs` in the 672px (`max-w-2xl`) form container without scroll.

**Accessibility:**

- `AlertTriangle` icon has `aria-hidden="true"` — the warning text is the accessible name.
- The warning is a sibling of the checkbox, not wrapping it, so screen readers announce it as standalone text before reaching the toggle.
- Color contrast: `text-amber-200` on `bg-amber-500/10` over `surface-2` — meets WCAG AA for `text-xs` body (verified against Tailwind's amber-200 `#fde68a` against composite background).
- No `role="alert"` — the warning is static context, not a live-updating error. Using `alert` would fire on every form mount.

### Table — TemplateList columns and state

| Column | Header | Cell content | Alignment |
|--------|--------|--------------|-----------|
| Vendor Type | `Vendor Type` | `{vendor_type}` in `font-mono text-sm text-gray-100` | Left |
| Label | `Label` | `{label || "—"}` in `text-sm text-gray-200` | Left |
| Created | `Created` | Human-relative: `"2h ago"` / `"3d ago"` / `"Apr 22"` if older than 7d. `text-xs text-gray-500` | Left |
| Actions | (no header — right-aligned actions cell) | `Edit` button (secondary) + `Delete` button (danger) | Right |

**Edit and Delete action buttons:** reuse `.btn-secondary` and `.btn-danger` classes. Both use `flex items-center gap-1.5` with `Pencil`/`Trash2` icons from `lucide-react` at `h-3.5 w-3.5` (matches `ProfileForm.tsx:L186` sizing).

**Loading state:** On initial load (`useTemplates` hook returns `loading=true, templates=[]`), show `<div className="flex items-center justify-center h-full"><div className="text-gray-500 text-sm">Loading...</div></div>` — exact match to `App.tsx:L149`. No skeletons (brownfield consistency; existing app uses text-only loading).

**Error state:** When the hook's `error` is non-null, render the existing error-banner pattern from `App.tsx:L210`:

```tsx
<div className="px-4 py-2 bg-red-600/15 border-b border-red-600/30 text-red-400 text-sm">
  {error}
</div>
```

The banner sits between the page top bar and the table content. Errors do not block the table — stale data stays visible so operators can still read the list.

### Validation Errors (inline, per-field)

Per D-13, Pydantic validation errors render beside the offending field.

**Markup (LOCKED):**

```tsx
{fieldErrors.vendor_type && (
  <p className="text-xs text-red-400 mt-1" role="alert">
    {fieldErrors.vendor_type}
  </p>
)}
```

- Position: immediately below the input, before the next form field.
- Color: `text-red-400` (matches error banner text color).
- Size: `text-xs` (matches `.label`).
- `role="alert"` here IS correct — the error is dynamic and should be announced when it appears.
- `mt-1` (4px) spacing between input and error — matches the existing `.label mb-1` rhythm.

**Server-side 409 on create (duplicate `vendor_type`):** surface as an inline error below the `vendor_type` field with copy `"A template for this vendor_type already exists."` (derived from the 409 response `detail` — see Error Payloads below).

### Delete Error Modal (409 with `blocking_profile_ids`)

Per D-13, delete-blocked 409 opens a modal listing the offending profile IDs.

**Modal markup skeleton (LOCKED):**

```tsx
<div role="dialog" aria-modal="true" aria-labelledby="delete-blocked-title"
     className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
  <div className="bg-surface-1 border border-border rounded-lg p-6 max-w-md w-full space-y-4">
    <h2 id="delete-blocked-title" className="text-lg font-semibold text-gray-100">
      Cannot delete template
    </h2>
    <p className="text-sm text-gray-300 leading-relaxed">
      This template has <span className="font-semibold text-gray-100">{n}</span>{" "}
      {n === 1 ? "profile" : "profiles"} still attached. Delete or reassign{" "}
      {n === 1 ? "it" : "them"} before removing the template.
    </p>
    <div className="bg-surface-2 border border-border rounded-md p-3 max-h-40 overflow-y-auto">
      <ul className="font-mono text-xs text-gray-400 space-y-1">
        {blockingIds.map(id => <li key={id}>{id}</li>)}
      </ul>
    </div>
    <div className="flex items-center justify-between gap-2">
      <button onClick={handleCopyIds} className="btn-secondary flex items-center gap-1.5">
        <Copy className="h-3.5 w-3.5" />
        <span>{copied ? "Copied" : "Copy IDs"}</span>
      </button>
      <button onClick={onClose} className="btn-primary">
        Close
      </button>
    </div>
  </div>
</div>
```

**Copy details:**

- Title: `Cannot delete template` — avoids `Error` / `Failed` which skew alarming for what is expected intent-protection behavior.
- Body: singular vs plural handled (`1 profile` / `3 profiles`). Ends with actionable guidance (`Delete or reassign them before removing…`) rather than a dead end.
- Copy button label toggles to `Copied` for 2 seconds after click, then reverts — matches common clipboard UX convention. Uses `Copy` icon from `lucide-react`.
- `Close` button (not `OK` or `Dismiss`) — unambiguous action label.

**Keyboard interaction:**

- Escape key dismisses modal (`useEffect` listener on `keydown`).
- Focus traps on open: the `Copy IDs` button receives initial focus (primary action for the operator) via `ref.current?.focus()` in a `useEffect` that runs on mount.
- Tab cycles Copy → Close → Copy (two focusable elements, trap is trivial).

### Destructive confirmation (single-template delete, no blocking profiles)

Existing ProfileForm uses `window.confirm(...)` for delete (see `ProfileForm.tsx:L123`). Mirror this in Phase 1 for consistency; modal upgrade is Phase 4 polish.

**Copy (LOCKED):**

```tsx
if (!confirm(`Delete template "${template.label || template.vendor_type}"? This cannot be undone.`)) return;
```

- Uses the template's `label` if set, else its `vendor_type` — operators recognize either.
- "This cannot be undone" is verbatim what `window.confirm` conventions call for, matching the existing ProfileForm L123 phrasing style.

### Error Payloads — Expected Shapes

Backend returns are documented so the UI can decode them to the copy above:

| Scenario | Status | Body | UI Surface |
|----------|--------|------|------------|
| Duplicate `vendor_type` on create | 409 | `{"detail": "A template for vendor_type 'X' already exists"}` | Inline field error under `vendor_type` input |
| Delete blocked by profiles | 409 | `{"detail": "Template has N attached profile(s); delete or reassign them first", "blocking_profile_ids": ["p1","p2",…]}` | Delete-blocked modal (above) |
| Pydantic validation | 422 | FastAPI default `{"detail":[{"loc":[...], "msg":"...", "type":"..."}, …]}` | Inline field errors, keyed by `loc[-1]` |
| Auth failure | 401 | — | Global `setOnUnauthorized` callback (existing, `api.ts:L84`) triggers LoginPage |
| Other server error | 500 | `{"detail": "..."}` | Error banner at top of templates view |

---

## Specialized Patterns (Phase-1-specific)

### Nav Pattern — minimal top-bar view switcher

Per CONTEXT.md D-12 and `<phase_ui_scope>` guidance ("minimal 2-button top-bar switcher"), Phase 1 extends `App.tsx`'s existing top bar with two view-switching buttons. This is a deliberately small footprint; Phase 4 redesigns the nav in full.

**Location:** Inside the existing top-bar `<div className="flex items-center gap-3">` block (`App.tsx:L172`), **before** the selected-profile label (which should only appear when `view === "view" | "edit"` in the profiles surface).

**Markup (LOCKED):**

```tsx
<div className="flex items-center gap-1 bg-surface-2 rounded-md p-0.5">
  <button
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
    onClick={() => setSurface("templates")}
    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
      surface === "templates"
        ? "bg-surface-3 text-gray-100"
        : "text-gray-400 hover:text-gray-200"
    }`}
  >
    Templates
  </button>
</div>
```

- **Order:** Profiles first, Templates second (locked in CONTEXT.md `<specifics>`).
- **Active state:** `bg-surface-3` with `text-gray-100` — reuses the same treatment as selected rows in `ProfileList.tsx:L60`. Do NOT use `accent` for the active nav state; accent is reserved for CTAs.
- **State model in App.tsx:** add a sibling `surface: "profiles" | "templates"` state alongside the existing `view` state. The existing `view` state continues to drive inner content when `surface === "profiles"`; when `surface === "templates"`, the right panel renders the Templates surface instead (list/form dispatch).

### Template Surface View State

Mirror the profiles surface's view dispatch, but on its own state machine so the two surfaces don't collide:

```tsx
type TemplateView = "empty" | "create" | "edit";
// (No "view" — templates have no runtime/viewer counterpart.)
```

- `empty` → TemplateList with empty-state placeholder (when `templates.length === 0`)
- `empty` → TemplateList with rows (when `templates.length > 0`) — empty name is a misnomer inherited from profiles surface; acceptable in brownfield for symmetry
- `create` → TemplateForm with `template={null}`
- `edit` → TemplateForm with `template={selectedTemplate}`

### Responsive Breakpoints — desktop-first, acceptable to ignore mobile

Single-host internal admin tool. Desktop-first is the locked stance (per `<locked_design_context>`):

- **Primary target:** ≥1024px width. All UI must be fully usable and readable.
- **Minimum acceptable:** 768px width. Layout may compress (e.g. `grid-cols-2` still works; sidebars may narrow) but no horizontal scroll.
- **Mobile (<768px):** Not supported. Admin dashboard has always been desktop-only; no mobile-first work required in Phase 1.

No explicit breakpoint classes needed in Phase 1 — the existing `max-w-2xl` form container and full-width table behave acceptably at both breakpoints without overrides.

### Polling and Loading State

Inherit from `useProfiles.ts` exactly:

- 3-second `setInterval` after initial mount (matches `useProfiles.ts:L24`).
- `loading=true` only on the very first fetch; subsequent polls update data silently.
- `error` clears on the next successful poll (matches `useProfiles.ts:L15`).
- No spinner on polling refreshes — silent background update is the UX contract.

### Unsaved-changes guard — NOT in scope for Phase 1

ProfileForm does not implement an unsaved-changes guard. Phase 1 inherits that behavior — cancel/navigation away drops in-progress edits without warning. Add to Phase 4 polish if operators request it. This is a LOCKED decision to keep scope tight.

### Accessibility Baseline

- All buttons have visible text labels (no icon-only buttons without `title` or accessible name).
- Icons inside buttons use `aria-hidden="true"` when paired with text; standalone icon buttons use a `title` attribute (matches existing `App.tsx:L177` sidebar toggle).
- Form labels are associated via `<label>` wrapping `<input>` or `htmlFor`/`id` pairing — the `.label` helper in `globals.css:L64` is the visual class, structural association is the executor's responsibility.
- Modal has `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to its title — verified in skeleton above.
- Focus-visible outline provided by `.input` / `.btn` focus states (existing Tailwind ring — `focus:ring-2 focus:ring-accent/50`).
- Color contrast: all text/background pairs meet WCAG AA at `text-sm` or larger. `text-gray-500` on `surface-0` is the lowest-contrast pair and is reserved for non-essential metadata (timestamps).

---

## Component Inventory (Phase 1)

| Component | Path | Status | Mirrors |
|-----------|------|--------|---------|
| TemplateList | `frontend/src/components/TemplateList.tsx` | NEW | `ProfileList.tsx` (layout, not columns) |
| TemplateForm | `frontend/src/components/TemplateForm.tsx` | NEW | `ProfileForm.tsx` (section-grouping) |
| DeleteBlockedModal | `frontend/src/components/DeleteBlockedModal.tsx` | NEW | — (net new; no existing modal in codebase) |
| WarningBadge (inlined) | within `TemplateForm.tsx` Security section | NEW (inline, not separate file) | — |
| useTemplates hook | `frontend/src/hooks/useTemplates.ts` | NEW | `useProfiles.ts` (3s polling, CRUD) |
| api.templates | extension to `frontend/src/lib/api.ts` | EXTEND | `api.profiles.*` |
| App.tsx surface switcher | `frontend/src/App.tsx` | EXTEND | — |

**Do NOT extract the warning badge into a reusable `<WarningBadge>` component in Phase 1.** Its styling is specific to the clipboard-sync context and prematurely generalizing it would invite misuse (e.g. reapplying amber to contexts where the Pitfall 11 framing doesn't apply). When a second amber warning is needed in a future phase, extract then.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none (shadcn not initialized this phase) | not applicable |
| third-party | none | not applicable |

Phase 1 introduces **zero** external UI dependencies. All new components are hand-rolled with Tailwind utilities and `lucide-react` icons (existing project dep). This is the locked stance per CONTEXT.md D-11 Claude's Discretion ("Tailwind design tokens: reuse existing `globals.css` palette; no new colors").

---

## Source Traceability

Every design decision in this contract traces back to a locked upstream source:

| Decision | Source |
|----------|--------|
| Section-grouped form with 7 sections | CONTEXT.md D-11 |
| `clipboard_sync` defaults false + amber warning | CONTEXT.md D-11, D-18; REQUIREMENTS.md SEC-06; research PITFALLS.md Pitfall 11 |
| Modal-style editing (not inline) | CONTEXT.md D-13 Claude's Discretion |
| 3-second polling interval | CONTEXT.md D-13 Claude's Discretion; `useProfiles.ts:L24` |
| 409 delete error with blocking IDs modal + copy helper | CONTEXT.md D-13 |
| Inline validation errors beside fields | CONTEXT.md D-13 |
| Templates nav alongside Profiles (order: Profiles first) | CONTEXT.md D-12; CONTEXT.md `<specifics>` |
| Reuse `globals.css` palette, no new colors | CONTEXT.md D-11 Claude's Discretion |
| Tailwind tokens: `surface-0..4`, `border`, `accent` | `frontend/tailwind.config.ts` L8-24 |
| `.btn-primary`/`.btn-secondary`/`.btn-danger`/`.input`/`.label` classes | `frontend/src/styles/globals.css` L45-65 |
| System font stack | `frontend/src/styles/globals.css` L12-13 |
| Loading text pattern | `frontend/src/App.tsx:L149` |
| Error banner pattern | `frontend/src/App.tsx:L210` |
| Empty-state copy template | `frontend/src/components/ProfileList.tsx:L52` |
| `lucide-react` as icon library | `frontend/src/App.tsx:L2` (existing import) |
| Desktop-first responsive stance | `<locked_design_context>` from invocation |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
