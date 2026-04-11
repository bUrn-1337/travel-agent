const API_BASE = window.location.port === "3000" || window.location.port === "80" || window.location.port === ""
  ? "" : "http://localhost:8000";

const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

let _destData   = null;
let _heroPhotos = [];
let _heroIdx    = 0;
let _galleryPhotos = [];
let _lightboxIdx   = 0;
let _planController = null;

/* ===== INIT ===== */
const destId = new URLSearchParams(window.location.search).get("id");

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
    ["Group type",  (d.group_suitability || []).join(", ") || "—"],
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
  const d = _destData;
  const items = [
    d.nearest_airport  ? { mode: "✈ Airport",  info: d.nearest_airport }  : null,
    d.nearest_railway  ? { mode: "🚂 Railway",  info: d.nearest_railway }  : null,
    d.nearest_bus_stand? { mode: "🚌 Bus Stand", info: d.nearest_bus_stand }: null,
  ].filter(Boolean);

  document.getElementById("dest-transport").innerHTML = items.length
    ? items.map(t => `
        <div class="dest-transport-card">
          <div class="dest-transport-mode">${t.mode}</div>
          <div class="dest-transport-info">${t.info}</div>
        </div>
      `).join("")
    : `<p style="color:var(--muted);font-size:.85rem">No transport info available.</p>`;
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
  } catch (err) {
    if (err.name === "AbortError") return;
    output.innerHTML = `<p style="color:#f87171">Failed to generate plan — <button class="btn-retry-plan" onclick="generatePlan()">↺ Retry</button></p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Plan";
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
