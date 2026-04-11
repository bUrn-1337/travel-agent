/**
 * P7 — Shared auth module.
 * Include on every page with: <script src="/auth.js" defer></script>
 * Then call TravelAuth.init() in DOMContentLoaded.
 */
const TravelAuth = {
  user: null,

  async init() {
    try {
      const resp = await fetch("/auth/me", { credentials: "include" });
      if (resp.ok) this.user = await resp.json();
    } catch { /* offline / not logged in */ }
    this._renderNav();
    this._handleLoginRedirect();
  },

  _handleLoginRedirect() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("login") === "success") {
      // Clean up URL without reload
      const clean = window.location.pathname;
      window.history.replaceState({}, "", clean);
    }
    if (params.get("auth_error")) {
      console.warn("Auth error:", params.get("auth_error"));
      window.history.replaceState({}, "", window.location.pathname);
    }
  },

  _renderNav() {
    const slot = document.getElementById("auth-nav");
    if (!slot) return;

    if (this.user) {
      slot.innerHTML = `
        <a href="/trips.html" class="nav-pill">My Trips</a>
        <div class="nav-user-menu">
          ${this.user.avatar_url
            ? `<img src="${this.user.avatar_url}" class="nav-avatar" alt="${this.user.name}" />`
            : `<span class="nav-avatar-placeholder">${this.user.name[0]}</span>`}
          <span class="nav-user-name">${this.user.name.split(" ")[0]}</span>
          <button class="nav-pill nav-logout-btn" onclick="TravelAuth.logout()">Logout</button>
        </div>`;
    } else {
      slot.innerHTML = `
        <a href="/auth/google" class="nav-pill accent nav-login-btn">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:.3rem;vertical-align:-.15em">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Sign in
        </a>`;
    }
  },

  async logout() {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    this.user = null;
    window.location.href = "/";
  },

  isLoggedIn() { return !!this.user; },

  /** Save a full trip snapshot to the server. Returns trip id or null. */
  async saveTrip({ destination, planMarkdown, days, budgetPerDay, groupType, vibes, photoUrl }) {
    if (!this.isLoggedIn()) return null;
    try {
      const resp = await fetch("/api/trips", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          destination_id:   destination.id,
          destination_name: destination.name,
          destination_data: destination,
          plan_markdown:    planMarkdown || "",
          days:             days || 5,
          budget_per_day:   budgetPerDay || 2000,
          group_type:       groupType || "friends",
          vibes:            vibes || [],
          photo_url:        photoUrl || null,
        }),
      });
      if (!resp.ok) return null;
      const data = await resp.json();
      return data.id;
    } catch { return null; }
  },
};
