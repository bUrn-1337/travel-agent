const API_BASE = window.location.port === "3000" || window.location.port === "80" || window.location.port === ""
  ? "" : "http://localhost:8000";

const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

let _destData        = null;
let _heroPhotos      = [];
let _heroIdx         = 0;
let _galleryPhotos   = [];
let _lightboxIdx     = 0;
let _planController  = null;
let _lastPlanMarkdown = "";   // raw markdown from last successful plan generation

/* ===== INIT ===== */
const _urlParams = new URLSearchParams(window.location.search);
const destId     = _urlParams.get("id");

document.addEventListener("DOMContentLoaded", () => {
  TravelAuth.init();
  // Pre-fill plan controls from URL params (passed by lookup tab)
  const days   = _urlParams.get("days");
  const budget = _urlParams.get("budget");
  const group  = _urlParams.get("group");
  if (days)   { const el = document.getElementById("plan-days");   if (el) el.value = days; }
  if (budget) { const el = document.getElementById("plan-budget"); if (el) el.value = budget; }
  if (group)  {
    const el = document.getElementById("plan-group");
    if (el) el.value = group;
  }
});

if (!destId) {
  document.body.innerHTML = `<div style="padding:4rem;text-align:center;color:#f87171">
    No destination specified. <a href="/" style="color:#4ade80">Go back →</a>
  </div>`;
} else {
  loadDestination(destId);
}

async function loadDestination(id) {
  const [destResp, photoResp] = await Promise.all([
    fetch(`${API_BASE}/api/destinations/${id}`).catch(() => null),
    fetch(`${API_BASE}/api/photos/${id}?count=15`).catch(() => null),
  ]);

  if (!destResp || !destResp.ok) {
    document.getElementById("dest-hero-content").innerHTML =
      `<p style="color:#f87171">Destination not found. <a href="/" style="color:#4ade80">Go back →</a></p>`;
    return;
  }

  _destData = await destResp.json();
  const photoData = photoResp && photoResp.ok ? await photoResp.json() : {};
  _heroPhotos    = photoData.photo_urls || [];
  _galleryPhotos = _heroPhotos;

  document.title = `TravelMind — ${_destData.name}`;
  renderHero();
  renderMain();

  // Auto-generate plan only when explicitly coming from the lookup tab
  if (_urlParams.get("autoplan") === "1") {
    setTimeout(() => {
      document.getElementById("btn-generate-plan")?.scrollIntoView({ behavior: "smooth", block: "center" });
      generatePlan();
    }, 600);
  }
}

/* ===== HERO ===== */
function renderHero() {
  const hero = document.getElementById("dest-hero");
  const nav  = document.getElementById("dest-hero-nav");

  if (_heroPhotos.length) {
    hero.style.backgroundImage = `url('${_heroPhotos[0]}')`;
  }

  const d = _destData;
  const inSeason = (d.best_months || []).includes(new Date().getMonth() + 1);

  document.getElementById("dest-hero-content").innerHTML = `
    <div class="dest-hero-eyebrow">${d.state} · ${d.region}</div>
    <h1 class="dest-hero-title">${d.name}</h1>
    <p class="dest-hero-sub">${d.description || ""}</p>
    <div class="dest-hero-badges">
      <span class="dest-hero-badge accent">${d.primary_vibe || ""}</span>
      <span class="dest-hero-badge">🗓 ${d.min_days}–${d.max_days} days</span>
      <span class="dest-hero-badge">₹${(d.avg_cost_mid||0).toLocaleString("en-IN")}/day</span>
      <span class="dest-hero-badge">${inSeason ? "✓ In season" : "⚠ Off season"}</span>
      ${_heroPhotos.length ? `<span class="dest-hero-badge" style="cursor:pointer" onclick="scrollToGallery()">📷 ${_heroPhotos.length} Photos</span>` : ""}
    </div>
  `;

  if (_heroPhotos.length > 1) {
    nav.style.display = "flex";
    renderHeroDots();
  }
}

function renderHeroDots() {
  document.getElementById("hero-dots").innerHTML =
    _heroPhotos.map((_, i) =>
      `<span class="photo-dot${i === _heroIdx ? " active" : ""}"></span>`
    ).join("");
}

function heroNav(dir) {
  _heroIdx = (_heroIdx + dir + _heroPhotos.length) % _heroPhotos.length;
  document.getElementById("dest-hero").style.backgroundImage =
    `url('${_heroPhotos[_heroIdx]}')`;
  renderHeroDots();
}

/* ===== MAIN ===== */
function renderMain() {
  const main = document.getElementById("dest-main");
  main.style.display = "flex";

  renderGallery();
  renderOverview();
  renderVibes();
  renderHighlights();
  renderFood();
  renderMonths();
  renderTransport();
  loadSimilar();
}

function renderGallery() {
  if (!_galleryPhotos.length) return;
  const section = document.getElementById("gallery-section");
  const grid    = document.getElementById("dest-gallery-grid");
  section.style.display = "block";
  grid.innerHTML = _galleryPhotos.map((url, i) => `
    <div class="dest-gallery-thumb" onclick="openLightbox(${i})">
      <img src="${url}" alt="Photo ${i+1}" loading="lazy" />
    </div>
  `).join("");
}

function scrollToGallery() {
  document.getElementById("gallery-section")?.scrollIntoView({ behavior: "smooth" });
}

function renderOverview() {
  const d = _destData;
  document.getElementById("dest-description").innerHTML =
    `<p>${d.description || "No description available."}</p>`;

  const popularity = d.popularity != null
    ? "⭐".repeat(Math.round(d.popularity / 2)) + ` (${d.popularity}/10)`
    : "—";

  document.getElementById("dest-stats").innerHTML = [
    ["Region",      d.region],
    ["State",       d.state],
    ["Best for",    `${d.min_days}–${d.max_days} days`],
    ["Avg cost",    `₹${(d.avg_cost_mid||0).toLocaleString("en-IN")}/day`],
    ["Group type",  Array.isArray(d.group_suitability)
      ? d.group_suitability.join(", ")
      : Object.entries(d.group_suitability || {}).filter(([,v]) => v >= 0.75).map(([k]) => k).join(", ") || "—"],
    ["Popularity",  popularity],
  ].map(([label, value]) => `
    <div class="dest-stat">
      <div class="dest-stat-label">${label}</div>
      <div class="dest-stat-value">${value}</div>
    </div>
  `).join("");
}

function renderVibes() {
  const d = _destData;
  const vibes = d.vibes || [];
  document.getElementById("dest-vibes").innerHTML = vibes.map(v => `
    <span class="dest-vibe-tag ${v === d.primary_vibe ? "primary" : ""}">${v}</span>
  `).join("") || `<span style="color:var(--muted);font-size:.85rem">No vibes listed.</span>`;
}

function renderHighlights() {
  const highlights = _destData.highlights || [];
  document.getElementById("dest-highlights").innerHTML =
    highlights.length
      ? highlights.map(h => `<li>${h}</li>`).join("")
      : `<li style="color:var(--muted)">No highlights listed.</li>`;
}

function renderFood() {
  const foods = _destData.food_specialties || [];
  document.getElementById("dest-food").innerHTML =
    foods.length
      ? foods.map(f => `<span class="dest-food-tag">🍽 ${f}</span>`).join("")
      : `<span style="color:var(--muted);font-size:.85rem">No food info available.</span>`;
}

function renderMonths() {
  const best = new Set(_destData.best_months || []);
  document.getElementById("dest-months").innerHTML = MONTHS_SHORT.map((m, i) => `
    <div class="dest-month ${best.has(i+1) ? "good" : ""}">
      <span class="dest-month-name">${m}</span>
      <span class="dest-month-dot"></span>
    </div>
  `).join("");
}

function renderTransport() {
  const el = document.getElementById("dest-transport");
  el.innerHTML = `<p class="transport-loading">📍 Detecting your location for travel options…</p>`;

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => fetchTravelOptions(pos.coords.latitude, pos.coords.longitude),
      ()  => fetchTravelOptions(null, null),
      { timeout: 5000 }
    );
  } else {
    fetchTravelOptions(null, null);
  }
}

async function fetchTravelOptions(lat, lon) {
  const el = document.getElementById("dest-transport");
  let url = `${API_BASE}/api/destinations/${destId}/travel`;
  if (lat != null) url += `?lat=${lat}&lon=${lon}`;

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    const fromLabel = lat != null ? "your location" : "Delhi (default)";

    el.innerHTML = `
      <p class="transport-origin">Routes from <strong>${fromLabel}</strong> · ~${data.dist_km.toLocaleString("en-IN")} km away</p>
      <div class="dest-transport-grid">
        ${data.transport_options.map(t => `
          <div class="dest-transport-card">
            <div class="dest-transport-mode">${modeIcon(t.mode)} ${t.mode}</div>
            <div class="dest-transport-route">${t.route}</div>
            <div class="dest-transport-meta">
              <span class="transport-duration">⏱ ${t.duration}</span>
              <span class="transport-cost">₹${t.one_way_cost_inr.toLocaleString("en-IN")} one-way</span>
            </div>
            <div class="dest-transport-note">${t.notes}</div>
          </div>
        `).join("")}
      </div>
    `;
  } catch {
    el.innerHTML = `<p style="color:var(--muted);font-size:.85rem">Could not load travel options.</p>`;
  }
}

function modeIcon(mode) {
  if (mode.toLowerCase().includes("flight")) return "✈";
  if (mode.toLowerCase().includes("train"))  return "🚂";
  if (mode.toLowerCase().includes("bus"))    return "🚌";
  if (mode.toLowerCase().includes("drive") || mode.toLowerCase().includes("cab")) return "🚗";
  return "🗺";
}

/* ===== AI PLAN ===== */
async function generatePlan() {
  if (!_destData) return;

  const btn    = document.getElementById("btn-generate-plan");
  const output = document.getElementById("dest-plan-output");
  const days   = parseInt(document.getElementById("plan-days").value) || 5;
  const budget = parseInt(document.getElementById("plan-budget").value) || 2000;
  const group  = document.getElementById("plan-group").value;

  // Also render cost estimate now that we have days/budget/group
  renderCostEstimate(days, budget, group);

  if (_planController) _planController.abort();
  _planController = new AbortController();

  btn.disabled  = true;
  btn.textContent = "Generating…";
  output.innerHTML = `<div class="plan-loading-row"><div class="plan-spinner"></div><span>Generating your travel plan…</span></div>`;

  let raw = "";

  let success = false;
  try {
    const resp = await fetch(`${API_BASE}/api/generate`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        destination_id: _destData.id,
        days, budget_per_day: budget, group_type: group,
        vibes: _destData.vibes || [], query: "",
      }),
      signal: _planController.signal,
    });

    if (!resp.ok) throw new Error(`${resp.status}`);

    output.innerHTML = `<span class="plan-source-badge plan-source-live">🌐 Knowledge Base + Live Web</span>`;

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const token = line.slice(6);
        if (token === "[DONE]") break;
        raw += token.replace(/\\n/g, "\n");
        const badge = output.querySelector(".plan-source-badge");
        const badgeHTML = badge ? badge.outerHTML : "";
        output.innerHTML = badgeHTML + (typeof marked !== "undefined" ? marked.parse(raw) : raw);
      }
    }
    _lastPlanMarkdown = raw;
    success = true;
  } catch (err) {
    if (err.name === "AbortError") return;
    output.innerHTML = `<p style="color:#f87171">Failed to generate plan — <button class="btn-retry-plan" onclick="generatePlan()">↺ Retry</button></p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Plan";
  }

  // Show Save Trip button after a successful generation
  if (success && TravelAuth.isLoggedIn()) {
    const controls = document.querySelector(".dest-plan-controls");
    if (controls && !document.getElementById("btn-save-dest-trip")) {
      const saveBtn = document.createElement("button");
      saveBtn.id = "btn-save-dest-trip";
      saveBtn.className = "btn-generate-plan";
      saveBtn.style.cssText = "background:none;border:1.5px solid var(--accent);color:var(--accent);";
      saveBtn.textContent = "💾 Save Trip";
      saveBtn.onclick = saveDestTrip;
      controls.appendChild(saveBtn);
    }
  }
}

async function saveDestTrip() {
  const btn = document.getElementById("btn-save-dest-trip");
  if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }

  const days   = parseInt(document.getElementById("plan-days").value) || 5;
  const budget = parseInt(document.getElementById("plan-budget").value) || 2000;
  const group  = document.getElementById("plan-group").value;
  const planMd = _lastPlanMarkdown || "";

  const id = await TravelAuth.saveTrip({
    destination:  _destData,
    planMarkdown: planMd,
    days, budgetPerDay: budget, groupType: group,
    vibes:    _destData.vibes || [],
    photoUrl: _heroPhotos[0] || null,
  });

  if (btn) {
    btn.textContent = id ? "✓ Saved" : "💾 Save Trip";
    btn.disabled = !!id;
    if (id) btn.style.color = "var(--accent)";
  }
}

/* ===== COST ESTIMATE ===== */
async function renderCostEstimate(days, budget, group) {
  // Use the search endpoint trick: just pull from a search for this destination
  // Actually we'll just show a basic cost breakdown from destination data
  const section = document.getElementById("cost-section");
  const el      = document.getElementById("dest-cost");
  const d       = _destData;

  const occupancy = { solo: 1, couple: 2, friends: 2.5, family: 2 }[group] || 2;
  const avgMid    = d.avg_cost_mid || 2000;
  const acc       = Math.round(avgMid * 0.42 * days);
  const food      = Math.round(avgMid * 0.30 * days);
  const local     = 350 * days;
  const total     = acc + food + local;
  const gap       = total - budget * days;

  el.innerHTML = `
    <div class="dest-cost-grid">
      ${[
        ["Accommodation", `₹${acc.toLocaleString("en-IN")}`],
        ["Food",          `₹${food.toLocaleString("en-IN")}`],
        ["Local Transport",`₹${local.toLocaleString("en-IN")}`],
        ["Days",          `${days} days`],
      ].map(([label, value]) => `
        <div class="dest-cost-item">
          <div class="dest-cost-label">${label}</div>
          <div class="dest-cost-value">${value}</div>
        </div>
      `).join("")}
    </div>
    <div class="dest-cost-total">
      <span class="dest-cost-total-label">${gap > 0 ? "⚠ Over budget by" : "✓ Under budget"}</span>
      <span class="dest-cost-total-value">₹${total.toLocaleString("en-IN")} total</span>
    </div>
  `;
  section.style.display = "block";
}

/* ===== LIGHTBOX ===== */
function openLightbox(idx) {
  _lightboxIdx = idx;
  const lb  = document.getElementById("dest-lightbox");
  const img = document.getElementById("lightbox-img");
  img.src   = _galleryPhotos[idx];
  lb.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  document.getElementById("dest-lightbox").style.display = "none";
  document.body.style.overflow = "";
}

function lightboxNav(dir) {
  _lightboxIdx = (_lightboxIdx + dir + _galleryPhotos.length) % _galleryPhotos.length;
  document.getElementById("lightbox-img").src = _galleryPhotos[_lightboxIdx];
}

// Keyboard nav
document.addEventListener("keydown", e => {
  const lb = document.getElementById("dest-lightbox");
  if (lb.style.display !== "none") {
    if (e.key === "ArrowLeft")  lightboxNav(-1);
    if (e.key === "ArrowRight") lightboxNav(1);
    if (e.key === "Escape")     closeLightbox();
  }
});

/* ===== SIMILAR DESTINATIONS ===== */
async function loadSimilar() {
  try {
    const resp = await fetch(`${API_BASE}/api/destinations/${destId}/similar?n=3`);
    if (!resp.ok) return;
    const similar = await resp.json();
    if (!similar.length) return;

    // Fetch a photo for each
    const withPhotos = await Promise.all(similar.map(async d => {
      try {
        const pr = await fetch(`${API_BASE}/api/photos/${d.id}?count=1`);
        const pd = pr.ok ? await pr.json() : {};
        return { ...d, photo: (pd.photo_urls || [])[0] || null };
      } catch { return { ...d, photo: null }; }
    }));

    const section = document.getElementById("similar-section");
    const grid    = document.getElementById("similar-grid");
    section.style.display = "block";

    grid.innerHTML = withPhotos.map(d => {
      const inSeason = (d.best_months || []).includes(new Date().getMonth() + 1);
      const photoStyle = d.photo
        ? `style="background-image:url('${d.photo}');background-size:cover;background-position:center"`
        : "";
      return `
        <a class="similar-card" href="/destination.html?id=${d.id}">
          <div class="similar-card-hero ${d.photo ? 'has-photo' : ''}" data-vibe="${d.primary_vibe || ''}" ${photoStyle}>
            <div class="similar-card-overlay"></div>
            <div class="similar-card-name">${d.name}</div>
            <div class="similar-card-state">${d.state}</div>
          </div>
          <div class="similar-card-body">
            <span class="dest-vibe-tag primary" style="font-size:.7rem">${d.primary_vibe || ''}</span>
            <span class="dest-vibe-tag" style="font-size:.7rem">${inSeason ? '✓ In season' : '⚠ Off season'}</span>
            <div class="similar-card-cost">₹${(d.avg_cost_mid||0).toLocaleString('en-IN')}/day</div>
          </div>
        </a>`;
    }).join("");
  } catch { /* silent fail */ }
}

/* ===== PACKING LIST ===== */
let _packingController = null;

async function generatePackingList() {
  if (!_destData) return;

  const btn    = document.getElementById("btn-packing-list");
  const output = document.getElementById("packing-output");
  const days   = parseInt(document.getElementById("plan-days").value) || 5;
  const group  = document.getElementById("plan-group").value;
  const month  = new Date().getMonth() + 1;

  if (_packingController) _packingController.abort();
  _packingController = new AbortController();

  btn.disabled    = true;
  btn.textContent = "Generating…";
  output.innerHTML = `<div class="plan-loading-row"><div class="plan-spinner"></div><span>Building your packing list…</span></div>`;

  let raw = "";
  try {
    const resp = await fetch(`${API_BASE}/api/packing-list`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        destination_id: _destData.id,
        days, group_type: group,
        vibes: _destData.vibes || [],
        travel_month: month,
      }),
      signal: _packingController.signal,
    });

    if (!resp.ok) throw new Error(`${resp.status}`);

    output.innerHTML = "";
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const token = line.slice(6);
        if (token === "[DONE]") break;
        raw += token.replace(/\\n/g, "\n");
        output.innerHTML = (typeof marked !== "undefined" ? marked.parse(raw) : raw);
      }
    }

    // Add copy button after generation
    const copyBtn = document.createElement("button");
    copyBtn.className = "btn-copy-packing";
    copyBtn.textContent = "📋 Copy List";
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(raw).then(() => {
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => { copyBtn.textContent = "📋 Copy List"; }, 2000);
      });
    };
    output.appendChild(copyBtn);

  } catch (err) {
    if (err.name === "AbortError") return;
    output.innerHTML = `<p style="color:#f87171">Failed — <button class="btn-retry-plan" onclick="generatePackingList()">↺ Retry</button></p>`;
  } finally {
    btn.disabled    = false;
    btn.textContent = "🎒 Regenerate";
  }
}
