# Demo video script: BMS dashboard (about 60 s)

Screen recording of the building display (`/bms/`), with a voice-over and/or on-screen text added afterwards. The playback console (`/`) appears only briefly at the start.

## Before recording

1. Start everything: `docker compose up --build` (dashboard at `http://localhost:8000`).
2. Open two windows: the console (`/`) and the display (`/bms/`). Record the display.
3. Find a start hour where at least one building shows **Watch** or **Alert** (cold weather), by test runs. Write it down here: `__________`. (Not yet checked.)
4. Set the speed to 6 hours/s or 1 day/s. Use light mode. Pre-select **3d** on the Smart heating page.
5. Record at 1080p. Do one rehearsal run.

## Script

| Time | On screen | Voice-over | Optional on-screen text |
|---|---|---|---|
| 0:00-0:07 | Console at `/`: press Play, show the clock and speed; switch to `/bms/` | "This is our heating optimization system for municipal buildings. We replay real data from three Oslo schools, and every screen follows one shared clock." | "Replay of 3 Oslo schools, Oct 2022 - Mar 2023" |
| 0:07-0:25 | **Control panel:** point at the summary tiles and the status bar; click the worst building to open the drawer (status reasons, 24 h graph) | "The control panel shows each building's heat use now, over the last 24 hours, and per square metre. An AI model forecasts heat use 1, 6 and 24 hours ahead. When a building uses much more heat than forecast, it is flagged Watch or Alert. The drawer gives the reason in plain words." | "AI forecast: +1 h / +6 h / +24 h"; "Status: OK / Watch / Alert / No data" |
| 0:25-0:48 | **Smart heating:** KPI tiles, then the temperature chart (hover), then the power chart; switch 3d to 7d | "Our digital twin simulates a classroom. We compare today's fixed schedule with smart heating that uses the weather forecast. The smart version uses less energy and has a lower peak power. It also keeps the room inside the comfort band during occupied hours." | "Digital twin: simulated 60 m² classroom"; "Current vs. smart heating" |
| 0:48-0:55 | **About:** scroll past the data source and room model | "The About page explains where each number comes from and how much to trust it." | "Sources, model, benchmarks, parameters" |
| 0:55-1:00 | Settings: toggle dark mode, then back to the control panel | "The display is read-only, and every result comes from our open API. Thank you." | "Data: SINTEF COFACTOR-SBHUB (CC BY 4.0)" |

About 140 words in total. If it runs long, cut the About segment.

## Points to keep honest

- The classroom is a **simulation**, and smart heating gets a perfect weather forecast, so it shows the best case.
- The status judges **heat use only** (more heat than expected). The data has no indoor temperature.
- Before saying "saves X %", read the real numbers on the KPI tiles during the test run and adjust the sentence.

## Features covered

- Shared replay clock and playback console
- Control panel: summary tiles, status bar, building list with forecasts, building drawer
- Smart heating: baseline vs optimized classroom (temperature, power, cumulative energy, table view)
- About page, units (°C/°F), light/dark theme
