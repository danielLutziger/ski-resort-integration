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
  resorts.yaml                  # resorts as DATA (one file, list of entries)
  lib/                          # NO homeassistant imports, testable alone
    models.py                   # Resort, DayForecast (frozen dataclasses); imports nothing from lib
    errors.py                   # SkiApiError (base, Exception) -> SkiApiConnectionError, SkiApiParseError
    open_meteo.py               # OpenMeteoProvider (aiohttp); pure _combine/_parse_daily/_ski_hours_visibility
    weather_codes.py            # WeatherClass (StrEnum), _CLASSES, classify()
    scoring.py                  # score_day(DayForecast) -> DayScore(total, reasons)
    settings.py                 # Settings dataclass (weekdays, max_results, min_good_score)
    service.py                  # pick_recommendations(); Recommendation, RecommendationResult, RecommendationStatus
    resorts.py                  # load_resorts(path) -> list[Resort]
scripts/try_forecast.py         # runs the whole chain on the real API and prints the ranking
tests/                          # pytest; fixtures in tests/fixtures
```

Import direction: `models` <- `weather_codes` <- `scoring` <- `service` (and `settings`). Never import
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
- Resort YAML loader; ~15 resorts in `resorts.yaml`; `scripts/try_forecast.py` prints the ranking.
- `weather_codes.py` + coverage test; `scoring.py` (sun 30, fresh snow 20, wind penalty above 30 km/h,
  temperature band, weather class points) + tests; `service.py` + tests (weekday filter, future-only,
  max results, same resort twice, no-go never good, missing resort, status).
- Visibility (B, done): `DayForecast.visibility_m` = median of hourly visibility 09:00–16:00, from a second
  batched request with model `icon_seamless`; scored as a penalty (0 at >= 5 km, −30 at <= 1 km, None = 0).

Not started: coordinator, sensor, config flow, dashboard card, ticket prices, train connections.

## Findings from the first real run (Sunday 22.11.2026) — to fix next

1. **Model horizon.** ICON-CH2 forecasts 120 h. On a Sunday evening Fri–Tue come back as `None`, so the
   weekend (Sat/Sun) has no data until about Tuesday. Missing data used to score 0 (misleading) — now
   skipped via `has_data` and reported as "No forecast yet" (verify this change is in the repo).
   Option: drop `models=` (best_match) or add a second model for days 6–8; test what Fri–Tue then return.
2. **Daily `weather_code` = most severe condition of the day.** One shower makes the whole day NO_GO
   (e.g. Andermatt Tue 24.11: 3.7 h sun, still 0 points). Plan: request **hourly** data and judge only
   ski hours (about 09:00–16:00), not the daily worst code.
3. **Snow is double-counted in opposite directions**: fresh snow gives up to +20, but snowfall codes
   (73/75/77/85) are in BAD (−15). A powder day ranks far below a dry sunny day. Decide what a snowfall
   day means (powder vs. visibility) and count it in one place.
4. **Elevation.** Temperature/precipitation come from the village coordinate. Add `elevation_m` to
   `Resort` (mid-station) and pass Open-Meteo's `elevation` parameter. Also consider hourly `snow_depth`
   (base matters more than fresh snow in early season).
5. Wind and temperature barely discriminate between resorts on the same day; they act as penalties/gates.
   Ranking is mostly sun + snow right now. That is expected in a dry November, tune again in season.
6. The total is not normalised to 0–100 (maximum is 70). Either normalise or keep `min_good_score` relative.
7. Zermatt-style cases: rain code together with a max temperature below 2 °C looks inconsistent
   (freezing rain, or grid/elevation mismatch) — check after the elevation fix.

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
- Claude may appear as co-author: a `Co-Authored-By` trailer in commits and the Claude Code line in PR
  descriptions are fine. Commits still use my own git author/committer identity (do not change
  `user.name`/`user.email`).
- Small, focused commits (one topic each). Do not commit junk (caches, `.venv`, secrets).
- `gh` is not installed in the dev container; PRs are opened through the GitHub REST API with the
  credential from the VS Code git credential helper (never print the token).

## Next steps (suggested order)

1. Settings-driven scoring (C), keep tests green. (B is done.)
2. Fix findings 2 and 3 (hourly ski-hours window, no double counting).
3. Multi-point resorts (A): agree on the data format and combination rule first, then implement.
4. Add `elevation_m`; test `best_match` vs. `meteoswiss_icon_seamless` for days 6–8.
5. Coordinator (hourly poll, `UpdateFailed`), sensor (state = headline, attributes = recommendations),
   config flow (weekdays, number of results, min score, scoring weights), then a Markdown dashboard card.
6. Later: train connection (Swiss public transport integration is already installed in my HA), ticket
   prices (no public API; many Swiss resorts use dynamic pricing — start with a static price per resort,
   never rely on scraping blindly).

## Data sources / facts

- Weather: Open-Meteo (MeteoSwiss ICON-CH models); MeteoSwiss Open Data also exists (CSV/STAC, hourly
  point forecasts, ~6000 points incl. mountain POIs, cite "Source: MeteoSwiss").
- Visibility on Open-Meteo (checked 22.11.2026): hourly only, metres, no daily aggregate. Not provided by
  `meteoswiss_icon_seamless`, ECMWF or Météo-France. `icon_seamless` (DWD) has it ~5 days ahead, later days
  are None, so days 1–5 can get a visibility penalty and later days cannot. GFS caps at 24 km.
- Different models use different grid cells for the same coordinate (e.g. Flims village coordinate:
  `icon_seamless` grid elevation 2253 m). Relevant for finding 4: pass `elevation` to both requests.
- Prices: dynamic pricing at many resorts (Adelboden-Lenk, Arosa Lenzerheide, Pizol, ...), no standard API.

## Working agreements

- Small steps, tests first for scoring/service logic; run `pytest` and `ruff check` before finishing.
- Explain non-obvious Python/HA choices briefly; the owner is rusty on software-dev conventions.
- Do not silently change defaults in `Settings` or weights; tell me when a weight change alters rankings.
