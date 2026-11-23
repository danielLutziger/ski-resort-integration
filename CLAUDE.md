# ski_resort_recommender — Home Assistant custom integration

## Goal

A Home Assistant custom integration that tells me **when and where to ski**, starting from my home
(Wetzikon ZH, Switzerland). It aggregates weather forecasts (and later ticket prices and train
connections) for about 10 Swiss/Austrian ski resorts and returns **at most 3 recommendations**, e.g.:

    Saturday, Flims Laax, sunny symbol, 89.-
    <train information>

Requirements agreed so far:

- Default: only **weekends** (Sat/Sun), configurable (weekdays are an option, later via config flow).
- Only **future days**: not today, not the past.
- The same resort may appear several times (different days). In HA, clicking the entity shows the list.
- If nothing is good, the headline says **"No good day"** but the list is still shown.
- If there is no forecast data at all for the allowed days: headline **"No forecast yet"**.
- Final shape in HA: one sensor (state = headline, attributes = list of recommendations) + a Markdown card.

## Setup

- Repo: `ski-resort-integration`, started from ludeeus/`integration_blueprint`, VS Code dev container
  (named volume), Python 3.14, `scripts/develop` starts a dev HA instance.
- Lint: `.ruff.toml` with `select = ["ALL"]` (HA-core style). Tests: `pytest` with `pytest.ini`
  (`pythonpath = .`, `testpaths = tests`). Run scripts from the repo root with `python -m scripts.<name>`.

## Architecture (keep this direction of imports!)

```
custom_components/ski_resort_recommender/
  __init__.py manifest.json config_flow.py const.py coordinator.py sensor.py   # HA glue only (mostly TODO)
  resorts/<key>.yaml            # resorts as DATA: one file per resort, file name = resort key
  lib/                          # NO homeassistant imports, testable alone
    models.py                   # Resort, WeatherPoint, DayForecast (frozen dataclasses), Forecasts alias; imports nothing from lib
    errors.py                   # SkiApiError (base, Exception) -> SkiApiConnectionError, SkiApiParseError
    open_meteo.py               # OpenMeteoProvider (aiohttp); pure _combine/_parse_location/_ski_hours/...
    sbb.py                      # SbbProvider (aiohttp, transport.opendata.ch); pure _parse/_pick
    pipeline.py                 # build_recommendations(): forecasts + SBB (TravelCache) + ranking
    view.py                     # headline(), entry(), render_table(): what the sensor shows
    options.py                  # option keys; settings_from_options / options_from_settings / validate_options
    weather_codes.py            # WeatherClass (StrEnum), _CLASSES, classify()
    scoring.py                  # score_day(DayForecast, ScoringSettings) -> DayScore(total, reasons); combine_scores()
    settings.py                 # Settings (weekdays, max_results, min_good_score, ranking_days, outlook_days, scoring)
                                # and ScoringSettings (all weights/thresholds of score_day, flat numbers)
    service.py                  # pick_recommendations(); Recommendation, RecommendationResult, RecommendationStatus
    resorts.py                  # load_resorts(folder) -> list[Resort] sorted by key; 1-5 points, unique names
scripts/try_forecast.py         # runs the whole chain on the real API and prints the ranking
tests/                          # pytest; fixtures in tests/fixtures
```

Import direction: `models` <- `weather_codes` <- `settings` <- `scoring` <- `service`. Never import
upwards (this caused a circular import once: `Recommendation` therefore lives in `service.py`).

Design decisions:

- Resorts are **data** (YAML -> `Resort` dataclass), no class per resort. Subclass/strategy only where
  *behavior* differs (e.g. a price provider per resort source, later).
- Data objects do **not** make calls. Providers do I/O and return data. Scoring/service are pure functions.
- Async only: `aiohttp` with the session injected (HA: `async_get_clientsession(hass)`), no `requests`,
  no pandas, no Open-Meteo SDK (it is sync). One batched request for all resorts; results are matched
  to resorts by position (`zip(strict=True)` guards the length, API keeps the coordinate order).
- Errors: own exception types (inherit `Exception`, not frozen dataclasses). Only the coordinator
  converts `SkiApiError` into `UpdateFailed`. One resort failing should not break the others.
- `Settings` is a frozen dataclass with defaults (weekends, 3 results, min good score). In HA the values
  will come from config entry options. **Never edit the defaults to experiment**; override in the script.
  **Tests must be fully explicit** (own `Settings(...)`, fixed `today`), never rely on defaults or the real date.
- `pick_recommendations(resorts, forecasts, settings=None, *, today=None)`: filters future days
  (`day > today`), allowed weekdays, skips days without data (`DayForecast.has_data`), scores, sorts best
  first, truncates to `max_results`. In HA pass the **local** date as `today`.
- Weather codes: Open-Meteo `weather_code` = WMO interpretation codes (WW), 29 codes, see
  https://open-meteo.com/en/docs . Classified into VERY_GOOD / NEUTRAL / BAD / NO_GO; a test checks that
  every documented code is classified exactly once. `is_good` requires score >= `min_good_score` and
  class != NO_GO.

## Current status

Done and tested (pytest green at last check):

- Open-Meteo provider (daily values, model `meteoswiss_icon_seamless`, batched), parse test with a saved fixture.
- Resort YAML loader; 23 resorts (101 points) in `resorts.yaml`; `scripts/try_forecast.py` prints the ranking.
- `weather_codes.py` + coverage test; `scoring.py` + tests (rating review 22.11, see below); `service.py` + tests (weekday filter, future-only,
  max results, same resort twice, no-go never good, missing resort, status).
- Rating (22.11), weather part max 85; travel time 10 and price 5 follow (max 100):
  - sun 0..40: sunshine / daylight, full from 80 % (DWD reports ~24 % more sun than MeteoSwiss on the
    same point-day; with the share both reach full points on clear days)
  - fresh snow 0..25: snowfall in the 48 h before opening, full from 30 cm
  - snow depth 0..20: model snow depth at opening (09:00), 0 up to 20 cm, full from 1 m; counts all
    season (both models have `snow_depth`; close to measured station depths)
  - wind 0..-30: max gust in ski hours, from 40 km/h, full at 80 km/h
  - temp 0..-20: mean in ski hours; -10 below -15 °C, slush penalty from +2 to +6 °C
  - weather: averaged over the ski hours; NO_GO (rain/freezing/thunder) -50, BAD (fog) -15, snowfall neutral
  - travel 0..10 (relative): train duration of the morning connection from `Settings.home_station`
    to `Resort.station`; shortest trip of all resorts 10, longest 0, linear. No connection in the
    arrival window (`arrival_earliest`..`arrival_latest`, 08:45–09:30, closest to `arrival_target`
    09:00) or no home station = 0. Travel times come from one reference day (the next allowed day);
    the shown connection of a recommendation is fetched for its exact day (`attach_connections`).
  - price 0..5 (relative): day ticket price, cheapest resort 5, most expensive 0; from
    `Resort.day_price_chf` or a `prices` dict (hook for live prices, issue #17). Unknown price = 0.
    Travel and price count towards `is_good` (final total >= `min_good_score`).
  - visibility 0..-30 as before. A clear day on a 1 m base without penalties = 60 = `min_good_score`;
    on a thin base 40. Bluebird powder day on a good base = 85.
  - icy 0..-40: rain + showers (liquid, mm) in the 48 h before opening refreeze into an icy slope;
    no penalty up to 0.5 mm, full from 5 mm. Applies to every point (all points are ski-area
    stations; a village point would be the only place where rain is acceptable). Real data last 30
    days at ~1600 m: drizzle 0.7–3 mm, storms 5–33 mm, rain before opening on about half the days.
    Snow that fell after the last rain hour (> 0.1 mm/h) covers the ice: the penalty shrinks linearly
    and is gone at `ice_cover_full_cm` (20). Snow before the rain is soaked and does not count.
    Decided 22.11: rain only counts for 48 h (same window as fresh snow), not until it is buried.
    Reason: resorts cover icy pistes with artificial snow within a day or two. Do not extend it.
- Horizon / outlook (done 22.11): 8 forecast days. MeteoSwiss where it has data, DWD `icon_seamless`
  for the rest (`_merge`). Days 1..`ranking_days` (5) are ranked; the best allowed day up to
  `outlook_days` (7) is `RecommendationResult.outlook`, a separate 4th entry. The status only looks at
  the ranked days (outlook only -> "No forecast yet").
- Visibility (B, done): `DayForecast.visibility_m` = median of hourly visibility 09:00–16:00, from a second
  batched request with model `icon_seamless`; scored as a penalty (0 at >= 5 km, −30 at <= 1 km, None = 0).

Not started: coordinator, sensor, config flow, dashboard card, ticket prices, train connections.

## Findings from the first real run (Sunday 22.11.2026) — to fix next

1. **Model horizon.** ICON-CH2 forecasts 120 h. On a Sunday evening Fri–Tue come back as `None`, so the
   weekend (Sat/Sun) has no data until about Tuesday. Missing data used to score 0 (misleading) — now
   skipped via `has_data` and reported as "No forecast yet" (verify this change is in the repo).
   Option: drop `models=` (best_match) or add a second model for days 6–8; test what Fri–Tue then return.
   Done 22.11: `has_data` fixed (empty days are skipped), DWD `icon_seamless` fills the days after
   MeteoSwiss' horizon.
2. **Daily `weather_code` = most severe condition of the day.** One shower makes the whole day NO_GO
   (e.g. Andermatt Tue 24.11: 3.7 h sun, still 0 points). Plan: request **hourly** data and judge only
   ski hours (about 09:00–16:00), not the daily worst code.
   Done 22.11: temperature (mean), gusts (max), visibility (median) and the weather code use the ski
   hours 09:00–16:00. Weather points = class points averaged over the ski hours; NO_GO (never good) needs
   rain/freezing/thunder in at least `no_go_min_hours` (2) ski hours. The daily code is only the fallback.
3. **Snow is double-counted in opposite directions**: fresh snow gives up to +20, but snowfall codes
   (73/75/77/85) are in BAD (−15). A powder day ranks far below a dry sunny day. Decide what a snowfall
   day means (powder vs. visibility) and count it in one place.
   Done 22.11: fresh snow = hourly snowfall in the 48 h before opening (09:00); snowfall codes are
   NEUTRAL; snow falling during ski hours only counts through visibility.
4. **Elevation.** Temperature/precipitation come from the village coordinate. Add `elevation_m` to
   `Resort` (mid-station) and pass Open-Meteo's `elevation` parameter. Also consider hourly `snow_depth`
   (base matters more than fresh snow in early season).
   Done 22.11: every weather point has `elevation_m`, passed to Open-Meteo. Snow depth added too (see the
   rating below).
5. Wind and temperature barely discriminate between resorts on the same day; they act as penalties/gates.
   Ranking is mostly sun + snow right now. That is expected in a dry November, tune again in season.
   22.11: wind now uses gusts (daily mean wind max was median 13 km/h, gusts up to 127 km/h).
   Still to do: tune wind and temperature in season (Jan/Feb). Cold penalty stays a flat step (decided).
6. The total is not normalised to 0–100 (maximum is 70). Either normalise or keep `min_good_score` relative.
   Done 22.11: positive parts sun 60 + fresh snow 40 = 100; everything else is a penalty.
7. Zermatt-style cases: rain code together with a max temperature below 2 °C looks inconsistent
   (freezing rain, or grid/elevation mismatch) — check after the elevation fix.
   Checked 22.11 (72 points, last 30 days + 7 forecast days): rain codes below 0 °C in 11 % of the rain
   hours (MeteoSwiss) / 2 % (DWD), almost all between −1 and 0 °C. Cause: Open-Meteo downscales the
   temperature to our station elevation, the precipitation type comes from the (lower) model grid.
   MeteoSwiss never reports freezing-rain codes. Rain near 0 °C is wet snow or freezing rain, bad either
   way, so NO_GO + icy penalty fit. No code change.

## Pain points / requirements added 22.11.2026

**A. Big resorts have several weather spots (multi-point forecasts).**
Large resorts (e.g. Zermatt, Flims Laax) are not one weather location. Weather can differ a lot
within one resort, e.g. Crap Sogn Gion vs. Flims village, and different points/models can predict
differently. One coordinate per resort is therefore not good enough. We need a way to feed **several
weather predictions per resort** (e.g. valley, mid, summit; or several lifts/areas) into one rating
for that resort. Open design questions, to decide together before coding:
- How a resort lists its points (in `resorts.yaml`, e.g. a list of named points with elevation) and
  how the batched Open-Meteo request handles that (more coordinates in the same request).
- How points are combined: average, weighted (e.g. by importance/elevation), or worst/best of the
  points. Keep it simple; start with the simplest rule that gives sensible results.
- Whether recommendations should also name the best point/area inside the resort.
- Disagreeing predictions (different models) could later be part of the same mechanism, but do not
  build that until the multi-point case works.

Decided and implemented 22.11.2026:
- Point weights reviewed and accepted by the owner (22.11).
- `resorts.yaml`: each resort has `points:` (1–5, `MAX_POINTS`), each a ski-area lift station (not the
  village) with `name`, `lat`, `lon`, `elevation_m`, `weight` (default 1; main area 2). Coordinates from
  OpenStreetMap `aerialway=station`, checked against the terrain height.
- One request location per point (72 points, still one batched request per model); `elevation` is
  passed per point. Forecasts are `resort key -> point name -> days` (`Forecasts` in `models.py`).
- Combination: weighted average of the point scores (total and every reason). Points without data on a
  day are left out of that day's average. The recommendation names the best point (`Recommendation.point`,
  `Recommendation.day` is that point's forecast). NO_GO only blocks `is_good` at the best point.

**B. Rename `vision` to `visibility` and use it in the rating.**
`DayForecast.vision` becomes `visibility` (check models, provider/parsing, fixtures, tests, script).
It is currently unused in scoring: it must be considered in the rating (fog/low visibility is bad for
skiing). Check what Open-Meteo offers (daily vs. hourly `visibility`) before deciding the unit and
the scoring rule.

**C. The rating must be configurable, ideally via settings.**
Weights and thresholds in `scoring.py` (sun/snow/wind/temperature/weather class/visibility points,
wind and temperature limits, class points) should not be hard-coded constants. Put them into
`Settings` (or one small scoring-settings dataclass that `Settings` holds), with the current values as
defaults, so config flow options can change them later. `score_day` takes them as a parameter
(default = current behaviour), so tests can pass explicit values.

Done 22.11.2026: `ScoringSettings` in `settings.py` (flat number fields, current values as defaults),
held as `Settings.scoring`; `score_day(day, scoring)` reads every weight and threshold from it and the
service passes `settings.scoring`. Tests use `tests/scoring_values.py` (`SCORING`, every value written
out); `test_defaults_are_the_documented_values` fails when a default changes, so a weight change is
always a visible decision. Same real-data scores before and after the refactor (576 point-days).

**D. Coding style: keep what we have, no over-engineering.**
Keep the style established in the existing files: small modules, frozen dataclasses, plain functions
for pure logic, classes only where there is I/O or state. No abstraction without a second use case,
but also no flattening that makes code hard to read. Not everything needs a base class, a factory or
a plugin system. If you are unsure, pick the simpler version and explain the trade-off in one or two sentences.

**E. Clean up boilerplate.**
The ludeeus blueprint brought a lot of files we do not need (demo API client, example switch/binary
sensor, translations for them, docs, CI leftovers, etc.). Remove everything not relevant for this
integration. Before deleting, list what you plan to delete and why, and keep what HA needs
(`manifest.json`, `__init__.py`, `const.py`, `config_flow.py`, `coordinator.py`, `sensor.py`,
`strings`/`translations` for our own options, hassfest/CI config if useful). Update `manifest.json`
and imports so that the integration still loads and tests/ruff stay green.

## Git rules (important)

- **One branch and one PR per finished change.** Branch from an up-to-date `main` (`feature/...`,
  `fix/...`, `docs/...`), push it and open a pull request to `main`. Do not commit to `main` directly;
  the owner reviews and merges.
- **Every PR targets `main`**, never another feature branch. If a PR builds on an unmerged one, branch
  from it but still target `main` and say "merge #N first" in the description. (22.11: stacked PRs #3/#4
  were merged into their base branches instead of `main`; GitHub only retargets when the base branch is
  deleted.)
- Claude may appear as co-author: a `Co-Authored-By` trailer in commits and the Claude Code line in PR
  descriptions are fine. Commits still use my own git author/committer identity (do not change
  `user.name`/`user.email`).
- Small, focused commits (one topic each). Do not commit junk (caches, `.venv`, secrets).
- `gh` is not installed in the dev container; PRs are opened through the GitHub REST API with the
  credential from the VS Code git credential helper (never print the token).

## Next steps (suggested order)

1. Live ticket prices (issue #17) and the per-day Snow'n'Rail availability (issue #19). Static prices,
   the relative price score and the static `snow-n-rail` tag are done.
2. Dashboard card (Markdown card with the `table` attribute, see README); scoring weights in the
   options form (second step) if needed. Options flow done: Configure button with home station
   (checked against the SBB station search, suggestions on typos), ski days, number of results, min
   score, arrival window, weather interval (`OptionsFlowWithReload`).
   Sensor done: state = headline (Good day / No good day / No forecast yet); attributes
   `recommendations` + `outlook` (classification, score, date, resort, point, weather_icon, price_chf,
   train, snow_n_rail, tags, reasons) and `table`, all three excluded from the recorder.
   `table` (23.11, owner's layout v2): `<table width="100%">` + `<colgroup>` (64 | 56 | rest | 44 px),
   three rows per result: `score (size 5, centered) + classification/icon (size 1)` (rowspan 3) |
   `resort · best point (size 1)` (colspan 2) | `price + <code>SnR</code>` (rowspan 3); then
   `date | Dep. station, 07:15 · S5 · Pl. 3`; then `(empty) | Arr. station, 09:10` (Dep./Arr. aligned).
   The Markdown card only allows plain HTML (no style/class); borders, spacing, ellipsis and the SnR
   badge (styled `code`) come from the card-mod snippet in the README.
   Future: issue #28 (configurable rows/cells, click opens all results).
   Weather icon = most frequent weather over all points and ski hours (weighted, ties -> worse); for
   dry weather the sunshine share decides (sunny from 60 %, partly cloudy from 25 %).
   Failed updates are visible: setup uses `async_refresh()` (no `first_refresh`), so the sensor exists
   even if the first update fails; it stays available: state "No data yet" + table/`last_error` with the
   reason, or the last result + "Last update failed". Messages via `errors.describe()` (source + rate
   limit / HTTP status / timeout / unreachable, no request URL) + "next try in 60 min".
   Coordinator done: runs hourly (`UPDATE_INTERVAL`), `build_recommendations` from `lib/pipeline.py`,
   SBB travel times cached once a day, exact connections only for the shown results, `SkiApiError` ->
   `UpdateFailed`, local date as today; settings from the options form (`settings_from_options`).
   Weather interval: Open-Meteo only every `Settings.weather_interval` (option, default 3 h); on errors
   (429) the last forecast is used up to `weather_max_age` (12 h). Open-Meteo answered 429 Too Many
   Requests on 22.11 after many manual runs with 101 points (2 requests with > 10 variables each).
3. Tune wind and temperature in season (Jan/Feb); re-check `DWD_SUN_FACTOR` in winter.
   (Done: A, B, C, findings 1–4, 6, 7, snow depth, SBB connection, static prices, 23 resorts.)

## Adding a resort

Add `custom_components/ski_resort_recommender/resorts/<key>.yaml` (the file name is the key, lower case with
underscores) with `name`, `meteoswiss_point_id` (empty), `station` (the SBB stop at the gondola, exactly as
transport.opendata.ch names it, or empty), `day_price_chf` (adult high-season day price), optional
`snow_n_rail: {offer, up_to_pct}` and `points:` (1-5 lift stations with `name`, `lat`, `lon`,
`elevation_m`, `weight`). Check coordinates against the terrain height (Open-Meteo elevation API) and the
station with `/v1/locations`. Every point adds a location to each Open-Meteo request (rate limit).

## Data sources / facts

- Weather: Open-Meteo (MeteoSwiss ICON-CH models); MeteoSwiss Open Data also exists (CSV/STAC, hourly
  point forecasts, ~6000 points incl. mountain POIs, cite "Source: MeteoSwiss").
- Visibility on Open-Meteo (checked 22.11.2026): hourly only, metres, no daily aggregate. Not provided by
  `meteoswiss_icon_seamless`, ECMWF or Météo-France. `icon_seamless` (DWD) has it ~5 days ahead, later days
  are None, so days 1–5 can get a visibility penalty and later days cannot. GFS caps at 24 km.
- Model accuracy, sunshine (checked 22.11.2026 against measured daily sunshine `sre000d0` at 12
  SwissMetNet mountain stations, 30 days, via the Open-Meteo previous-runs API): MeteoSwiss = 1.05x the
  measurement (MAE 1.1 h), DWD latest = 1.59x (MAE 2.4 h), DWD 5 days ahead = 1.72x (MAE 3.7 h).
  MeteoSwiss is preferred wherever it has data; DWD days get `DWD_SUN_FACTOR` = 0.6. Re-check in winter.
  Observations: `https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/<sta>/ogd-smn_<sta>_d_recent.csv`
  (`htoautd0` = measured snow depth). No MeteoSwiss previous runs in Open-Meteo.
- The `elevation` in an Open-Meteo response is the 90 m terrain height of the coordinate, used for
  downscaling (not the model grid height). We pass each point's `elevation_m` explicitly.
- MeteoSwiss `meteoswiss_icon_seamless` daily data only reaches today + 4 days (22.11: Fri–Sun empty);
  DWD `icon_seamless` daily data reaches about today + 7.
- Station coordinates: OpenStreetMap Overpass (`aerialway=station`), terrain height from the Open-Meteo
  elevation API, Swiss names cross-checked with the swisstopo search API.
- Day prices (`day_price_chf`, adult, high season 2026/27, CHF, researched 22.11.2026). Sources:
  schneehoehen.de price pages (Hauptsaison 2026/27), official sites, nume.ch, freizeit.ch; bergfex blocks
  automated reads. Dynamic resorts use the high-season desk/standard price:
  Laax 92 (dynamic, ~85 online), Flumserberg 76 (weekend), Zermatt 104 (dynamic), Andermatt and
  Andermatt+Sedrun+Disentis 99 (one pass), Engelberg 78 (dynamic, standard), Pizol 74, Davos Parsenn and
  Jakobshorn 87, Melchsee-Frutt 69, St. Moritz Corviglia 95 (dynamic), Corvatsch 88, Scuol 69, Samnaun and
  Ischgl 82 (Silvretta Arena, CHF price of Samnaun), St. Anton 78 (EUR 85 x 0.9223, ECB 20.11.2026),
  Arosa Lenzerheide 89, Saas-Fee 84, Adelboden-Lenk 80 (no official individual list; group rate 68),
  Grindelwald-Wengen 83, Verbier 4 Vallées 94 (official), Crans-Montana 94 (desk), Hoch-Ybrig 62.
  Live prices: issue #17 (pricenow etc. are private booking APIs: only with permission).
- Snow'n'Rail (SBB RailAway train + ski pass): `Resort.snow_n_rail` (offer slug + "up to" discount) in
  `resorts.yaml`; recommendations of such resorts get the tag `snow-n-rail` (`SNOW_N_RAIL_TAG`). The
  discounted tickets are limited per month (discount steps down, then none); the per-day availability check
  is issue #19 (no public API; the RailAway shop API is private -> only with SBB's permission). Offers
  2026/27 from skiboard.ch / deinskigebiet.ch; Andermatt Gemsstock left out (not named in the ASD offer),
  Davos Jakobshorn 10 % (sources say 10 or 30 %).
- SBB: `https://transport.opendata.ch/v1/connections` (free, no key, no rate-limit headers; keep calls
  few, `MAX_PARALLEL` 4). `journey.name` is the train number for trains, an internal trip id for buses.
  Not in the Swiss timetable: Ischgl (station left empty). St. Anton returned no plausible morning
  connection for 28.11. Stöckalp (Melchsee-Frutt) has no bus before the winter season (from mid-Dec
  07:10 -> 08:55 from Zürich). Tests and Claude use Zürich HB, never the owner's home station.
- Prices: dynamic pricing at many resorts (Adelboden-Lenk, Arosa Lenzerheide, Pizol, ...), no standard API.

## Working agreements

- Small steps, tests first for scoring/service logic; run `pytest` and `ruff check` before finishing.
- Explain non-obvious Python/HA choices briefly; the owner is rusty on software-dev conventions.
- Do not silently change defaults in `Settings` or weights; tell me when a weight change alters rankings.
