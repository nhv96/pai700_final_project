# BMS display: Heat Control

The building-management display for Trollhättan Stad / Kraftstaden (a teammate's UI), served by the dashboard server at `/bms/`. It is a read-only demo display: it shows what the replay has reached and follows the shared clock that the playback console controls. Plain HTML, CSS and JavaScript, no build step.

## What it shows

- **Control panel:** the replayed buildings (heat now, last 24 h, kWh/m², outdoor temperature) and a drawer per building with its last 24 hours.
- **Smart heating:** a simulated 60 m² classroom, legacy (baseline) vs combined (optimized) controller, for the last 1-7 completed days before the clock, on the weather of the selected building. Plus the AI heat forecast (1, 6, 24 h) made at the clock's hour.
- **Settings:** °C/°F and light/dark theme (kept in the browser).
- **About:** data provenance, scenarios, room model, benchmarks and parameter table with confidence tags (`data/about.json`).

Everything shown is from the API (`/api/playback`, `/api/readings`, `/api/twin/compare`, `/api/forecast/*`). Nothing later than the clock is shown. Heat use is the whole building; the classroom simulation is an illustration of control, not of a building's bill. There is no cost, CO₂, AHU, room or alarm data because the data has none.

## Files

```
index.html       app shell and markup
dashboard.css    styles (light/dark via CSS variables)
dashboard.js     rendering: control panel, drawer, controller-comparison charts, About
data-source.js   the adapter: API + shared clock -> the page's data object
data/about.json  static About tables (benchmarks, parameters, open items)
assets/          logo and sidebar background
```

## Run

Start the services (see `../../../README.md`), open `http://localhost:8000/bms/`, and press Play in the playback console at `/`.

## Credits

Weather and heat data: SINTEF COFACTOR-SBHUB Oslo (Lien et al., *Data in Brief*, 2025, CC BY 4.0). Benchmarks: SKR 2011 (citing Energimyndigheten STIL2). Radiator survey: Jangsten 2017 (Chalmers).
