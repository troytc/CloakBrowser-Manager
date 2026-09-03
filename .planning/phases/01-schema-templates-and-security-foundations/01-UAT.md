---
status: complete
phase: 01-schema-templates-and-security-foundations
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md, 01-08-SUMMARY.md]
started: 2026-05-09T02:50:00Z
updated: 2026-09-03
---

## Current Test

[testing complete — all 7 items pass]

## Tests

### 1. Cold Start Smoke Test
expected: Stop any running container, bring it back up, container boots cleanly with no errors in `docker compose logs`, SQLite migrations run through (init_db idempotent), entrypoint chown succeeds, and the dashboard or health endpoint returns live data.
result: pass

### 2. Create Vendor Template via Dashboard
expected: Open the admin dashboard at http://localhost:8080/, log in if AUTH_TOKEN is set, click the **Templates** pill in the top bar, click **New Template**, fill `vendor_type=shopify` + `label=Shopify` + leave other fields default, click Create. Form unmounts back to the empty/list view; new row appears in the table with vendor_type=shopify and label=Shopify; no error banner.
result: pass

### 3. Edit Existing Template
expected: From the Templates list, click **Edit** on the shopify row, change `label` to `Shopify Edited`, click Save. Form returns to list view; row label updates within ~3s polling refresh; no error banner.
result: pass

### 4. Delete-from-form Blocked by Attached Profile (BL-02 fix)
expected: Create a profile that references the shopify template. Use the machine API — the admin `POST /api/profiles` surface was removed in Phase 4 and returns 410: `curl -X POST http://localhost:8080/sessions -H "X-API-Key: $MAIN_APP_API_KEY" -H 'Content-Type: application/json' -d '{"vendor_type":"shopify","vendor_connection_id":"uat-block-01"}'`. Then in the dashboard, click **Edit** on the shopify template, click the form's own **Delete** button, OK the confirm dialog. Observe **DeleteBlockedModal** with title "Cannot delete template", the template's vendor_type quoted, count of attached profiles, list of profile IDs, **Copy IDs** button (toggles to "Copied" for ~2s), Close button, Escape key dismisses. The Edit-Template form **stays mounted behind the modal** — this is the BL-02 fix.
result: pass

### 5. Delete Template After Removing Blocking Profile
expected: Close the DeleteBlockedModal, delete the blocking profile, return to Templates, click Delete on the shopify row. Confirm dialog → row disappears from the list; no modal; no error banner. Removal paths: machine `DELETE /sessions/{profile_id}` then `DELETE /profiles/{profile_id}` (both require `X-API-Key`), or the still-live admin `DELETE /api/profiles/{profile_id}`.
result: pass

### 6. Container Recreate with UID Mismatch (OPS-04 entrypoint chown)
expected: `docker compose down`, change host UID owning the data dir (e.g. `sudo chown -R 1000:1000 ~/.cloakbrowser-manager` or your bind-mount path), then `docker compose up`. Watch entrypoint logs and the first Chromium launch on a profile wake. Service starts cleanly (entrypoint chown -R brings ownership back to CHROME_UID before uvicorn exec). On first profile launch, Chromium can write cookies (no "Failed to flush cookies" / EACCES errors).
result: pass

### 7. Fail-Closed Startup Without Required Secrets (SEC-06)
expected: Stop the container. Comment out / unset `MAIN_APP_API_KEY` AND `VIEWER_SECRET` in `.env`, ensure `DEV_MODE` is unset (production mode). `docker compose up`. Container exits with a RuntimeError naming both VIEWER_SECRET and MAIN_APP_API_KEY as missing, and pointing operator at `DEV_MODE=1`. Uvicorn does **not** bind port 8080.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]

## Notes

Tests 4 and 6 confirmed by operator on 2026-09-03, closing the two items deferred at
v1.0 milestone close. Test 4's setup step was corrected at the same time: it previously
pointed at the "Phase 2 surface" admin profile-create API, which Phase 4 retired
(`POST /api/profiles` → 410). Profile creation now goes through machine `POST /sessions`.
