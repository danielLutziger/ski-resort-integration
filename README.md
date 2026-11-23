# Ski Resort Recommender

Home Assistant custom integration that tells you **when and where to ski**.

It rates the upcoming days for 23 Swiss/Austrian ski resorts (`custom_components/ski_resort_recommender/resorts/`,
one file per resort) from weather forecasts ([Open-Meteo](https://open-meteo.com/), MeteoSwiss and DWD
models), the snow, the train connection from your home station (SBB timetable via
[transport.opendata.ch](https://transport.opendata.ch)) and the day ticket price. One sensor shows the result:

- **State:** `Good day`, `No good day` or `No forecast yet`
- **Attributes:** `recommendations` (top days), `outlook` (best of days 6–7) and `table` (Markdown for a dashboard card)

## Installation

### Option A: HACS (the repository must be public)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/danielLutziger/ski-resort-integration`,
   type **Integration**.
2. Install **Ski Resort Recommender** and restart Home Assistant.

HACS cannot install from private repositories.

### Option B: copy the folder (works with a private repository)

1. Copy `custom_components/ski_resort_recommender/` into your Home Assistant configuration folder, so that
   you get `config/custom_components/ski_resort_recommender/` (Samba, SSH or Studio Code Server add-on).
2. Restart Home Assistant.

### Set it up

1. **Settings → Devices & services → Add integration → "Ski Resort Recommender"**, then confirm.
2. On the integration, click **Configure** and set:
   - **Home station** as in the SBB timetable (e.g. `Zürich HB`; a typo shows suggestions). Leave it empty
     for no train connections.
   - **Ski days** (default Saturday and Sunday), **number of recommendations**, **minimum score**.
   - **Arrival window** at the gondola (default 08:45 – 09:00 – 09:30).
   - **Weather update interval** (default 3 h; raise it if Open-Meteo rate-limits).
3. Saving reloads the integration. The sensor is `sensor.ski_resort_recommender`.

### Dashboard card

A Markdown card shows the table, one compact block per result:

```
 52          Hoch-Ybrig · Spirstock                                  62.-
 Not good ⛅  Sat 28.11  Dep.  Zürich HB, 07:15 · S5 · Pl. 3          [SnR]
                        Arr.  Hoch-Ybrig, Talst. Weglosen, 09:10
```

(score and classification with the weather icon; resort · best point; date, departure and arrival of the
morning train; day price in CHF; SnR = Snow'n'Rail offer)

Home Assistant only allows plain HTML in a Markdown card, no CSS. The layout (incl. the dividers between results) works without CSS; for **no borders,
tight spacing, "…" instead of line breaks and the SnR badge** add these
[card-mod](https://github.com/thomasloven/lovelace-card-mod) styles:

```yaml
type: markdown
content: "{{ state_attr('sensor.ski_resort_recommender', 'table') }}"
card_mod:
  style:
    .: |
      ha-card {
        --markdown-table-border-color: transparent;
        --markdown-table-border-width: 0;
      }
      ha-markdown { padding: 2px !important; }
    ha-markdown$: |
      table { display: table !important; width: 100% !important; table-layout: fixed;
              border-collapse: collapse; border: 0 !important; margin: 0 !important; }
      tr, th, td { border: 0 !important; background: none !important; }
      td { padding: 0 2px !important; line-height: 1.1; vertical-align: middle;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      font { line-height: 1.1; }
      hr { margin: 2px 0; border: 0; border-top: 1px solid var(--divider-color); }
      code { font-family: inherit; font-size: 10px; font-weight: 600; line-height: 1;
             padding: 2px 7px; border-radius: 10px;
             background: var(--primary-color); color: var(--text-primary-color, #fff); }
```

If the card still scrolls, give it more height (e.g. `grid_options: rows: 4`) or lower *Number of
recommendations* in the options.

### Troubleshooting

- The card shows **"⚠️ No data yet: …"**: the first update failed. The reason is shown (also in the sensor
  attribute `last_error` and in *Settings → System → Logs*), and the integration retries every hour.
  **"Open-Meteo rate limit (HTTP 429)"** means the free weather API quota is used up for this internet
  connection; raise the *Weather update interval* if it happens regularly.
- The card is **completely empty**: the entity does not exist. Check *Developer tools → States* for
  `sensor.ski_resort_recommender` (the ID can differ, e.g. `_2`) and *Settings → Devices & services*.

## Development

- Open the repo in the VS Code dev container.
- `scripts/develop` starts a dev Home Assistant (http://localhost:8123) with this integration loaded;
  set it up there as described above.
- `pytest` runs the tests, `ruff check .` the linter.
- `python -m scripts.try_forecast --from "Zürich HB" [--all]` runs the whole chain against the real APIs.
- Adding a resort: see "Adding a resort" in `CLAUDE.md`.

Based on [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint) (MIT).
