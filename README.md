# Ski Resort Recommender

Home Assistant custom integration that tells you **when and where to ski**.

It fetches weather forecasts from [Open-Meteo](https://open-meteo.com/) (MeteoSwiss ICON-CH models)
for a list of Swiss/Austrian ski resorts (`custom_components/ski_resort_recommender/resorts.yaml`),
scores each upcoming day and shows the best few recommendations (default: weekends, top 3) in one
sensor: the state is the headline, the attributes hold the list.

Status: work in progress. The forecast/scoring library in `lib/` works and is tested; the Home
Assistant coordinator and sensor are still stubs. Ticket prices and train connections are planned.

## Development

- Open the repo in the VS Code dev container.
- `scripts/develop` starts a dev Home Assistant instance with this integration loaded.
- `pytest` runs the tests, `ruff check .` the linter.
- `python -m scripts.try_forecast` runs the whole chain against the real API and prints the ranking.

Based on [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint) (MIT).
