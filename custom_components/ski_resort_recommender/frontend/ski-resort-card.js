// Ski Resort Recommender card: compact table of the best days; a click opens a
// modal with every resort-day, expandable details and the scoring formula.
// Loaded automatically by the integration (no build step, no extra install).

const RESULTS_COMMAND = "ski_resort_recommender/results";
const DEFAULT_ENTITY = "sensor.ski_resort_recommender";
// color mode: good days get this background (card option good_color)
const DEFAULT_GOOD_COLOR = "#c8f2cf"; // pastel green
// required by the SLF data licence: a visible reference with a link
const SLF_LINK = `<a href="https://www.slf.ch" target="_blank" rel="noopener">WSL Institute for Snow and Avalanche Research SLF</a>`;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const price = (chf) => {
  if (!chf) return "";
  return Number.isInteger(chf) ? `${chf}.-` : chf.toFixed(2);
};

// lower case without accents: "vallees" finds "Vallées"
const fold = (text) =>
  String(text ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// the modal's search: every word must appear in resort, point or day
const matches = (haystack, query) => fold(query).split(/\s+/).every((word) => haystack.includes(word));

// parking for one ski day: "free", "8.-", "13.60"; null = unknown
const parkingPrice = (chf) => (chf === null || chf === undefined ? null : chf === 0 ? "free" : price(chf));

const num = (value, digits = 0, unit = "") =>
  value === null || value === undefined ? "–" : `${Number(value).toFixed(digits)}${unit}`;

// travel lines of a block: [label, html]; train Dep./Arr., car (car mode)
function travelLines(r) {
  const t = r.train;
  const lines = [];
  if (t) {
    lines.push([
      "Dep.",
      `${esc(t.from ?? "")}${t.from ? ", " : ""}${esc(t.departure)}` +
        `${t.line ? ` · ${esc(t.line.replace(" ", ""))}` : ""}` +
        `${t.platform ? ` · Pl. ${esc(t.platform)}` : ""}`,
    ]);
    lines.push(["Arr.", `${esc(t.to ?? "")}${t.to ? ", " : ""}${esc(t.arrival)}`]);
  } else if (!r.car) {
    lines.push(["", "No train"], ["", ""]); // keeps the block height of the train layout
  }
  if (r.car) lines.push(["Car", esc(r.car.summary)]);
  return lines;
}

// one compact block: score/classification | resort · point | price + SnR
//                    date | Dep. | station, time · train · platform
//                         | Arr. | station, time
//                         | Car  | access point · 1:41 h · 139 km   (car mode)
function block(r) {
  const park = parkingPrice(r.car?.parking?.[0]?.price_chf);
  const lines = travelLines(r)
    .map(([label, text], i) => `<div class="line"><span class="date">${i === 0 ? esc(r.day) : ""}</span><span class="lbl">${label}</span><span class="txt">${text}</span></div>`)
    .join("");
  const snr = r.snow_n_rail ? `<span class="badge" title="Snow'n'Rail up to ${r.snow_n_rail.up_to_pct} %">SnR</span>` : "";
  return `
    <div class="block${r.is_good ? " good" : ""}">
      <div class="score">
        <div class="points">${esc(r.score)}</div>
        <div class="class">${esc(r.classification)} <ha-icon icon="${esc(r.weather_icon)}"></ha-icon></div>
      </div>
      <div class="main">
        <div class="title"><b>${esc(r.resort)}</b> · <span class="small">${esc(r.point)}</span></div>
        ${lines}
      </div>
      <div class="side"><div>${price(r.price_chf)}</div>${park ? `<div class="small" title="Parking, one ski day">P ${esc(park)}</div>` : ""}${snr}</div>
    </div>`;
}

const LABELS = {
  sun: "Sun",
  snow: "Fresh snow",
  depth: "Snow depth",
  travel: "Travel",
  price: "Price",
  wind: "Wind",
  temp: "Temperature",
  weather: "Weather",
  visibility: "Visibility",
  icy: "Icy",
};

function maxPoints(key, w) {
  return {
    sun: w.sun_points,
    snow: w.snow_points,
    depth: w.snow_depth_points,
    travel: w.travel_points,
    price: w.price_points,
    wind: w.wind_penalty,
    temp: w.temp_slush_penalty,
    weather: -w.weather_no_go_points,
    visibility: w.visibility_penalty,
    icy: w.icy_penalty,
  }[key] || 1;
}

function breakdown(reasons, w) {
  return Object.entries(reasons)
    .map(([key, value]) => {
      const width = Math.min(Math.abs(value) / maxPoints(key, w), 1) * 100;
      const cls = value < 0 ? "neg" : "pos";
      return `<div class="bar"><span class="bl">${esc(LABELS[key] ?? key)}</span>
        <span class="track"><span class="fill ${cls}" style="width:${width.toFixed(0)}%"></span></span>
        <span class="bv ${cls}">${value > 0 ? "+" : ""}${Number(value).toFixed(1)}</span></div>`;
    })
    .join("");
}

function pointsTable(points) {
  const rows = points
    .map((p) => {
      const f = p.forecast;
      return `<tr><td>${esc(p.name)} <span class="small">${esc(p.elevation_m)} m · ×${esc(p.weight)}</span></td>
        <td>${esc(p.score)}</td><td>${num(f.sunshine_hours, 1)}/${num(f.daylight_hours, 1, " h")}</td>
        <td>${num(f.fresh_snow_cm, 0, " cm")}</td><td>${num(f.snow_depth_cm, 0, " cm")}</td>
        <td>${num(f.gust_max_kmh, 0, " km/h")}</td><td>${num(f.temp_ski_c, 1, " °C")}</td>
        <td>${f.visibility_m === null ? "–" : `${(f.visibility_m / 1000).toFixed(1)} km`}</td>
        <td>${num(f.recent_rain_mm, 1, " mm")}</td></tr>`;
    })
    .join("");
  return `<table class="pts"><tr><th>Point</th><th>Score</th><th>Sun</th><th>Fresh</th><th>Depth</th>
    <th>Gusts</th><th>Temp</th><th>View</th><th>Rain</th></tr>${rows}</table>`;
}

// SLF stations behind the snow depth (measured base); none: model depth
function snowStations(stations) {
  if (!stations?.length) return `<div class="small">Snow depth: model only (no SLF station nearby).</div>`;
  const list = stations
    .map((s) => `${esc(s.name)} <span class="small">${esc(s.code)}, ${esc(s.elevation_m)} m</span> ${num(s.depth_cm, 0, " cm")}`)
    .join(" · ");
  return `<div class="small">Snow depth measured at 09:00 (median = base of every point): ${list}. Source: ${SLF_LINK}</div>`;
}

// car parks of the access point: spaces, price for a ski day, walk to the gondola
function carParks(parks) {
  if (!parks?.length) return "";
  const items = parks
    .map((c) => {
      const cost = parkingPrice(c.price_chf);
      const facts = [
        c.spaces ? `${esc(c.spaces)} spaces` : "spaces unknown",
        cost === null ? "price unknown" : cost === "free" ? "free" : `CHF ${esc(cost)} per ski day`,
        `${esc(c.walk_min)} min walk`,
      ];
      return `<li>${esc(c.name)}: ${facts.join(" · ")}</li>`;
    })
    .join("");
  return `<ul class="legs">${items}</ul>`;
}

// electric car: public chargers at the access point (BFE); null = not checked / no data
function chargers(c) {
  if (!c) return "";
  if (!c.count) return `<div class="small">⚡ No public charger listed at this access point.</div>`;
  const kw = c.kw_max ? (c.kw_min === c.kw_max ? `${esc(c.kw_max)} kW` : `${esc(c.kw_min)}–${esc(c.kw_max)} kW`) : "power unknown";
  return `<div class="small">⚡ ${esc(c.count)} public charging point${c.count === 1 ? "" : "s"} within 300 m, ${kw}.</div>`;
}

function legs(train) {
  if (!train) return `<div class="small">No morning connection in the arrival window.</div>`;
  const items = (train.legs ?? [])
    .map(
      (l) => `<li>${esc(l.departure)} ${esc(l.from)}${l.platform ? ` (Pl. ${esc(l.platform)})` : ""} →
        ${esc(l.arrival)} ${esc(l.to)} · <b>${esc(l.line)}</b>${l.train_number ? ` ${esc(l.train_number)}` : ""}</li>`,
    )
    .join("");
  return `<div class="small">${esc(train.duration_min)} min, ${esc(train.transfers)} change(s)</div><ol class="legs">${items}</ol>`;
}

function details(r, w) {
  return `
    <details data-search="${esc(fold(`${r.resort} ${r.point} ${r.day}`))}">
      <summary>${block(r)}</summary>
      <div class="detail">
        <h4>Score breakdown</h4>${breakdown(r.reasons, w)}
        <h4>Weather points (weighted average)</h4>${pointsTable(r.points ?? [])}${snowStations(r.snow_stations)}
        ${r.car ? `<h4>Car</h4><div class="small">To ${esc(r.car.access)} (the closest access point): ${esc(r.car.summary.split(" · ").slice(1).join(" · "))}, without traffic</div>${carParks(r.car.parking)}${chargers(r.car.chargers)}` : ""}
        ${r.train || !r.car ? `<h4>Train</h4>${legs(r.train)}` : ""}
        ${r.snow_n_rail ? `<div class="small">Snow'n'Rail offer up to ${esc(r.snow_n_rail.up_to_pct)} % – <a href="${esc(r.snow_n_rail.url)}" target="_blank" rel="noopener">SBB RailAway</a> (availability not checked)</div>` : ""}
      </div>
    </details>`;
}

function legend(s) {
  const w = s.weights;
  return `
    <div class="legend">
      <h3>Legend</h3>
      <ul>
        <li><b>Score</b> 0–100: weather part (max ${w.sun_points + w.snow_points + w.snow_depth_points}) + travel + price, minus penalties.</li>
        <li><span class="swatch"></span><b>Good day</b>: score ≥ ${esc(s.min_good_score)} and no rain/thunder at the best point. <b>Not good</b>: below. <b>Outlook</b>: days ${s.ranking_days + 1}–${s.outlook_days} (less certain; the best one is shown in the card when <i>Show the outlook</i> is on).</li>
        <li><b>Icon</b>: most frequent weather over all points and ski hours (09–16 h).</li>
        <li><b>Resort · point</b>: the best weather point (lift station) of the resort that day.</li>
        <li><b>Dep. / Arr.</b>: morning train from your home station, arriving at the gondola in the arrival window; first train and platform.</li>
        <li><b>Car</b>: drive from your home location to the closest access point (valley station / car park), without traffic. <b>P</b>: parking for one ski day (about 8 h) at its main car park, from parking.ch and the resort websites (2026/27, may change). <b>⚡</b> (electric car): public charging points within 300 m; not every charger is listed, no data in Austria.</li>
        <li><b>Price</b>: adult high-season day pass in CHF. <span class="badge">SnR</span>: the resort has an SBB Snow'n'Rail offer.</li>
      </ul>
      <h3>Scoring</h3>
      <div class="formula">
        <div><b>Score</b> = Σ<sub>points</sub> weight × (Sun + Fresh snow + Snow depth − Wind − Temp − Weather − Visibility − Icy) / Σ weight + Travel + Price</div>
        <div><b>Sun</b> = min(sunshine ÷ daylight ÷ ${w.sun_full_share}, 1) × ${w.sun_points}</div>
        <div><b>Fresh snow</b> = min(snow in the 48 h before opening ÷ ${w.snow_full_cm} cm, 1) × ${w.snow_points}</div>
        <div><b>Snow depth</b> = log(1 + d ÷ ${w.snow_depth_curve_cm}) ÷ log(1 + ${w.snow_depth_full_cm} ÷ ${w.snow_depth_curve_cm}) × ${w.snow_depth_points}, d = depth up to ${w.snow_depth_full_cm} cm: measured today at the resort's SLF stations (median) + the model's change until that day; model only without a station</div>
        <div><b>Travel</b> = (longest trip − trip) ÷ (longest − shortest) × ${w.travel_points}; trip = train or drive time (with both: the faster)</div>
        <div><b>Price</b> = (dearest − price) ÷ (dearest − cheapest) × ${w.price_points}</div>
        <div><b>Wind</b> = ramp(max gust, ${w.gust_limit_kmh}, ${w.gust_full_kmh} km/h) × ${w.wind_penalty}</div>
        <div><b>Temp</b> = ${w.temp_cold_penalty} below ${w.temp_cold_c} °C, or ramp(mean temp, ${w.temp_slush_start_c}, ${w.temp_slush_full_c} °C) × ${w.temp_slush_penalty} (slush)</div>
        <div><b>Weather</b> = average over the ski hours: fog ${-w.weather_bad_points}, rain/thunder ${-w.weather_no_go_points} (no-go from ${w.no_go_min_hours} h)</div>
        <div><b>Visibility</b> = ramp(below ${w.visibility_good_m / 1000} km down to ${w.visibility_bad_m / 1000} km) × ${w.visibility_penalty}</div>
        <div><b>Icy</b> = ramp(rain in the 48 h before opening, ${w.rain_limit_mm}, ${w.rain_full_mm} mm) × (1 − ramp(snow on top, 0, ${w.ice_cover_full_cm} cm)) × ${w.icy_penalty}</div>
        <div class="small">ramp(x, a, b) = 0 below a, 1 above b, linear in between.</div>
      </div>
      <h3>Sources</h3>
      <div class="small">Weather: <a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo</a> (MeteoSwiss, DWD) ·
        Snow depth: ${SLF_LINK} (CC BY 4.0) · Trains: <a href="https://transport.opendata.ch" target="_blank" rel="noopener">transport.opendata.ch</a> ·
        Drive times: <a href="https://project-osrm.org" target="_blank" rel="noopener">OSRM</a>, map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors ·
        Charging points: <a href="https://www.ich-tanke-strom.ch" target="_blank" rel="noopener">Swiss Federal Office of Energy SFOE</a></div>
    </div>`;
}

const STYLE = `
  :host { --ski-gap: 3px; --ski-score-width: 104px; --ski-date-width: 64px; --ski-label-width: 32px; --ski-side-width: 42px; }
  ha-card { padding: calc(2 * var(--ski-gap) + 1px) 4px; cursor: pointer; height: 100%; box-sizing: border-box;
            overflow-x: hidden; overflow-y: auto; scrollbar-width: thin; }  /* never cut off the outlook: scroll */
  .block { display: grid; grid-template-columns: var(--ski-score-width) 1fr var(--ski-side-width); align-items: center; }
  .block + .block, .sep { border-top: 1px solid var(--divider-color); margin-top: var(--ski-gap); padding-top: var(--ski-gap); }
  .score { text-align: center; }
  /* color mode: good days on a coloured background, dark text (readable in dark themes too) */
  :host([color-mode]) .block { padding: var(--ski-gap) 2px; border-radius: 6px; }
  :host([color-mode]) .block.good { background: var(--ski-good-color); color: #1f2d22;
    --primary-text-color: #1f2d22; --secondary-text-color: #45574a; }
  .swatch { display: none; width: 10px; height: 10px; margin-right: 4px; border-radius: 2px; background: var(--ski-good-color); vertical-align: -1px; }
  :host([color-mode]) .swatch { display: inline-block; }
  .points { font-size: 24px; font-weight: 700; line-height: 1.1; }
  .class, .small { font-size: 12px; color: var(--secondary-text-color); }
  .class ha-icon { --mdc-icon-size: 16px; }
  .main { min-width: 0; }
  .title { padding-bottom: 3px; }
  .title, .txt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .line { display: grid; grid-template-columns: var(--ski-date-width) var(--ski-label-width) 1fr; font-size: 12px; line-height: 1.3; }
  .line + .line { padding-top: 2px; }
  .side { text-align: right; font-size: 13px; }
  .badge { display: inline-block; font-size: 10px; font-weight: 600; line-height: 1; padding: 2px 7px; border-radius: 10px;
           background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .empty { padding: 8px; color: var(--secondary-text-color); }
  .overlay { position: fixed; inset: 0; z-index: 2000; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; cursor: default; }
  .dialog { background: var(--card-background-color, var(--ha-card-background)); color: var(--primary-text-color);
            border-radius: var(--ha-card-border-radius, 12px); width: min(760px, 96vw); max-height: 90vh; display: flex; flex-direction: column; }
  .head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--divider-color); }
  .head h2 { margin: 0; font-size: 18px; }
  .close { background: none; border: 0; color: inherit; font-size: 22px; cursor: pointer; }
  .body { overflow-y: auto; padding: 8px 12px 16px; }
  .filter { padding: 8px 12px 0; }
  .filter input { width: 100%; box-sizing: border-box; padding: 6px 10px; font: inherit; font-size: 14px; color: inherit;
                  background: var(--secondary-background-color); border: 1px solid var(--divider-color); border-radius: 6px; }
  details[hidden] { display: none; }
  details:not([hidden]) ~ details:not([hidden]) { border-top: 1px solid var(--divider-color); }  /* line between shown results */
  details { padding: var(--ski-gap) 0; }
  summary { list-style: none; cursor: pointer; }
  summary::-webkit-details-marker { display: none; }
  details[open] summary { background: var(--secondary-background-color); border-radius: 6px; }
  .detail { padding: 4px 8px 8px; font-size: 13px; }
  .detail h4 { margin: 10px 0 4px; font-size: 13px; }
  .bar { display: grid; grid-template-columns: 90px 1fr 48px; align-items: center; gap: 6px; font-size: 12px; }
  .track { height: 6px; background: var(--divider-color); border-radius: 3px; overflow: hidden; }
  .fill { display: block; height: 100%; }
  .fill.pos { background: var(--success-color, #4caf50); } .fill.neg { background: var(--error-color, #db4437); }
  .bv { text-align: right; } .bv.neg { color: var(--error-color, #db4437); }
  .pts { width: 100%; border-collapse: collapse; font-size: 12px; }
  .pts th, .pts td { text-align: left; padding: 2px 4px; border-bottom: 1px solid var(--divider-color); white-space: nowrap; }
  .legs { margin: 4px 0; padding-left: 18px; font-size: 12px; }
  .legend { border-top: 2px solid var(--divider-color); margin-top: 8px; padding-top: 8px; font-size: 13px; }
  .legend h3 { font-size: 14px; margin: 8px 0 4px; }
  .legend ul { margin: 0; padding-left: 18px; }
  .formula div { padding: 2px 0; }
  .error { color: var(--error-color, #db4437); padding: 8px; }
`;

const DEFAULT_RESULTS = 3; // size before the first result (default number of results)

// the entries the compact table shows: recommendations + outlook (if switched on)
function results(state) {
  const a = state?.attributes ?? {};
  return [...(a.recommendations ?? []), ...(a.outlook ? [a.outlook] : [])];
}

class SkiResortCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: DEFAULT_ENTITY, color_mode: true, good_color: DEFAULT_GOOD_COLOR, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    // color mode: CSS on :host([color-mode]); setProperty keeps the colour a plain value
    this.toggleAttribute("color-mode", this._config.color_mode !== false);
    this.style.setProperty("--ski-good-color", this._config.good_color);
  }

  set hass(hass) {
    const state = hass.states[this._config.entity];
    const changed = !this._hass || this._hass.states[this._config.entity] !== state;
    this._hass = hass;
    if (changed) this._renderCard(state);
  }

  // a block is about 40 px + 19 px per travel line (train 2, car 1); a sections
  // grid row is 56 px + 8 px gap. Read when the dashboard builds the card: a
  // changed number of results applies after a page reload, until then it scrolls.
  _rows() {
    const shown = results(this._hass?.states[this._config?.entity]);
    const px = shown.length
      ? shown.reduce((sum, r) => sum + 40 + 19 * travelLines(r).length, 0)
      : DEFAULT_RESULTS * 78;
    return Math.ceil((px + 8) / 64);
  }

  getCardSize() {
    return this._rows();
  }

  getGridOptions() {
    return { columns: 12, rows: this._rows(), min_rows: 2 };
  }

  static getStubConfig() {
    return { entity: DEFAULT_ENTITY };
  }

  _renderCard(state) {
    const a = state?.attributes ?? {};
    const shown = results(state);
    const body = shown.length
      ? shown.map(block).join("")
      : `<div class="empty">${esc(state ? state.state : `${this._config.entity} not found`)}${a.last_error ? `: ${esc(a.last_error)}` : ""}</div>`;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card><div id="modal"></div>`;
    this.shadowRoot.querySelector("ha-card").addEventListener("click", () => this._openModal());
  }

  _openModal() {
    openResults(this.shadowRoot, async () => {
      const data = await this._hass.callWS({ type: RESULTS_COMMAND });
      return {
        title: `Ski days · ${data.headline}`,
        results: data.results,
        scoring: data.scoring,
        empty: `${data.headline}${data.last_error ? `: ${data.last_error}` : ""}`,
      };
    });
  }
}

// the window with results (expandable details), a search box and the legend;
// load() returns {title, results, scoring, empty} (all results or one resort's)
async function openResults(root, load) {
  const modal = root.getElementById("modal");
  modal.innerHTML = `<div class="overlay"><div class="dialog"><div class="head"><h2>Ski days</h2>
    <button class="close" title="Close">×</button></div>
    <div class="filter"><input type="search" placeholder="Search resort, point or day" list="ski-resorts" aria-label="Search"><datalist id="ski-resorts"></datalist></div>
    <div class="body"><div class="empty">Loading…</div></div></div></div>`;
  const close = () => {
    modal.innerHTML = "";
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => e.key === "Escape" && close();
  document.addEventListener("keydown", onKey);
  modal.querySelector(".close").addEventListener("click", close);
  modal.querySelector(".overlay").addEventListener("click", (e) => e.target === e.currentTarget && close());
  const body = modal.querySelector(".body");
  try {
    const data = await load();
    modal.querySelector("h2").textContent = data.title;
    const w = data.scoring.weights;
    const list = data.results.length
      ? data.results.map((r) => details(r, w)).join("")
      : `<div class="empty">${esc(data.empty)}</div>`;
    body.innerHTML = list + `<div class="empty nomatch" hidden>No resort matches.</div>` + legend(data.scoring);
    const names = [...new Set(data.results.map((r) => r.resort))].sort();
    modal.querySelector("datalist").innerHTML = names.map((n) => `<option value="${esc(n)}"></option>`).join("");
    modal.querySelector(".filter input").addEventListener("input", (e) => filterResults(body, e.target.value));
  } catch (err) {
    body.innerHTML = `<div class="error">Could not load the results: ${esc(err.message ?? err)}</div>`;
  }
}

// hide the results that do not match; the legend stays
function filterResults(body, query) {
  let shown = 0;
  for (const item of body.querySelectorAll("details")) {
    item.hidden = !matches(item.dataset.search, query);
    if (!item.hidden) shown += 1;
  }
  body.querySelector(".nomatch").hidden = shown > 0;
}

customElements.define("ski-resort-card", SkiResortCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "ski-resort-card",
  name: "Ski Resort Recommender",
  description: "Best ski days; click for all resorts, details and the scoring formula.",
});

// ---- map card: custom:ski-resort-map-card ---------------------------------------
// Home, one pin per resort (its best day: score + date; click = its days) and the
// car road / train stops of the recommended resorts. Leaflet comes with the
// integration; tiles from CARTO (like the Home Assistant map card).

const LEAFLET_URL = "/ski_resort_recommender/leaflet";
const TILES = "https://basemaps.cartocdn.com/{style}/{z}/{x}/{y}{r}.png";
const TILES_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors ' +
  '&copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';
const CAR_COLOR = "#1e88e5";
const TRAIN_COLOR = "#e53935";

let leafletLoading = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  leafletLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `${LEAFLET_URL}/leaflet.js`;
    script.onload = () => resolve(window.L);
    script.onerror = () => {
      leafletLoading = null;
      reject(new Error("the map library could not be loaded"));
    };
    document.head.appendChild(script);
  });
  return leafletLoading;
}

// results (best first) grouped by resort key; the first of each is its best day
function byResort(results) {
  const groups = new Map();
  for (const r of results) {
    if (!groups.has(r.key)) groups.set(r.key, []);
    groups.get(r.key).push(r);
  }
  return groups;
}

// the train as one line through every stop of every leg
function trainLine(r) {
  return (r.train?.legs ?? []).flatMap((leg) => leg.stops ?? []);
}

function pinHtml(r, top) {
  const cls = `pin${r.is_good ? " good" : ""}${top ? " top" : ""}`;
  return `<div class="${cls}"><b>${esc(r.score)}</b><span>${esc(r.day)}</span></div>`;
}

const MAP_STYLE = `
  ha-card.mapcard { padding: 0; cursor: default; overflow: hidden; height: 100%; }
  .map { width: 100%; height: 100%; min-height: 200px; }
  .maperr { position: absolute; top: 8px; left: 50px; right: 8px; z-index: 1000; }
  .pin { transform: translate(-50%, -100%); width: max-content; text-align: center; font-size: 11px; line-height: 1.15;
         padding: 2px 6px; border-radius: 8px; cursor: pointer; white-space: nowrap;
         background: var(--card-background-color, #fff); color: var(--primary-text-color, #222);
         border: 2px solid var(--secondary-text-color, #777); box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4); }
  .pin b { display: block; font-size: 14px; }
  .pin.top { border-color: var(--primary-color, #03a9f4); border-width: 3px; }
  :host([color-mode]) .pin.good { background: var(--ski-good-color); color: #1f2d22; }
  .home { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
          transform: translate(-50%, -50%); background: var(--primary-color, #03a9f4); color: #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4); }
  .home ha-icon { --mdc-icon-size: 18px; }
  .maplegend { background: var(--card-background-color, #fff); color: var(--primary-text-color, #222); padding: 4px 8px;
               border-radius: 6px; font-size: 11px; line-height: 1.5; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3); }
  .maplegend i { display: inline-block; width: 18px; height: 0; vertical-align: middle; margin-right: 4px; border-top: 3px solid; }
  .leaflet-container { font: inherit; background: var(--secondary-background-color, #ddd); }
`;

class SkiResortMapCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: DEFAULT_ENTITY, color_mode: true, good_color: DEFAULT_GOOD_COLOR, routes: true, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.toggleAttribute("color-mode", this._config.color_mode !== false);
    this.style.setProperty("--ski-good-color", this._config.good_color);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    // new results: the sensor changed (hourly) or the theme switched
    const stamp = `${hass.states[this._config.entity]?.last_updated}|${hass.themes?.darkMode}`;
    if (stamp !== this._stamp) {
      this._stamp = stamp;
      this._load();
    }
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_rows: 4 };
  }

  static getStubConfig() {
    return { entity: DEFAULT_ENTITY };
  }

  _build() {
    this._built = true;
    this.shadowRoot.innerHTML = `<link rel="stylesheet" href="${LEAFLET_URL}/leaflet.css">
      <style>${STYLE}${MAP_STYLE}</style>
      <ha-card class="mapcard"><div class="map"></div><div class="maperr"></div></ha-card><div id="modal"></div>`;
  }

  async _load() {
    const err = this.shadowRoot.querySelector(".maperr");
    try {
      const [L, data] = await Promise.all([loadLeaflet(), this._hass.callWS({ type: RESULTS_COMMAND })]);
      err.innerHTML = data.results.length ? "" : `<div class="empty maplegend">${esc(data.headline)}${data.last_error ? `: ${esc(data.last_error)}` : ""}</div>`;
      this._draw(L, data);
    } catch (e) {
      err.innerHTML = `<div class="error maplegend">Map: ${esc(e.message ?? e)}</div>`;
    }
  }

  _draw(L, data) {
    const dark = Boolean(this._hass.themes?.darkMode);
    if (!this._map) {
      const el = this.shadowRoot.querySelector(".map");
      this._map = L.map(el, { zoomSnap: 0.5 });
      new ResizeObserver(() => this._map.invalidateSize()).observe(el);
      const legend = L.control({ position: "bottomleft" });
      legend.onAdd = () => {
        const div = L.DomUtil.create("div", "maplegend");
        div.innerHTML = `<div><i style="border-color:${CAR_COLOR}"></i>Car</div><div><i style="border-color:${TRAIN_COLOR};border-top-style:dashed"></i>Train</div>`;
        return div;
      };
      legend.addTo(this._map);
    }
    if (this._dark !== dark) {
      this._tiles?.remove();
      this._tiles = L.tileLayer(TILES.replace("{style}", dark ? "dark_all" : "light_all"), {
        attribution: TILES_ATTRIBUTION,
        maxZoom: 18,
      }).addTo(this._map);
      this._dark = dark;
    }
    this._layer?.remove();
    const layer = L.layerGroup().addTo(this._map);
    this._layer = layer;

    const home = [this._hass.config.latitude, this._hass.config.longitude];
    const groups = byResort(data.results);
    const top = new Set(data.recommended ?? []);
    const bounds = [home];

    if (this._config.routes !== false) {
      for (const key of top) {
        const best = groups.get(key)?.[0];
        if (!best) continue;
        const road = best.car?.route ?? [];
        if (road.length > 1) {
          L.polyline(road, { color: CAR_COLOR, weight: 4, opacity: 0.8 })
            .bindTooltip(`${esc(best.resort)}: ${esc(best.car.summary)}`)
            .addTo(layer);
        }
        const rail = trainLine(best);
        if (rail.length > 1) {
          const t = best.train;
          L.polyline(rail, { color: TRAIN_COLOR, weight: 3, opacity: 0.85, dashArray: "6 6" })
            .bindTooltip(`${esc(best.resort)}: ${esc(t.departure)} → ${esc(t.arrival)}, ${esc(t.duration_min)} min`)
            .addTo(layer);
        }
      }
    }

    L.marker(home, {
      icon: L.divIcon({ className: "", html: `<div class="home"><ha-icon icon="mdi:home"></ha-icon></div>`, iconSize: null }),
      interactive: false,
      keyboard: false,
    }).addTo(layer);

    for (const [key, list] of groups) {
      const best = list[0];
      if (!best.location) continue;
      bounds.push(best.location);
      L.marker(best.location, {
        icon: L.divIcon({ className: "", html: pinHtml(best, top.has(key)), iconSize: null }),
        title: best.resort,
        zIndexOffset: top.has(key) ? 1000 : 0,
      })
        .on("click", () =>
          openResults(this.shadowRoot, async () => ({
            title: `${best.resort} · ${list.length} day${list.length === 1 ? "" : "s"}`,
            results: list,
            scoring: data.scoring,
            empty: "",
          })),
        )
        .addTo(layer);
    }

    if (!this._fitted && bounds.length > 1) {
      this._map.fitBounds(bounds, { padding: [40, 40] });
      this._fitted = true; // keep the user's zoom on later updates
    }
  }
}

customElements.define("ski-resort-map-card", SkiResortMapCard);
window.customCards.push({
  type: "ski-resort-map-card",
  name: "Ski Resort Recommender map",
  description: "Map with home, every resort's best day and the routes of the recommendations; click a pin for details.",
});
