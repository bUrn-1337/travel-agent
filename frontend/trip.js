const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

document.addEventListener("DOMContentLoaded", async () => {
  TravelAuth.init();

  // Extract trip ID from path: /trip/<id>
  const tripId = window.location.pathname.replace(/^\/trip\/?/, "").split("?")[0];

  if (!tripId) {
    showError();
    return;
  }

  try {
    const resp = await fetch(`/api/share/${tripId}`);
    if (!resp.ok) { showError(); return; }
    const trip = await resp.json();
    renderTrip(trip);
  } catch {
    showError();
  }
});

function showError() {
  document.getElementById("trip-error").style.display = "block";
}

function renderTrip(trip) {
  const d = trip.destination_data || {};
  document.title = `TravelMind — ${trip.destination_name} Trip`;

  // Hero
  const hero = document.getElementById("trip-hero");
  if (trip.photo_url) {
    hero.style.backgroundImage = `url('${trip.photo_url}')`;
    hero.style.backgroundSize  = "cover";
    hero.style.backgroundPosition = "center";
  }
  hero.style.display = "block";

  const inSeason = (d.best_months || []).includes(new Date().getMonth() + 1);
  document.getElementById("trip-hero-content").innerHTML = `
    <div class="dest-hero-eyebrow">${d.state || ""} · ${d.region || ""}</div>
    <h1 class="dest-hero-title">${trip.destination_name}</h1>
    <p class="dest-hero-sub">${d.description || ""}</p>
    <div class="dest-hero-badges">
      ${d.primary_vibe ? `<span class="dest-hero-badge accent">${d.primary_vibe}</span>` : ""}
      <span class="dest-hero-badge">🗓 ${trip.days} days</span>
      <span class="dest-hero-badge">₹${trip.budget_per_day.toLocaleString("en-IN")}/day</span>
      <span class="dest-hero-badge">${trip.group_type}</span>
      <span class="dest-hero-badge">${inSeason ? "✓ In season" : "⚠ Off season"}</span>
    </div>`;

  // Meta
  document.getElementById("trip-meta").innerHTML = [
    ["Destination",  trip.destination_name],
    ["Duration",     `${trip.days} days`],
    ["Budget/day",   `₹${trip.budget_per_day.toLocaleString("en-IN")}`],
    ["Group type",   trip.group_type],
    ["Vibes",        (trip.vibes || []).join(", ") || "—"],
    ["Saved on",     new Date(trip.created_at).toLocaleDateString("en-IN", { day:"numeric", month:"long", year:"numeric" })],
  ].map(([label, value]) => `
    <div class="dest-stat">
      <div class="dest-stat-label">${label}</div>
      <div class="dest-stat-value">${value}</div>
    </div>`).join("");

  // Plan
  const planEl = document.getElementById("trip-plan");
  if (trip.plan_markdown) {
    planEl.innerHTML = typeof marked !== "undefined"
      ? marked.parse(trip.plan_markdown)
      : `<pre>${trip.plan_markdown}</pre>`;
  } else {
    planEl.innerHTML = `<p style="color:var(--muted)">No plan was saved with this trip.</p>`;
  }

  // CTA
  document.getElementById("cta-dest-name").textContent = trip.destination_name;
  document.getElementById("cta-dest-link").href = `/destination.html?id=${trip.destination_id}`;

  // Shared by
  if (trip.user) {
    document.getElementById("trip-shared-by").innerHTML = `
      <div class="trip-sharer">
        ${trip.user.avatar_url
          ? `<img src="${trip.user.avatar_url}" class="nav-avatar" alt="${trip.user.name}" />`
          : ""}
        <span>Shared by <strong>${trip.user.name}</strong></span>
      </div>`;
  }

  document.getElementById("trip-main").style.display = "flex";
}
