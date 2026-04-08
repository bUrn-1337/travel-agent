/* ===== CONFIG ===== */
// Empty string = same origin (works both in Docker via nginx proxy and direct localhost:8000 dev)
const API_BASE = window.location.port === "3000" || window.location.port === "80" || window.location.port === ""
  ? ""
  : "http://localhost:8000";

// GPS state
let _userLat = null;
let _userLon = null;

// Active SSE controllers for top-pick generation (cancel on new search)
let _genControllers = [];

// P4: Map + filter state
let _map         = null;
let _allGeoMarkers = {};   // id → Leaflet marker (all 144)
let _allGeo      = [];     // full geo payload from /api/destinations/geo
let _activeFilters = { region: "", budget: "", season: "" };
let _filteredResults = [];

/* ===== VIBES CONFIG ===== */
const VIBES = [
  { id: "mountains",  label: "Mountains",   icon: "⛰️" },
  { id: "beach",      label: "Beach",        icon: "🏖️" },
  { id: "heritage",   label: "Heritage",     icon: "🏛️" },
  { id: "adventure",  label: "Adventure",    icon: "🧗" },
  { id: "wildlife",   label: "Wildlife",     icon: "🐯" },
  { id: "spiritual",  label: "Spiritual",    icon: "🙏" },
  { id: "offbeat",    label: "Offbeat",      icon: "🔭" },
  { id: "desert",     label: "Desert",       icon: "🏜️" },
  { id: "backwaters", label: "Backwaters",   icon: "🚤" },
  { id: "nature",     label: "Nature",       icon: "🌿" },
  { id: "honeymoon",  label: "Honeymoon",    icon: "💑" },
  { id: "trekking",   label: "Trekking",     icon: "🥾" },
];

const MONTHS = ["", "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/* ===== STATE ===== */
let selectedVibes = new Set();
let lastResults = [];
let lastRequestedVibes = [];

/* ===== INIT ===== */
document.addEventListener("DOMContentLoaded", () => {
  renderVibeChips();
  bindRangeSliders();
  bindRadioButtons();
  initMap();
  bindFilterChips();
  renderSavedSection();
});

function renderVibeChips() {
  const grid = document.getElementById("vibes-grid");
  grid.innerHTML = VIBES.map(v => `
    <button class="vibe-chip" data-id="${v.id}" onclick="toggleVibe('${v.id}', this)">
      <span>${v.icon}</span> ${v.label}
    </button>
  `).join("");
}

function toggleVibe(id, el) {
  if (selectedVibes.has(id)) {
    selectedVibes.delete(id);
    el.classList.remove("selected");
  } else {
    selectedVibes.add(id);
    el.classList.add("selected");
  }
}

function bindRangeSliders() {
  const daysSlider = document.getElementById("days");
  const daysVal   = document.getElementById("days-val");
  daysSlider.addEventListener("input", () => { daysVal.textContent = daysSlider.value; });

  const budgetSlider = document.getElementById("budget");
  const budgetVal    = document.getElementById("budget-val");
  budgetSlider.addEventListener("input", () => {
    budgetVal.textContent = "₹" + Number(budgetSlider.value).toLocaleString("en-IN");
  });
}

function bindRadioButtons() {
  document.querySelectorAll('input[name="group"]').forEach(radio => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".radio-btn").forEach(btn => btn.classList.remove("active"));
      radio.closest(".radio-btn").classList.add("active");
    });
  });
}

function getGroupType() {
  const checked = document.querySelector('input[name="group"]:checked');
  return checked ? checked.value : "friends";
}

/* ===== GPS ===== */
function getGPS() {
  const btn    = document.getElementById("btn-gps");
  const status = document.getElementById("gps-status");

  if (!navigator.geolocation) {
    status.textContent = "Geolocation not supported by your browser.";
    return;
  }

  btn.textContent = "⏳";
  status.textContent = "Getting location...";

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      _userLat = pos.coords.latitude;
      _userLon = pos.coords.longitude;
      btn.textContent = "✅";
      btn.classList.add("active");
      status.textContent = `GPS: ${_userLat.toFixed(3)}, ${_userLon.toFixed(3)}`;
    },
    () => {
      btn.textContent = "📍";
      status.textContent = "Location denied — distance scoring disabled.";
      _userLat = null;
      _userLon = null;
    }
  );
}

/* ===== SEARCH ===== */
async function doSearch() {
  const city   = document.getElementById("city").value.trim();
  const days   = parseInt(document.getElementById("days").value);
  const budget = parseInt(document.getElementById("budget").value);
  const group  = getGroupType();
  const month  = parseInt(document.getElementById("month").value);
  const query  = document.getElementById("query").value.trim();
  const topK   = parseInt(document.getElementById("top-k").value);

  const payload = {
    city,
    vibes:          [...selectedVibes],
    days,
    budget_per_day: budget,
    group_type:     group,
    query,
    travel_month:   month,
    top_k:          topK,
    user_lat:       _userLat,
    user_lon:       _userLon,
  };

  // Cancel any previous generation streams
  _genControllers.forEach(c => c.abort());
  _genControllers = [];

  showLoader();
  hideError();
  hideResults();

  try {
    const resp = await fetch(`${API_BASE}/api/search`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }

    const data = await resp.json();
    lastResults        = data.destinations;
    lastRequestedVibes = payload.vibes;

    // P4: update map pin colors + zoom to results
    updateMapScores(lastResults);

    // P4: reset filters on new search
    resetFilters();

    // Render top picks with auto-generation
    renderTopPicks(data.top_picks, data.query_info, payload);

    // Render full collapsible list
    renderResults(lastResults, data.query_info);
  } catch (err) {
    showError(`Could not reach the search server. Make sure the backend is running.\n${err.message}`);
  } finally {
    hideLoader();
  }
}

/* ===== TOP PICKS — auto-generate plans ===== */
function renderTopPicks(topPicks, queryInfo, searchPayload) {
  const section  = document.getElementById("top-picks-section");
  const grid     = document.getElementById("top-picks-grid");
  const sub      = section.querySelector(".top-picks-sub");
  const gpsBadge = document.getElementById("gps-badge");

  if (!topPicks || topPicks.length === 0) return;

  section.style.display = "block";
  sub.textContent = `Generating personalised travel plans for your top ${topPicks.length} matches...`;

  if (queryInfo.gps_active) gpsBadge.style.display = "inline";
  else gpsBadge.style.display = "none";

  // P3: Render comparison table first (uses cost_estimate from search response)
  const compEl = document.getElementById("comparison-table-wrap");
  if (compEl) compEl.innerHTML = renderComparisonTable(topPicks, searchPayload);

  grid.innerHTML = topPicks.map((dest, i) => topPickCard(dest, i + 1)).join("");

  // Auto-trigger streaming generation for each top pick in parallel
  topPicks.forEach((dest) => {
    const planPayload = {
      destination_id: dest.id,
      days:           searchPayload.days,
      budget_per_day: searchPayload.budget_per_day,
      group_type:     searchPayload.group_type,
      vibes:          searchPayload.vibes,
      query:          searchPayload.query || "",
    };
    streamPlanIntoCard(dest.id, planPayload);
  });
}

/* ===== P3: COMPARISON TABLE ===== */
function renderComparisonTable(topPicks, searchPayload) {
  if (!topPicks || topPicks.length === 0) return "";

  const days = searchPayload.days || 5;

  // Find best (lowest total cost) and worst among top picks
  const totals = topPicks.map(d => d.cost_estimate?.per_person?.total || 0);
  const minTotal = Math.min(...totals);
  const maxTotal = Math.max(...totals);

  const headerCells = topPicks.map((d, i) => `
    <th>
      <div class="compare-dest-name">#${i+1} ${d.name}</div>
      <div class="compare-dest-state">${d.state}</div>
    </th>`).join("");

  const rows = [
    {
      label: "Match Score",
      cells: topPicks.map(d => {
        const pct = Math.round((d.score || 0) * 100);
        return `<td>${pct}%</td>`;
      }),
    },
    {
      label: "Est. Total (per person)",
      cells: topPicks.map((d) => {
        const total = d.cost_estimate?.per_person?.total || 0;
        const fits  = d.cost_estimate?.fits_budget;
        const cls   = total === minTotal ? " best" : (total === maxTotal && minTotal !== maxTotal ? " worst" : "");
        const badge = `<span class="fits-badge ${fits ? 'fits-yes' : 'fits-no'}">${fits ? "Fits budget" : "Over budget"}</span>`;
        return `<td class="${cls}">₹${total.toLocaleString("en-IN")}<br>${badge}</td>`;
      }),
    },
    {
      label: "Transport (return)",
      cells: topPicks.map(d => {
        const v = d.cost_estimate?.per_person?.transport_return || 0;
        return `<td>₹${v.toLocaleString("en-IN")}</td>`;
      }),
    },
    {
      label: "Accommodation",
      cells: topPicks.map(d => {
        const v = d.cost_estimate?.per_person?.accommodation || 0;
        return `<td>₹${v.toLocaleString("en-IN")}</td>`;
      }),
    },
    {
      label: "Food",
      cells: topPicks.map(d => {
        const v = d.cost_estimate?.per_person?.food || 0;
        return `<td>₹${v.toLocaleString("en-IN")}</td>`;
      }),
    },
    {
      label: "Activities",
      cells: topPicks.map(d => {
        const v = d.cost_estimate?.per_person?.activities || 0;
        return `<td>₹${v.toLocaleString("en-IN")}</td>`;
      }),
    },
    {
      label: "Distance from you",
      cells: topPicks.map(d => {
        const km = d.cost_estimate?.dist_from_origin_km;
        return `<td>${km != null ? km + " km" : "—"}</td>`;
      }),
    },
    {
      label: "Best Transport",
      cells: topPicks.map(d => {
        const opts = d.cost_estimate?.transport_options || [];
        if (!opts.length) return "<td>—</td>";
        const cheapest = opts.reduce((a, b) => a.one_way_cost_inr < b.one_way_cost_inr ? a : b);
        return `<td>${cheapest.mode}<br><span style="font-size:.72rem;color:var(--muted)">${cheapest.duration}</span></td>`;
      }),
    },
  ];

  const bodyRows = rows.map(row => `
    <tr>
      <td class="row-label">${row.label}</td>
      ${row.cells.join("")}
    </tr>`).join("");

  return `
    <div class="comparison-section">
      <div style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:.65rem">
        Side-by-Side Comparison · ${days}-day trip per person
      </div>
      <div class="comparison-table-wrap">
        <table class="comparison-table">
          <thead>
            <tr><th style="min-width:120px">Category</th>${headerCells}</tr>
          </thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    </div>`;
}

function topPickCard(dest, rank) {
  const score   = dest.score || 0;
  const pct     = Math.round(score * 100);
  const vibes   = (dest.vibes || []).slice(0, 4);
  const reqSet  = new Set(lastRequestedVibes);
  const bestMonths = dest.best_months || [];
  const inSeason   = bestMonths.includes(new Date().getMonth() + 1);

  const vibeHTML = vibes.map(v =>
    `<span class="vibe-tag ${reqSet.has(v) ? "matched" : ""}">${v}</span>`
  ).join("");

  return `
  <div class="top-pick-card" id="pick-card-${dest.id}">
    <div class="top-pick-hero">
      <div class="pick-rank">#${rank} Best Match</div>
      <div class="pick-name">${dest.name}</div>
      <div class="pick-state">${dest.state} · ${dest.region}</div>
      <div class="pick-meta">
        <span class="pick-meta-item">🗓 ${dest.min_days}–${dest.max_days} days</span>
        <span class="pick-meta-item">₹${(dest.avg_cost_mid||0).toLocaleString("en-IN")}/day</span>
        <span class="pick-meta-item">${inSeason ? "✓ In season" : "⚠ Off season"}</span>
      </div>
    </div>
    <div class="pick-body">
      <div class="pick-score-row">
        <span class="pick-score-label">Match score</span>
        <div class="pick-score-bar">
          <div class="pick-score-fill" style="width:${pct}%"></div>
        </div>
        <span class="pick-score-val">${pct}%</span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:.35rem;margin-bottom:.75rem">${vibeHTML}</div>
    </div>
    <div class="plan-output-wrap">
      <div class="plan-loading" id="plan-loading-${dest.id}">
        <div class="plan-spinner"></div>
        <span>Generating travel plan...</span>
      </div>
      <div class="plan-output" id="plan-output-${dest.id}" style="display:none;"></div>
    </div>
    <div class="pick-save-row">
      <button class="btn-save pick-save-btn" onclick='toggleSave(${JSON.stringify(dest)})' id="save-btn-${dest.id}">
        ${isSaved(dest.id) ? "★ Saved" : "☆ Save"}
      </button>
    </div>
  </div>`;
}

async function streamPlanIntoCard(destId, payload) {
  const loadingEl = document.getElementById(`plan-loading-${destId}`);
  const outputEl  = document.getElementById(`plan-output-${destId}`);
  const section   = document.querySelector(".top-picks-sub");

  const controller = new AbortController();
  _genControllers.push(controller);

  let rawMarkdown = "";

  try {
    const resp = await fetch(`${API_BASE}/api/generate`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
      signal:  controller.signal,
    });

    if (!resp.ok) throw new Error(`Server error ${resp.status}`);

    loadingEl.style.display = "none";
    outputEl.style.display  = "block";

    // Show source badge
    outputEl.innerHTML = `<span class="plan-source-badge plan-source-live">
      🌐 Knowledge Base + Live Web
    </span>`;

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
        rawMarkdown += token.replace(/\\n/g, "\n");
        const badge = outputEl.querySelector(".plan-source-badge");
        const badgeHTML = badge ? badge.outerHTML : "";
        if (typeof marked !== "undefined") {
          outputEl.innerHTML = badgeHTML + marked.parse(rawMarkdown);
        } else {
          outputEl.textContent = rawMarkdown;
        }
      }
    }

    if (section) section.textContent = "Travel plans ready.";

  } catch (err) {
    if (err.name === "AbortError") return;
    if (loadingEl) loadingEl.style.display = "none";
    if (outputEl) {
      outputEl.style.display = "block";
      outputEl.innerHTML = `<p style="color:#dc2626;font-size:.8rem">
        Could not generate plan: ${err.message}
      </p>`;
    }
  }
}

/* ===== SORT ===== */
function sortResults() {
  const sortBy = document.getElementById("sort-by").value;
  const sorted = [...lastResults];

  if (sortBy === "score")       sorted.sort((a, b) => b.score - a.score);
  else if (sortBy === "budget") sorted.sort((a, b) => a.avg_cost_mid - b.avg_cost_mid);
  else if (sortBy === "popularity") sorted.sort((a, b) => b.popularity - a.popularity);
  else if (sortBy === "vibe_match") sorted.sort((a, b) => b.score_breakdown.vibe_match - a.score_breakdown.vibe_match);

  renderResults(sorted, null);
}

/* ===== RENDER ===== */
function renderResults(destinations, queryInfo) {
  const section = document.getElementById("results-section");
  const grid    = document.getElementById("results-grid");
  const title   = document.getElementById("results-title");

  section.style.display = "block";

  if (queryInfo) {
    const sem = queryInfo.semantic_enabled ? " · semantic search on" : " · keyword search only";
    title.textContent = `${destinations.length} destinations found${sem}`;
  }

  grid.innerHTML = destinations.map((dest, i) => destinationCard(dest, i + 1)).join("");
}

function destinationCard(dest, rank) {
  const score   = dest.score || 0;
  const bd      = dest.score_breakdown || {};
  const vibes   = (dest.vibes || []);
  const reqSet  = new Set(lastRequestedVibes);
  const bestMonths = dest.best_months || [];
  const currentMonth = new Date().getMonth() + 1;
  const inSeason = bestMonths.includes(currentMonth);

  const vibeHTML = vibes.slice(0, 5).map(v => {
    const matched = reqSet.has(v) ? "matched" : "";
    return `<span class="vibe-tag ${matched}">${v}</span>`;
  }).join("");

  const scorePercent = Math.round(score * 100);

  const breakdownHTML = Object.entries(bd).map(([key, val]) => {
    const pct = Math.round(val * 100);
    const color = pct >= 70 ? "#16a34a" : pct >= 40 ? "#d97706" : "#dc2626";
    const label = key.replace("_", " ");
    return `
      <div class="mini-bar-row">
        <span class="mini-label">${label}</span>
        <div class="mini-bar">
          <div class="mini-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <span style="font-size:.68rem;color:${color};font-weight:700;min-width:26px">${pct}%</span>
      </div>`;
  }).join("");

  return `
  <div class="result-card" onclick="showModal(${JSON.stringify(dest).replace(/"/g, '&quot;')})">
    <div class="card-header">
      <div class="card-rank">#${rank}</div>
      <div class="card-name">${dest.name}</div>
      <div class="card-state">${dest.state} · ${dest.region}</div>
    </div>
    <div class="card-body">
      <div class="score-bar-row">
        <span class="score-label">Match</span>
        <div class="score-bar"><div class="score-fill" style="width:${scorePercent}%"></div></div>
        <span class="score-val">${scorePercent}%</span>
      </div>
      <div class="breakdown-grid">${breakdownHTML}</div>
      <div class="card-vibes">${vibeHTML}</div>
      <p class="card-description">${dest.description || ""}</p>
      <div class="card-meta">
        <div class="meta-row"><span>✈️</span><span>${dest.nearest_airport || "—"}</span></div>
        <div class="meta-row"><span>🕐</span><span>${dest.min_days}–${dest.max_days} days recommended</span></div>
      </div>
    </div>
    <div class="card-footer">
      <span class="cost-badge">~₹${(dest.avg_cost_mid || 0).toLocaleString("en-IN")}/day (mid)</span>
      <span class="season-badge ${inSeason ? "season-good" : "season-bad"}">
        ${inSeason ? "✓ In season" : "⚠ Off season"}
      </span>
      <button class="btn-save card-save-btn" onclick='event.stopPropagation();toggleSave(${JSON.stringify(dest).replace(/"/g,"&quot;")})' id="save-btn-${dest.id}">
        ${isSaved(dest.id) ? "★" : "☆"}
      </button>
    </div>
  </div>`;
}

/* ===== MODAL ===== */
function showModal(dest) {
  const overlay = document.getElementById("modal-overlay");
  const content = document.getElementById("modal-content");
  const bd      = dest.score_breakdown || {};
  const reqSet  = new Set(lastRequestedVibes);

  const bestMonths = (dest.best_months || []).map(m => MONTHS[m]).join(", ");
  const highlights = (dest.highlights || []).map(h => `<span class="tag">${h}</span>`).join("");
  const food       = (dest.food_specialties || []).map(f => `<span class="tag">${f}</span>`).join("");
  const accTypes   = (dest.accommodation || []).map(a => `<span class="tag">${a}</span>`).join("");
  const vibeHTML   = (dest.vibes || []).map(v => {
    const matched = reqSet.has(v) ? "matched" : "";
    return `<span class="vibe-tag ${matched}">${v}</span>`;
  }).join(" ");

  const breakdownHTML = Object.entries(bd).map(([key, val]) => {
    const pct = Math.round(val * 100);
    const color = pct >= 70 ? "#16a34a" : pct >= 40 ? "#d97706" : "#dc2626";
    const label = key.replace(/_/g, " ");
    return `
      <div class="mini-bar-row" style="margin-bottom:.4rem">
        <span class="mini-label" style="width:90px">${label}</span>
        <div class="mini-bar" style="height:7px">
          <div class="mini-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <span style="font-size:.78rem;color:${color};font-weight:700;min-width:36px;text-align:right">${pct}%</span>
      </div>`;
  }).join("");

  content.innerHTML = `
    <div class="modal-hero">
      <h2>${dest.name}</h2>
      <p>${dest.state} · ${dest.region}</p>
      <div style="margin-top:.75rem;display:flex;gap:.5rem;flex-wrap:wrap">${vibeHTML}</div>
    </div>
    <div class="modal-body">
      <div class="modal-section">
        <h3>About</h3>
        <p style="font-size:.88rem;line-height:1.65;color:#374151">${dest.description || ""}</p>
      </div>

      <div class="modal-section">
        <h3>Match Score Breakdown</h3>
        <div class="modal-score-section">
          <div style="font-size:1.3rem;font-weight:800;color:#2563eb;margin-bottom:.75rem">
            Overall: ${Math.round((dest.score || 0) * 100)}%
          </div>
          ${breakdownHTML}
        </div>
      </div>

      <div class="modal-section">
        <h3>Highlights</h3>
        <div class="tag-list">${highlights}</div>
      </div>

      <div class="modal-section">
        <h3>Food Specialties</h3>
        <div class="tag-list">${food}</div>
      </div>

      <div class="modal-section">
        <h3>Accommodation Types</h3>
        <div class="tag-list">${accTypes}</div>
      </div>

      <div class="modal-section">
        <h3>Trip Info</h3>
        <div class="info-table">
          <span class="info-key">Duration</span>
          <span>${dest.min_days}–${dest.max_days} days</span>
          <span class="info-key">Budget/day</span>
          <span>
            Budget ₹${(dest.avg_cost_budget||0).toLocaleString("en-IN")} ·
            Mid ₹${(dest.avg_cost_mid||0).toLocaleString("en-IN")} ·
            Luxury ₹${(dest.avg_cost_luxury||0).toLocaleString("en-IN")}
          </span>
          <span class="info-key">Best Months</span>
          <span>${bestMonths}</span>
          <span class="info-key">Nearest Airport</span>
          <span>${dest.nearest_airport || "—"}</span>
          <span class="info-key">Nearest Rail</span>
          <span>${dest.nearest_railway || "—"}</span>
          <span class="info-key">Popularity</span>
          <span>${dest.popularity}/10</span>
        </div>
      </div>

      <!-- RAG GENERATE BUTTON -->
      <div class="modal-section">
        <h3>AI Travel Plan (RAG + Structured)</h3>
        <p style="font-size:.82rem;color:#64748b;margin-bottom:.75rem">
          Generates a structured itinerary, food guide, transport breakdown &amp; accommodation
          using retrieved knowledge base chunks + LLM (Groq/Gemini if configured).
        </p>
        <div style="display:flex;gap:.6rem;flex-wrap:wrap">
          <button class="btn-generate" id="btn-generate" onclick="generatePlanStructured('${dest.id}')">
            Generate Structured Plan
          </button>
          <button class="btn-save" id="btn-save-modal" onclick="toggleSave(${JSON.stringify(dest).replace(/"/g, '&quot;')})">
            ${isSaved(dest.id) ? "★ Saved" : "☆ Save"}
          </button>
        </div>
      </div>

      <!-- STRUCTURED OUTPUT -->
      <div id="rag-output-wrap" style="display:none;" class="modal-section">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem">
          <h3 style="margin:0">Generated Plan</h3>
          <div style="display:flex;gap:.5rem">
            <button class="btn-export" onclick="exportPlan('clipboard')" title="Copy to clipboard">📋 Copy</button>
            <button class="btn-export" onclick="exportPlan('print')" title="Print / Save PDF">🖨 Print</button>
          </div>
        </div>
        <div id="rag-output" class="rag-output"></div>
      </div>

      <!-- REFINEMENT CHAT -->
      <div id="refine-wrap" style="display:none;" class="modal-section">
        <h3>Ask a Follow-up</h3>
        <div class="refine-chat" id="refine-chat"></div>
        <div class="refine-input-row">
          <input type="text" id="refine-input" class="refine-input"
            placeholder="e.g. Suggest budget hotels · Make day 2 vegetarian-friendly · Best time to avoid crowds"
            onkeydown="if(event.key==='Enter') sendRefinement('${dest.id}')" />
          <button class="btn-refine" onclick="sendRefinement('${dest.id}')">Ask</button>
        </div>
      </div>
    </div>
  `;

  overlay.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeModal() {
  document.getElementById("modal-overlay").style.display = "none";
  document.body.style.overflow = "";
  // Cancel modal-level generation if any
  if (window._modalGenController) {
    window._modalGenController.abort();
    window._modalGenController = null;
  }
}

/* ===== P3: STRUCTURED GENERATION (modal) ===== */
async function generatePlanStructured(destId) {
  const btn    = document.getElementById("btn-generate");
  const wrap   = document.getElementById("rag-output-wrap");
  const output = document.getElementById("rag-output");

  const days      = parseInt(document.getElementById("days").value)   || 5;
  const budget    = parseInt(document.getElementById("budget").value) || 2000;
  const groupType = getGroupType();
  const query     = document.getElementById("query").value.trim();

  btn.disabled    = true;
  btn.textContent = "Generating…";
  wrap.style.display = "block";
  output.innerHTML   = '<div class="rag-spinner"></div><p style="text-align:center;color:var(--muted);font-size:.82rem;margin-top:.5rem">Building your structured travel plan…</p>';

  const payload = {
    destination_id: destId,
    days,
    budget_per_day: budget,
    group_type:     groupType,
    vibes:          [...selectedVibes],
    query,
  };

  try {
    const resp = await fetch(`${API_BASE}/api/generate/structured`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }

    const data = await resp.json();
    output.innerHTML = renderStructuredPlan(data.plan, data.cost_estimate);

    // Store plan text for refinement + export
    window._currentPlanDestId = payload.destination_id;
    window._currentPlanText   = output.innerText;
    window._currentPlanPayload = payload;

    // Show refinement chat
    const refineWrap = document.getElementById("refine-wrap");
    if (refineWrap) refineWrap.style.display = "block";

  } catch (err) {
    output.innerHTML = `<p style="color:#dc2626">Error: ${err.message}<br>Make sure the backend is running and RAG is indexed.</p>`;
  } finally {
    btn.disabled    = false;
    btn.textContent = "Regenerate Plan";
  }
}


/* ===== EXPORT PLAN ===== */
function exportPlan(mode) {
  const output = document.getElementById("rag-output");
  if (!output) return;

  if (mode === "clipboard") {
    const text = output.innerText;
    navigator.clipboard.writeText(text).then(() => {
      const btn = event.target;
      const orig = btn.textContent;
      btn.textContent = "✓ Copied!";
      setTimeout(() => { btn.textContent = orig; }, 2000);
    }).catch(() => {
      // Fallback for browsers without clipboard API
      const ta = document.createElement("textarea");
      ta.value = output.innerText;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    });
    return;
  }

  if (mode === "print") {
    // Get destination name from modal hero
    const heroName = document.querySelector(".modal-hero h2")?.textContent || "Travel Plan";
    const printWindow = window.open("", "_blank");
    printWindow.document.write(`
      <!DOCTYPE html><html><head>
        <title>${heroName} — Travel Plan</title>
        <meta charset="UTF-8">
        <style>
          body { font-family: Georgia, serif; max-width: 800px; margin: 2rem auto; color: #111; line-height: 1.7; }
          h1 { color: #1e3a5f; border-bottom: 2px solid #2563eb; padding-bottom: .5rem; }
          h2 { color: #2563eb; margin-top: 1.5rem; }
          h3 { color: #374151; }
          table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
          th, td { border: 1px solid #e2e8f0; padding: .5rem .75rem; text-align: left; }
          th { background: #f1f5f9; font-weight: 700; }
          .day-card { border: 1px solid #e2e8f0; border-radius: 8px; margin: .75rem 0; padding: .75rem 1rem; }
          .tips-list li { background: #fffbeb; border-left: 3px solid #f59e0b; padding: .4rem .6rem; margin: .3rem 0; list-style: none; }
          @media print { body { margin: 1rem; } }
        </style>
      </head><body>
        <h1>${heroName}</h1>
        ${output.innerHTML}
      </body></html>`);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => printWindow.print(), 500);
  }
}


/* ===== REFINEMENT CHAT ===== */
async function sendRefinement(destId) {
  const input   = document.getElementById("refine-input");
  const chat    = document.getElementById("refine-chat");
  const message = input?.value.trim();
  if (!message || !chat) return;

  input.value = "";

  // Add user bubble
  chat.innerHTML += `<div class="refine-bubble refine-user">${message}</div>`;

  // Add bot bubble (will stream into it)
  const botId = `refine-bot-${Date.now()}`;
  chat.innerHTML += `<div class="refine-bubble refine-bot" id="${botId}">
    <div class="plan-spinner" style="width:14px;height:14px;border-width:2px"></div>
  </div>`;
  chat.scrollTop = chat.scrollHeight;

  const payload = window._currentPlanPayload || {};
  const requestPayload = {
    destination_id: destId,
    days:           payload.days           || parseInt(document.getElementById("days").value)   || 5,
    budget_per_day: payload.budget_per_day || parseInt(document.getElementById("budget").value) || 2000,
    group_type:     payload.group_type     || getGroupType(),
    vibes:          payload.vibes          || [...selectedVibes],
    existing_plan:  window._currentPlanText || "",
    user_message:   message,
  };

  try {
    const resp = await fetch(`${API_BASE}/api/refine`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(requestPayload),
    });

    if (!resp.ok) throw new Error(`Server error ${resp.status}`);

    const botEl  = document.getElementById(botId);
    botEl.innerHTML = "";
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", raw = "";

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
        botEl.innerHTML = typeof marked !== "undefined" ? marked.parse(raw) : raw;
        chat.scrollTop = chat.scrollHeight;
      }
    }
  } catch (err) {
    const botEl = document.getElementById(botId);
    if (botEl) botEl.innerHTML = `<span style="color:#dc2626">Error: ${err.message}</span>`;
  }
}

/* ===== P3: RENDER STRUCTURED PLAN ===== */
function renderStructuredPlan(plan, cost) {
  if (!plan) return "<p>No plan data received.</p>";

  const src = plan._source || "fallback";
  const srcLabel = src === "groq" ? "Groq LLaMA" : src === "gemini" ? "Gemini 1.5 Flash" : "Knowledge Base";
  const srcClass = src === "groq" ? "source-groq" : src === "gemini" ? "source-gemini" : "source-fallback";

  let html = `<div class="structured-plan">`;
  html += `<span class="source-badge ${srcClass}">${srcLabel}</span>`;

  // Summary
  if (plan.summary) {
    html += `<div class="plan-summary">${plan.summary}</div>`;
  }

  // Cost summary (from deterministic estimator)
  if (cost) {
    const pp = cost.per_person || {};
    html += `<div class="plan-section-title">Estimated Trip Cost (per person · ${cost.days} days)</div>`;
    html += `<div class="cost-summary-grid">
      <div class="cost-item"><div class="cost-item-label">Transport</div><div class="cost-item-val">₹${(pp.transport_return||0).toLocaleString("en-IN")}</div></div>
      <div class="cost-item"><div class="cost-item-label">Stay</div><div class="cost-item-val">₹${(pp.accommodation||0).toLocaleString("en-IN")}</div></div>
      <div class="cost-item"><div class="cost-item-label">Food</div><div class="cost-item-val">₹${(pp.food||0).toLocaleString("en-IN")}</div></div>
      <div class="cost-item"><div class="cost-item-label">Activities</div><div class="cost-item-val">₹${(pp.activities||0).toLocaleString("en-IN")}</div></div>
    </div>
    <div class="cost-total-row">
      <span class="cost-total-label">Total estimate</span>
      <span class="cost-total-val">₹${(pp.total||0).toLocaleString("en-IN")}</span>
    </div>`;
  }

  // Itinerary
  if (plan.itinerary && plan.itinerary.length) {
    html += `<div class="plan-section-title">Day-by-Day Itinerary</div><div class="day-cards">`;
    for (const day of plan.itinerary) {
      html += `
        <div class="day-card">
          <div class="day-card-header">
            <span class="day-num">Day ${day.day}</span>
            <span class="day-title">${day.title || ""}</span>
            ${day.highlight ? `<span class="day-highlight">★ ${day.highlight}</span>` : ""}
          </div>
          <div class="day-card-body">
            ${day.morning   ? `<div class="day-slot"><span class="slot-label">Morning</span><span>${day.morning}</span></div>` : ""}
            ${day.afternoon ? `<div class="day-slot"><span class="slot-label">Afternoon</span><span>${day.afternoon}</span></div>` : ""}
            ${day.evening   ? `<div class="day-slot"><span class="slot-label">Evening</span><span>${day.evening}</span></div>` : ""}
          </div>
        </div>`;
    }
    html += `</div>`;
  }

  // Food guide
  if (plan.food_guide && plan.food_guide.length) {
    html += `<div class="plan-section-title">Food Guide</div>
      <table class="food-table">
        <thead><tr><th>Dish</th><th>Where to Try</th><th>~Cost</th></tr></thead>
        <tbody>`;
    for (const f of plan.food_guide) {
      html += `<tr>
        <td><div class="food-dish">${f.dish}</div><div style="font-size:.75rem;color:var(--muted)">${f.description||""}</div></td>
        <td>${f.where||"—"}</td>
        <td class="food-cost">${f.approx_cost_inr ? "₹"+f.approx_cost_inr : "—"}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  // Transport options (LLM-generated + overlay deterministic)
  const llmTransport = plan.transport;
  if (llmTransport) {
    html += `<div class="plan-section-title">Getting There & Transport</div><div class="transport-cards">`;
    const opts = llmTransport.options || [];
    for (const o of opts) {
      html += `
        <div class="transport-card">
          <div class="transport-mode">${o.mode}</div>
          <div class="transport-detail">
            <div class="transport-route">${o.route}</div>
            <div class="transport-dur">${o.duration}</div>
          </div>
          <div class="transport-cost">${o.est_cost_inr ? "₹"+Number(o.est_cost_inr).toLocaleString("en-IN") : ""}</div>
        </div>`;
    }
    html += `</div>`;
    if (llmTransport.local) {
      html += `<div class="local-transport-note">🚶 Local: ${llmTransport.local}</div>`;
    }
  }

  // Accommodation
  if (plan.accommodation && plan.accommodation.length) {
    html += `<div class="plan-section-title">Accommodation Options</div><div class="acc-cards">`;
    for (const a of plan.accommodation) {
      html += `
        <div class="acc-card">
          <div class="acc-type">${a.type}</div>
          <div class="acc-area">${a.area||""}</div>
          <div class="acc-price">${a.price_range||""}</div>
          <div class="acc-for">${a.best_for||""}</div>
        </div>`;
    }
    html += `</div>`;
  }

  // Tips
  if (plan.tips && plan.tips.length) {
    html += `<div class="plan-section-title">Travel Tips</div><ul class="tips-list">`;
    for (const tip of plan.tips) {
      html += `<li>${tip}</li>`;
    }
    html += `</ul>`;
  }

  html += `</div>`;
  return html;
}

/* =====================================================================
   P4 — A: INTERACTIVE MAP
   ===================================================================== */

const VIBE_COLORS = {
  mountains: "#3b82f6", beach: "#06b6d4", heritage: "#8b5cf6",
  adventure: "#f97316", wildlife: "#16a34a", spiritual: "#ec4899",
  offbeat: "#64748b", desert: "#d97706", backwaters: "#0891b2",
  nature: "#22c55e", honeymoon: "#e879f9", trekking: "#84cc16",
  default: "#94a3b8",
};

function vibeColor(vibe) {
  return VIBE_COLORS[vibe] || VIBE_COLORS.default;
}

function makeCircleIcon(color, r = 8, border = "#fff") {
  return L.divIcon({
    className: "",
    html: `<svg width="${r*2+4}" height="${r*2+4}" viewBox="0 0 ${r*2+4} ${r*2+4}">
      <circle cx="${r+2}" cy="${r+2}" r="${r}" fill="${color}" stroke="${border}" stroke-width="2"/>
    </svg>`,
    iconSize: [r*2+4, r*2+4],
    iconAnchor: [r+2, r+2],
    popupAnchor: [0, -(r+4)],
  });
}

async function initMap() {
  _map = L.map("map", { zoomControl: true }).setView([22.5, 80], 4.5);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(_map);

  try {
    const resp = await fetch(`${API_BASE}/api/destinations/geo`);
    _allGeo = await resp.json();
  } catch { return; }

  _allGeo.forEach(dest => {
    const color  = vibeColor(dest.primary_vibe);
    const radius = 6 + (dest.popularity / 10) * 4;   // 6–10px based on popularity
    const marker = L.marker([dest.lat, dest.lon], { icon: makeCircleIcon(color, radius) })
      .addTo(_map)
      .bindPopup(mapPopupHtml(dest, null));

    marker.on("click", () => {
      marker.setPopupContent(mapPopupHtml(dest, null));
    });

    _allGeoMarkers[dest.id] = marker;
  });
}

function mapPopupHtml(geo, score) {
  const pct    = score != null ? Math.round(score * 100) : null;
  const color  = score == null ? "#94a3b8" : score > 0.7 ? "#16a34a" : score > 0.5 ? "#d97706" : "#ea580c";
  const scoreBar = pct != null
    ? `<div style="margin:.4rem 0 .3rem">
         <div style="height:5px;background:#e2e8f0;border-radius:4px;overflow:hidden">
           <div style="height:100%;width:${pct}%;background:${color};border-radius:4px"></div>
         </div>
         <span style="font-size:.7rem;color:${color};font-weight:700">${pct}% match</span>
       </div>`
    : "";

  const savedBtn = `<button onclick="toggleSaveById('${geo.id}')" style="
    background:none;border:1px solid #e2e8f0;border-radius:6px;padding:.2rem .5rem;
    cursor:pointer;font-size:.72rem;color:#64748b;margin-top:.3rem"
    id="map-save-${geo.id}">${isSaved(geo.id) ? "★ Saved" : "☆ Save"}</button>`;

  return `
    <div style="min-width:170px;font-family:Inter,sans-serif">
      <div style="font-weight:800;font-size:.95rem;color:#0f172a">${geo.name}</div>
      <div style="font-size:.75rem;color:#64748b;margin-bottom:.3rem">${geo.state}</div>
      ${scoreBar}
      <div style="display:flex;gap:.35rem;flex-wrap:wrap;margin:.3rem 0">
        ${(geo.vibes||[]).slice(0,3).map(v=>`<span style="font-size:.65rem;padding:.1rem .35rem;border-radius:4px;background:#eff6ff;color:#2563eb;font-weight:600">${v}</span>`).join("")}
      </div>
      <div style="display:flex;gap:.4rem;margin-top:.4rem">
        <button onclick="openModalById('${geo.id}')" style="
          background:#2563eb;color:#fff;border:none;border-radius:6px;
          padding:.3rem .7rem;cursor:pointer;font-size:.75rem;font-weight:700">
          View Details
        </button>
        ${savedBtn}
      </div>
    </div>`;
}

function updateMapScores(rankedDests) {
  // Reset all markers to default vibe color first
  _allGeo.forEach(geo => {
    const color  = vibeColor(geo.primary_vibe);
    const radius = 6 + (geo.popularity / 10) * 4;
    _allGeoMarkers[geo.id]?.setIcon(makeCircleIcon(color, radius));
  });

  const scoreMap = {};
  rankedDests.forEach((d, i) => { scoreMap[d.id] = { score: d.score, rank: i + 1 }; });

  const bounds = [];
  rankedDests.slice(0, 20).forEach((dest, i) => {
    const m = _allGeoMarkers[dest.id];
    if (!m) return;

    let color, r;
    if (i < 3)           { color = "#2563eb"; r = 14; }
    else if (dest.score > 0.7) { color = "#16a34a"; r = 11; }
    else if (dest.score > 0.5) { color = "#d97706"; r = 9; }
    else                       { color = "#ea580c"; r = 8; }

    m.setIcon(makeCircleIcon(color, r, i < 3 ? "#fff" : "#fff"));
    m.setPopupContent(mapPopupHtml(dest, dest.score));
    if (dest.lat) bounds.push([dest.lat, dest.lon]);
  });

  if (bounds.length > 1) {
    _map.fitBounds(bounds, { padding: [60, 60], maxZoom: 9 });
  } else if (bounds.length === 1) {
    _map.setView(bounds[0], 8);
  }
}

async function openModalById(destId) {
  try {
    const resp = await fetch(`${API_BASE}/api/destinations/${destId}`);
    const dest = await resp.json();
    // merge score if available
    const ranked = lastResults.find(d => d.id === destId);
    if (ranked) Object.assign(dest, { score: ranked.score, score_breakdown: ranked.score_breakdown });
    showModal(dest);
  } catch (e) {
    console.error("openModalById failed", e);
  }
}


/* =====================================================================
   P4 — B: SMART FILTERS
   ===================================================================== */

function bindFilterChips() {
  ["filter-region", "filter-budget", "filter-season"].forEach(groupId => {
    const group = document.getElementById(groupId);
    if (!group) return;
    const key = groupId.replace("filter-", "");
    group.querySelectorAll(".filter-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        group.querySelectorAll(".filter-chip").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        _activeFilters[key] = btn.dataset.val;
        applyFilters();
      });
    });
  });
}

function applyFilters() {
  let results = [...lastResults];

  if (_activeFilters.region) {
    results = results.filter(d => d.region === _activeFilters.region);
  }

  if (_activeFilters.budget) {
    results = results.filter(d => d.budget_range === _activeFilters.budget);
  }

  if (_activeFilters.season === "in-season") {
    const currentMonth = new Date().getMonth() + 1;
    results = results.filter(d => (d.best_months || []).includes(currentMonth));
  }

  _filteredResults = results;

  const statusEl = document.getElementById("filter-status");
  const active = Object.values(_activeFilters).filter(Boolean).length;
  if (statusEl) {
    statusEl.textContent = active
      ? `${results.length} destinations match your filters`
      : "";
  }

  renderResults(results, null);
}

function resetFilters() {
  _activeFilters = { region: "", budget: "", season: "" };
  document.querySelectorAll(".filter-chip").forEach(b => {
    b.classList.toggle("active", b.dataset.val === "");
  });
  applyFilters();
}


/* =====================================================================
   P4 — B: SAVED TRIPS
   ===================================================================== */

const SAVED_KEY = "travelmind_saved";

function getSaved() {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]"); }
  catch { return []; }
}

function isSaved(destId) {
  return getSaved().some(s => s.id === destId);
}

function toggleSave(dest) {
  let saved = getSaved();
  const nowSaved = !isSaved(dest.id);
  if (!nowSaved) {
    saved = saved.filter(s => s.id !== dest.id);
  } else {
    saved.push({
      id:          dest.id,
      name:        dest.name,
      state:       dest.state,
      region:      dest.region,
      score:       dest.score || 0,
      vibes:       dest.vibes || [],
      avg_cost_mid: dest.avg_cost_mid || 0,
      savedAt:     new Date().toISOString(),
    });
  }
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  renderSavedSection();

  // Update every button that references this dest id
  document.querySelectorAll(`[id="save-btn-${dest.id}"]`).forEach(btn => {
    const isCard = btn.classList.contains("card-save-btn");
    btn.textContent = nowSaved ? (isCard ? "★" : "★ Saved") : (isCard ? "☆" : "☆ Save");
  });
  const modalBtn = document.getElementById("btn-save-modal");
  if (modalBtn) modalBtn.textContent = nowSaved ? "★ Saved" : "☆ Save";
  const mapBtn = document.getElementById(`map-save-${dest.id}`);
  if (mapBtn) mapBtn.textContent = nowSaved ? "★ Saved" : "☆ Save";
}

function toggleSaveById(destId) {
  // For map popup clicks — find dest in lastResults or allGeo
  const dest = lastResults.find(d => d.id === destId)
    || _allGeo.find(d => d.id === destId)
    || { id: destId, name: destId };
  toggleSave(dest);
}

function clearAllSaved() {
  localStorage.removeItem(SAVED_KEY);
  renderSavedSection();
}

function renderSavedSection() {
  const saved   = getSaved();
  const section = document.getElementById("saved-section");
  const grid    = document.getElementById("saved-grid");
  if (!section || !grid) return;

  if (!saved.length) { section.style.display = "none"; return; }

  section.style.display = "block";
  grid.innerHTML = saved.map(s => {
    const pct = Math.round((s.score || 0) * 100);
    return `
      <div class="saved-card">
        <div class="saved-card-top">
          <div>
            <div class="saved-name">${s.name}</div>
            <div class="saved-state">${s.state} · ${s.region}</div>
          </div>
          <button class="saved-remove" onclick="removeSaved('${s.id}')" title="Remove">✕</button>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:.3rem;margin:.5rem 0">
          ${(s.vibes||[]).slice(0,4).map(v=>`<span class="vibe-tag">${v}</span>`).join("")}
        </div>
        <div class="saved-meta">
          ${pct ? `<span style="color:var(--primary);font-weight:700">${pct}% match</span>` : ""}
          <span>₹${(s.avg_cost_mid||0).toLocaleString("en-IN")}/day</span>
        </div>
        <button class="btn-view-saved" onclick="openModalById('${s.id}')">View Details</button>
      </div>`;
  }).join("");
}

function removeSaved(destId) {
  const saved = getSaved().filter(s => s.id !== destId);
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  renderSavedSection();
}


/* ===== HELPERS ===== */
function showLoader()  { document.getElementById("loader").style.display = "flex"; }
function hideLoader()  { document.getElementById("loader").style.display = "none"; }
function hideResults() {
  document.getElementById("results-section").style.display = "none";
  document.getElementById("top-picks-section").style.display = "none";
}
function showError(msg) {
  const el = document.getElementById("error-msg");
  el.style.display = "block";
  el.textContent = msg;
}
function hideError() { document.getElementById("error-msg").style.display = "none"; }
