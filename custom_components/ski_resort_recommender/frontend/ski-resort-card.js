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

const num = (value, digits = 0, unit = "") =>
  value === null || value === undefined ? "–" : `${Number(value).toFixed(digits)}${unit}`;

// one compact block: score/classification | resort · point | price + SnR
//                    date | Dep. | station, time · train · platform
//                         | Arr. | station, time
function block(r) {
  const t = r.train;
  const dep = t
    ? `${esc(t.from ?? "")}${t.from ? ", " : ""}${esc(t.departure)}` +
      `${t.line ? ` · ${esc(t.line.replace(" ", ""))}` : ""}` +
      `${t.platform ? ` · Pl. ${esc(t.platform)}` : ""}`
    : "No train";
  const arr = t ? `${esc(t.to ?? "")}${t.to ? ", " : ""}${esc(t.arrival)}` : "";
  const snr = r.snow_n_rail ? `<span class="badge" title="Snow'n'Rail up to ${r.snow_n_rail.up_to_pct} %">SnR</span>` : "";
  return `
    <div class="block${r.is_good ? " good" : ""}">
      <div class="score">
        <div class="points">${esc(r.score)}</div>
        <div class="class">${esc(r.classification)} <ha-icon icon="${esc(r.weather_icon)}"></ha-icon></div>
      </div>
      <div class="main">
        <div class="title"><b>${esc(r.resort)}</b> · <span class="small">${esc(r.point)}</span></div>
        <div class="line"><span class="date">${esc(r.day)}</span><span class="lbl">${t ? "Dep." : ""}</span><span class="txt">${dep}</span></div>
        <div class="line"><span class="date"></span><span class="lbl">${t ? "Arr." : ""}</span><span class="txt">${arr}</span></div>
      </div>
      <div class="side"><div>${price(r.price_chf)}</div>${snr}</div>
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
        <h4>Train</h4>${legs(r.train)}
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
        <li><b>Price</b>: adult high-season day pass in CHF. <span class="badge">SnR</span>: the resort has an SBB Snow'n'Rail offer.</li>
      </ul>
      <h3>Scoring</h3>
      <div class="formula">
        <div><b>Score</b> = Σ<sub>points</sub> weight × (Sun + Fresh snow + Snow depth − Wind − Temp − Weather − Visibility − Icy) / Σ weight + Travel + Price</div>
        <div><b>Sun</b> = min(sunshine ÷ daylight ÷ ${w.sun_full_share}, 1) × ${w.sun_points}</div>
        <div><b>Fresh snow</b> = min(snow in the 48 h before opening ÷ ${w.snow_full_cm} cm, 1) × ${w.snow_points}</div>
        <div><b>Snow depth</b> = log(1 + d ÷ ${w.snow_depth_curve_cm}) ÷ log(1 + ${w.snow_depth_full_cm} ÷ ${w.snow_depth_curve_cm}) × ${w.snow_depth_points}, d = depth up to ${w.snow_depth_full_cm} cm: measured today at the resort's SLF stations (median) + the model's change until that day; model only without a station</div>
        <div><b>Travel</b> = (longest trip − trip) ÷ (longest − shortest) × ${w.travel_points}</div>
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
        Snow depth: ${SLF_LINK} (CC BY 4.0) · Trains: <a href="https://transport.opendata.ch" target="_blank" rel="noopener">transport.opendata.ch</a></div>
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
  .overlay { position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; cursor: default; }
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

  // one result block is about 78 px; a sections grid row is 56 px + 8 px gap.
  // Read when the dashboard builds the card: a changed number of results
  // (e.g. the outlook option) applies after a page reload, until then it scrolls.
  _rows() {
    const shown = results(this._hass?.states[this._config?.entity]).length || DEFAULT_RESULTS;
    return Math.ceil((shown * 78 + 8) / 64);
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

  async _openModal() {
    const modal = this.shadowRoot.getElementById("modal");
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
      const data = await this._hass.callWS({ type: RESULTS_COMMAND });
      modal.querySelector("h2").textContent = `Ski days · ${data.headline}`;
      const w = data.scoring.weights;
      const list = data.results.length
        ? data.results.map((r) => details(r, w)).join("")
        : `<div class="empty">${esc(data.headline)}${data.last_error ? `: ${esc(data.last_error)}` : ""}</div>`;
      body.innerHTML = list + `<div class="empty nomatch" hidden>No resort matches.</div>` + legend(data.scoring);
      const names = [...new Set(data.results.map((r) => r.resort))].sort();
      modal.querySelector("datalist").innerHTML = names.map((n) => `<option value="${esc(n)}"></option>`).join("");
      modal.querySelector(".filter input").addEventListener("input", (e) => this._filter(body, e.target.value));
    } catch (err) {
      body.innerHTML = `<div class="error">Could not load the results: ${esc(err.message ?? err)}</div>`;
    }
  }

  // hide the results that do not match; the legend stays
  _filter(body, query) {
    let shown = 0;
    for (const item of body.querySelectorAll("details")) {
      item.hidden = !matches(item.dataset.search, query);
      if (!item.hidden) shown += 1;
    }
    body.querySelector(".nomatch").hidden = shown > 0;
  }
}

customElements.define("ski-resort-card", SkiResortCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "ski-resort-card",
  name: "Ski Resort Recommender",
  description: "Best ski days; click for all resorts, details and the scoring formula.",
});
