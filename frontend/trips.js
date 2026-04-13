let _trips = [];

document.addEventListener("DOMContentLoaded", async () => {
  await TravelAuth.init();

  if (!TravelAuth.isLoggedIn()) {
    document.getElementById("trips-sub").textContent = "";
    document.getElementById("trips-login-prompt").style.display = "block";
    return;
  }

  await loadTrips();
});

async function loadTrips() {
  const sub  = document.getElementById("trips-sub");
  const grid = document.getElementById("trips-grid");
  sub.textContent = "Loading…";
  grid.innerHTML  = "";

  try {
    const resp = await fetch("/api/trips", { credentials: "include" });
    if (!resp.ok) throw new Error("Failed");
    _trips = await resp.json();
  } catch {
    sub.textContent = "Failed to load trips.";
    return;
  }

  if (!_trips.length) {
    sub.textContent = "No saved trips yet.";
    grid.innerHTML  = `
      <div class="trips-empty">
        <p>You haven't saved any trips yet.</p>
        <a href="/" class="btn-generate-plan" style="text-decoration:none;display:inline-block;margin-top:1rem">
          Start Exploring →
        </a>
      </div>`;
    return;
  }

  sub.textContent = `${_trips.length} saved trip${_trips.length !== 1 ? "s" : ""}`;
  grid.innerHTML  = _trips.map(renderTripCard).join("");
}

function renderTripCard(trip) {
  const d         = trip.destination_data || {};
  const photoStyle = trip.photo_url
    ? `style="background-image:url('${trip.photo_url}');background-size:cover;background-position:center;"`
    : "";
  const date = new Date(trip.created_at).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
  const vibes = (trip.vibes || []).slice(0, 3).map(v =>
    `<span class="dest-vibe-tag" style="font-size:.7rem;padding:.2rem .6rem">${v}</span>`
  ).join("");

  return `
  <div class="trip-card" id="trip-${trip.id}">
    <div class="trip-card-hero ${trip.photo_url ? 'has-photo' : ''}"
         data-vibe="${d.primary_vibe || ''}" ${photoStyle}>
      <div class="card-header-overlay"></div>
      <div class="trip-card-hero-content">
        <div class="trip-card-name">${trip.destination_name}</div>
        <div class="trip-card-meta">${d.state || ""} · ${trip.days} days · ₹${trip.budget_per_day.toLocaleString("en-IN")}/day · ${trip.group_type}</div>
      </div>
    </div>
    <div class="trip-card-body">
      <div class="trip-card-vibes">${vibes}</div>
      ${trip.plan_markdown
        ? `<p class="trip-card-preview">${trip.plan_markdown.slice(0, 140).replace(/[#*`]/g, "")}…</p>`
        : `<p class="trip-card-preview" style="color:var(--muted)">No plan generated.</p>`}
      <div class="trip-card-date">Saved ${date}</div>
    </div>
    <div class="trip-card-actions">
      ${trip.plan_markdown
        ? `<button class="btn-trip-action" onclick="viewPlan('${trip.id}')">📄 View Plan</button>`
        : ""}
      <a class="btn-trip-action" href="/destination.html?id=${trip.destination_id}&days=${trip.days}&budget=${trip.budget_per_day}&group=${trip.group_type}" target="_blank">🔗 Destination</a>
      ${trip.is_public
        ? `<button class="btn-trip-action accent" onclick="copyShareLink('${trip.id}')">🔗 Copy Link</button>`
        : `<button class="btn-trip-action" onclick="shareTrip('${trip.id}', this)">📤 Share</button>`}
      <button class="btn-trip-action danger" onclick="deleteTrip('${trip.id}')">🗑 Delete</button>
    </div>
  </div>`;
}

function viewPlan(tripId) {
  const trip = _trips.find(t => t.id === tripId);
  if (!trip?.plan_markdown) return;

  const modal   = document.getElementById("plan-modal");
  const content = document.getElementById("plan-modal-content");
  content.innerHTML = `
    <h2 style="margin-bottom:1rem;font-size:1.1rem">${trip.destination_name} — Travel Plan</h2>
    <div style="font-size:.9rem;line-height:1.75;color:var(--text-2)">
      ${typeof marked !== "undefined" ? marked.parse(trip.plan_markdown) : trip.plan_markdown}
    </div>`;
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closePlanModal() {
  document.getElementById("plan-modal").style.display = "none";
  document.body.style.overflow = "";
}

async function shareTrip(tripId, btn) {
  btn.disabled = true;
  btn.textContent = "Sharing…";
  try {
    const resp = await fetch(`/api/trips/${tripId}/share`, {
      method: "POST", credentials: "include",
    });
    if (!resp.ok) throw new Error();
    const data = await resp.json();

    // Update local state
    const trip = _trips.find(t => t.id === tripId);
    if (trip) trip.is_public = true;

    btn.textContent = "✓ Shared!";
    btn.classList.add("accent");
    btn.onclick = () => copyShareLink(tripId);
    setTimeout(() => copyShareLink(tripId), 200);
  } catch {
    btn.disabled = false;
    btn.textContent = "📤 Share";
  }
}

async function copyShareLink(tripId) {
  const url = `${window.location.origin}/trip/${tripId}`;
  try {
    await navigator.clipboard.writeText(url);
    const btn = document.querySelector(`#trip-${tripId} .btn-trip-action.accent`);
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "✓ Copied!";
      setTimeout(() => { btn.textContent = orig; }, 2000);
    }
  } catch {
    prompt("Copy this link:", url);
  }
}

async function deleteTrip(tripId) {
  if (!confirm("Delete this saved trip?")) return;
  try {
    const resp = await fetch(`/api/trips/${tripId}`, {
      method: "DELETE", credentials: "include",
    });
    if (!resp.ok) throw new Error();
    _trips = _trips.filter(t => t.id !== tripId);
    document.getElementById(`trip-${tripId}`)?.remove();
    const sub = document.getElementById("trips-sub");
    if (sub) sub.textContent = `${_trips.length} saved trip${_trips.length !== 1 ? "s" : ""}`;
    if (!_trips.length) loadTrips();
  } catch {
    alert("Failed to delete trip.");
  }
}
