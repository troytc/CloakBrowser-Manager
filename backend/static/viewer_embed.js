/**
 * Signed viewer embed bootstrap (no inline script — satisfies viewer CSP).
 * Page URL: /viewer/{profile_id}#token=<jwt>
 */
const pathMatch = location.pathname.match(/^\/viewer\/([^/]+)\/?$/);
const profileId = pathMatch?.[1];
const params = new URLSearchParams(location.hash.replace(/^#/, ""));
const token = params.get("token");
const errEl = document.getElementById("error");
const screen = document.getElementById("screen");

if (!profileId) {
  errEl.hidden = false;
  errEl.textContent = "Invalid viewer URL path.";
} else if (!token) {
  errEl.hidden = false;
  errEl.textContent = "Missing viewer token in URL fragment (#token=).";
} else {
  import("https://cdn.jsdelivr.net/npm/@novnc/novnc@1.4.0/core/rfb.js")
    .then(({ default: RFB }) => {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${location.host}/viewer/${profileId}/ws?token=${encodeURIComponent(token)}`;
      const rfb = new RFB(screen, wsUrl, { wsProtocols: ["binary"] });
      rfb.scaleViewport = true;
      rfb.resizeSession = true;
      rfb.addEventListener("disconnect", (e) => {
        if (!e.detail.clean) {
          errEl.hidden = false;
          errEl.textContent = "Viewer disconnected.";
        }
      });
    })
    .catch((e) => {
      errEl.hidden = false;
      errEl.textContent = "Failed to load viewer: " + e;
    });
}
