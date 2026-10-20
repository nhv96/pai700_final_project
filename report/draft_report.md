# Feasibility Study of AI-Assisted Heating Optimization in Municipal Buildings

**Draft project report, Group 10, PAI700 Project Work in AI and Automation, University West**

Client: Trollhättan Stad / Kraftstaden (contacts: Peter Versén, Property Manager; Erik Beckius, IT Strategist)

Status: DRAFT. Items in **[square brackets]** must be filled in or confirmed by the team before submission.

---

## Abstract

Trollhättan Stad asked us to find out, before any investment, whether AI-assisted heating optimization is a viable and cost-effective solution for its older municipal buildings. We built a small proof of concept with three parts: an **AI model** that forecasts the heat use of a school building 1, 6 and 24 hours ahead, a **digital twin** that simulates one classroom with its radiator and ventilation and compares today's control with improved control, and a **dashboard** that shows both to a building manager.

The AI model was trained and tested on eleven years of hourly data from three Oslo schools. On a test period it never saw, it forecasts the heat use of a whole building with an error of about 9 % (1 hour ahead) to 13 % (6 and 24 hours ahead). That is half to two thirds less error than a simple "same hour yesterday" guess. This number is an upper bound, because the test used measured weather as a perfect weather forecast.

In the simulated classroom, the improved controller (forecast pre-heating plus room-compensated supply-air temperature) cut heat by 21 % in the base case and by 11 to 19 % in sunny late-winter weeks on real Oslo weather. In the cold and dark weeks of November to mid-February it saved nothing and used up to 4.7 % more heat in exchange for fewer cold lessons. Over the ten sampled winter weeks the net difference was zero. **We therefore do not claim an annual saving.** We claim that a saving is plausible in the weeks when sun and people overheat the room, that its size is between 0 and about 20 % of classroom heat, and that proving it needs indoor temperature and plant data from a real building. The cost equivalent is the saved kWh times the district-heating price. With the 1.10 to 1.35 SEK per kWh from our background check, a sunny week saves about 25 to 47 SEK per classroom and each 1 % of a school's yearly heat is worth about 6,000 to 16,000 SEK. The price has to be confirmed with Kraftstaden, and the investment cost is not estimated, because it needs facts from the client that we could not obtain (section 12).

---

## 1. Introduction

### 1.1 Background

Municipalities face rising energy costs and sustainability targets while managing many ageing buildings. Many of these buildings are heated with fixed schedules that do not react to the weather, the sun or the people in the room. In Sweden, schools and preschools use about 5 TWh a year, and in 2006 the average school used about 213 kWh/m², of which 152 kWh/m² was heating [1]. Most schools are heated by district heating through water radiators. The radiators are rarely the limit; the control is [2].

The client describes a familiar pattern. Heating runs hard in the morning, the room overshoots, and around midday the ventilation ramps up to blow the extra heat out. The ventilation then works against the radiator ("system fighting"). Because the walls store heat, the radiators keep giving heat after the room is already warm enough. There is also no central overview of the buildings.

### 1.2 Aim

From the client's proposal, the project is a pre-study (förstudie) that should:

1. analyse current practice and map available data sources,
2. evaluate AI-based heating optimization, using open-source software and cheap sensors,
3. assess expected energy savings, investment cost, scalability and integration complexity,
4. demonstrate a proof of concept using weather forecasts, building schedules and historical data.

The focus is decision support for future municipal investments, not a finished control system.

### 1.3 Research question

> Is it feasible to use AI to optimize heating in old municipal buildings?

We split it into three questions that our proof of concept can address:

- **Q1.** Can the heat use of a school building be forecast well enough, 1 to 24 hours ahead, from past heat use, weather and the calendar?
- **Q2.** Does smarter control reduce heat use and cold lessons in a simulated classroom, and when?
- **Q3.** Can the results be put in front of a building manager in one place?

### 1.4 Scope and honesty about limits

- No real building of the client was available. The data comes from three public Oslo schools, and the classroom is simulated with **assumed** parameters.
- The Oslo data contains no indoor temperature, occupancy or valve data. The overshoot and the saving are therefore shown in simulation only.
- Cooling is not covered. Hot water is part of the heat figure in the Oslo data (section 6).

---

## 2. Project team and division of work

Group 10, Master in AI and Automation, University West.

| Member | Main parts |
|---|---|
| Hoang Vinh Nguyen | Digital twin; AI model (data preparation, training, testing, forecast service) |
| Mary Wagura | Heat model of the room; integration of the heat model into the twin |
| Kelvin Njoroge Wanjiku | Dashboard |

**[Check the split and the names.]** 

The three parts were developed as separate programs that talk to each other over HTTP, so each member could work on their own part without breaking the others. They share one frozen data window (section 6.4), which means they can be compared at the same timestamps.

---

## 3. Problem definition

**What problem are we solving?** Heating a school with fixed schedules wastes heat in two ways.

1. **Overshoot and system fighting.** On a cold morning the radiator pre-heats the room. Then the sun and the pupils add heat. The room goes above 24 °C and the ventilation switches to a higher flow. The ventilation heating coil keeps warming the cold incoming air to 21 °C, even though the room is already warm. The school pays twice: for radiator heat and for coil heat.
2. **Poor start time.** If heating starts too early, heat is wasted. If it starts too late, the first lesson is cold. Thermal inertia of the walls makes the right moment hard to find.

The literature reports the same symptoms in Swedish schools: high indoor temperatures [3] and measured energy use that differs from the calculated use by between 44 % below and 28 % above, driven mainly by user-related parameters [4]. Operations optimization in school buildings is reported to give savings of roughly 10 to 30 % [1].

---

## 4. Requirements

The proposal does not set numeric targets. We derived these requirements from it and from the problem; **[confirm with the client]**.

| ID | Requirement | How we check it |
|---|---|---|
| R1 | Forecast the heat use of a building 1, 6 and 24 hours ahead | Error on a test period the model never saw, compared with simple baselines |
| R2 | Use only information that exists at forecast time | Test that changing the future heat does not change the forecast |
| R3 | Show whether better control can reduce heat and cold lessons | Simulation of legacy against improved control, on real weather and with a sensitivity analysis |
| R4 | Use open-source software and data that cheap sensors could provide | Only open tools; inputs are heat meter, outdoor temperature, sun, wind and the calendar |
| R5 | Give a central overview of buildings, forecasts and twin results | Dashboard |
| R6 | State clearly what is simulated, assumed and measured | Warnings in the dashboard, parameter confidence labels, this report |
| R7 | Estimate savings and their cost equivalent | Section 12 |

---

## 5. Concepts and solution choice

**What alternatives exist?** Heating can be improved by rules (weather compensation, optimal start and stop), by model-based control that uses a model of the room, or by AI that forecasts demand or learns the control. The literature review plan compares these. Fully AI-learned control needs a lot of measured indoor data that the client has not supplied yet.

**Why did we choose this solution?** Because the pre-study must be cheap and must work without a new building-management system, we combined three parts, each using the cheapest suitable method:

| Part | Choice | Reason |
|---|---|---|
| AI model | Gradient-boosted trees (LightGBM), plus a GRU neural network at longer horizons | Trees are fast, robust and need little data preparation. The GRU adds a second view of the history and helps at 6 and 24 hours. |
| Digital twin | Our own two-node room model with a radiator and an air-handling unit | Transparent and fast, and it needs few parameters. A safe place to test control ideas without touching a real building. |
| Dashboard | Web page with replay of data | One place for the overview; adding sources means adding routes. |

The AI model forecasts demand; the twin tests control. We decided that the AI forecast is a **benchmark only** for the twin: the twin's controllers do not read it. The reason is that the AI forecasts a whole building and the twin simulates one 60 m² classroom, and a rule to map one to the other would be an unvalidated assumption.

---

## 6. Data

### 6.1 Where the data comes from

We use the **COFACTOR-SBHUB Oslo** dataset: hourly data from 48 Oslo schools, published by SINTEF under the licence CC BY 4.0 (DOI 10.60609/2hvr-wc82; Lien et al. 2025, Data in Brief 63, 112288). We chose it because we needed building heat data over several years, openly available. A similar Drammen set was dropped.

### 6.2 Earlier data: SMHI weather

At the start of the project we used weather data from **SMHI** (the Swedish Meteorological and Hydrological Institute, open data, CC BY 4.0; hourly observations, with the weather station at Trollhättan–Vänersborg Airport as the nearest to the client). It was used to build and try out the **heat model** of the room: it gave realistic outdoor temperature and sun to drive the model while the room equations and parameters were being set up.

SMHI provides weather only. It has **no heat use**, so it could not be used to train the AI model, which needs heat use as its target. For that reason we moved to the Oslo dataset above. The SMHI work was still valuable, because it let the team develop and check the heat model on real Swedish weather before the heat data arrived. **[Mary: please check the wording and add which SMHI parameters and period were used.]**

### 6.3 What we used

Three Oslo schools with a long history and few gaps: buildings **8105** (8,415 m², built 2011), **8107** (6,063 m², 1982) and **8116** (13,408 m², 1959). The period is 2012-10-01 to 2023-10-22, about 90,000 hourly rows per building after cleaning.

| Column | Meaning | Use |
|---|---|---|
| `HtTot` | Heat from district heating, Wh per hour (space heating plus hot water) | Target of the AI model |
| `Tout` | Outdoor temperature, °C | AI input; weather for the twin |
| `SolGlob` | Sun on a horizontal surface, W/m² | AI input; weather for the twin (converted to the south wall) |
| `WindSpd`, `WindDir` | Wind speed and direction | AI input |
| `floor_area`, `year_of_construction` | Building data | Floor area for per-m² figures; construction year not used by the model |

Time is fixed at UTC+1 all year, with no daylight saving.

**What the data cannot give us:** indoor temperature, occupancy, valve position, supply temperature, and a split of `HtTot` into radiators, ventilation and hot water. This limits what can be validated (section 13).

### 6.4 Cleaning and the frozen window

The cleaning rules were chosen after a quality scan and each decision is recorded in `notebooks/quality_inspect_decision.md`:

- Gaps in weather of up to 3 hours are filled by interpolation; longer gaps are left empty and those rows are dropped.
- The sentinel value −273.15 °C for the outdoor temperature is treated as missing, and negative sun values are set to 0.
- For `HtTot`, empty rows, zero rows (outside June to August) and flat runs of 6 or more identical hours are dropped. In summer, zero heat is real information (heating is off) and is kept.
- Zero sun values are kept (they are real: night).
- The wind direction is stored as sine and cosine so that 359° and 1° are neighbours.

Three components needed to look at the same period, so we created a **frozen window**: 2022-09-24 to 2023-03-31 for the three buildings (4,536 hourly rows each: a 7-day warm-up plus the replay from 1 October). The file is immutable and has a checksum. A **replay feed** plays it like live sensor data, one hour at a time, and never returns heat use after the replay clock. The window lies inside the AI model's test period, so the model has never seen it.

---

## 7. The AI model

### 7.1 What it does

At a given hour it forecasts the building's heat use (`HtTot`) for **1, 6 and 24 hours ahead**, from the previous 168 hours (one week) of heat use and weather, the coming hours' weather and the calendar. Heat in this section is the whole building, not a classroom.

### 7.2 Inputs

- The last 168 hours of heat use and weather.
- Calendar: hour, weekday, month, public holidays, school breaks and "off" days (for the target day, the day before and the day after).
- Trend features, for example the change in heat use over the last 1, 3, 6 and 24 hours, how far the current hour is from its normal level, the change in outdoor temperature and the accumulated cold over the last days.
- For the future hours: the weather (here the measured weather, used as a perfect forecast) and the calendar.

The sun and wind trend group added nothing in a test where each group was removed in turn, so it was dropped. The other four groups were kept. The model does not know which building it is looking at.

### 7.3 How the model was trained

- **Time-based, never random.** Training always uses the past and testing the future.
- **Ten rolling validation folds** of six months each (2017-03-01 to 2022-03-01), with an expanding training window, were used to compare methods and settings.
- **A test block** (2022-03-01 to 2023-10-22) was kept untouched and used **once** at the end.
- The final saved models are trained on all windows before 2022-03-01.
- Predicting the *difference* from "same hour yesterday" (the residual) worked better at 6 and 24 hours. At 1 hour, predicting the value directly was better in 10 of 10 folds.

Methods compared:

1. **Baselines.** "Same hour yesterday or last week" (seasonal naive) and, at 1 hour, "same as one hour ago" (persistence).
2. **LightGBM** (decision trees) on the inputs above. Tuning the settings gave less than 1 % improvement, so defaults were kept.
3. **GRU** (a recurrent neural network) reading the 168-hour history plus a small network for the future weather.
4. **Average of the two**, with equal weights. This is a simple average, not stacking.

Final rule: 1 hour = trees only; 6 and 24 hours = 50/50 average of trees and GRU.

### 7.4 Results on the test block

| Horizon | WAPE (error / heat) | Average error | Seasonal-naive WAPE | Better than naive by |
|---|---|---|---|---|
| 1 hour | 0.093 | 9.7 kWh per hour | 0.252 | 63 % |
| 6 hours | 0.127 | 13.3 kWh per hour | 0.252 | 50 % |
| 24 hours | 0.128 | 13.6 kWh per hour | 0.252 | 49 % |

- At 1 hour, against "same as one hour ago" (WAPE 0.130) the model is better by 29 %.
- Winter is predicted best (WAPE 0.074 to 0.102) and autumn worst (0.099 to 0.153).
- By building: 8116 is easiest (WAPE 0.064 to 0.097), 8107 is in the middle (0.128 to 0.161) and 8105 is hardest (0.146 to 0.194).
- Holidays and school breaks, and the Monday morning start-up, are the weakest points.

Figures: `results/final/figures/winter_week.png` (16 to 22 January 2023) and `holiday_week.png` (19 to 25 December 2022) show actual heat use against the 1 h and 24 h forecasts for each building.

### 7.5 What the results do and do not mean

- The weather used is the **measured** weather. A real weather forecast has errors, so with a real forecast the model will be somewhat worse. The scores are an upper bound.
- For a building the model has never seen, the error is larger (validation: 0.118 against 0.101 at 1 hour). Only three buildings were used.
- The GRU was tried with one setting and one seed and is not bit-for-bit repeatable. The saved models score within 0.4 percentage points of the test run for the 6 h and 24 h average.

### 7.6 Serving the model

The saved models (`models/ai_v1/`) have a SHA-256 checksum per file, which the forecast service checks at start-up. The service (port 8003) reads heat history from the replay feed up to the forecast hour and the coming weather, and returns forecasts for 1, 6 and 24 hours. An automated test confirms that changing the heat after the forecast hour does not change the forecast.

---

## 8. The digital twin

### 8.1 What it is

A simulation of **one 60 m² classroom** with a 3 kW radiator, a ventilation unit with a heating coil, a school-day schedule with 25 pupils, a window on the south wall, and a two-node heat model: a fast node for the room air (about 11 minutes) and a slow node for the walls (about 91 hours). The slow node stores heat and releases it later; this is what lets the room overshoot after the radiator is closed. The step is 60 seconds.

All room parameters are **assumed** values with a confidence label (`config/params.yaml`). Airflow per person and per m² come from sources [3] and the Swedish school guidance [1].

### 8.2 The controllers compared

| Controller | What it does |
|---|---|
| **Legacy** | Radiator on fixed timers plus a thermostat that reads the room temperature now. Ventilation heats incoming air to 21 °C all day and raises the flow by 50 % when the room is at 24 °C or above ("purge"). |
| **Forecast heating** | Asks the twin to preview the future. Starts pre-heating at the latest moment that still reaches 21 °C at the first lesson, and closes the valve early if sun or people will warm the room. |
| **Supply-temperature control** | Lowers the coil's target temperature when the room is warm: target = 21 °C − 2 K for each K above 21 °C, but not below 16 °C. |
| **Combined** | Forecast heating plus supply-temperature control. |

The forecast heating uses a perfect weather preview and a perfect room model, which is a best case.

### 8.3 Weather and how the twin uses the data

The twin runs on the real hourly weather of a selected Oslo building from the replay feed. Outdoor temperature is interpolated to the 60-second step. The sun on a horizontal surface is converted to the south wall with one fixed, assumed ratio of 1.5. The twin never reads the heat data.

### 8.4 Where the radiator and coil kWh come from

They are calculated by the twin, not measured. The radiator power is 3 kW times the valve opening times a factor for how much hotter the water is than the room; the coil power is air density times specific heat times airflow times the temperature lift to the target. The `metrics` code sums the power over time into kWh.

### 8.5 Results

**Base case (synthetic repeating weather, mean 2 °C, 5 school days):**

| | Heat | Peak room | Lesson minutes below 20 °C |
|---|---|---|---|
| Legacy | 169.9 kWh (about 90 % in the coil) | 25.45 °C | 71 |
| Forecast heating only | +2.6 % | 25.47 °C | 6 |
| Supply-temperature only | −22.3 % | 24.19 °C | 71 |
| **Combined** | **−21.1 %** | **24.19 °C** | **6** |

Supply-temperature control brings the saving and the lower peak; forecast heating brings the comfort at the cold start.

**Sensitivity (26 cases, one assumed value changed at a time).** The combined saving ranges from −2.4 % to +40.9 % and is positive in 25 of 26 cases. It is large when the legacy room overshoots a lot (mild weather, strong sun) and small when it barely overshoots. With external shading there is no overshoot and the combined controller costs 2.4 % more heat. It never raised the peak and never added cold lesson minutes.

**On real Oslo weather (building 8105, 5 school days, every second Monday):**

| Week from | Mean outdoor °C | Legacy kWh | Combined kWh | Combined vs legacy | Lesson min below 20 °C, legacy / combined |
|---|---|---|---|---|---|
| 2022-11-07 | 9.1 | 120.1 | 118.1 | −1.6 % | 104 / 6 |
| 2022-11-21 | 1.3 | 207.5 | 216.8 | +4.5 % | 139 / 18 |
| 2022-12-05 | −3.6 | 264.9 | 276.9 | +4.5 % | 270 / 19 |
| 2022-12-19 | 0.2 | 220.7 | 230.4 | +4.4 % | 160 / 19 |
| 2023-01-02 | −4.2 | 275.4 | 288.3 | +4.7 % | 395 / 20 |
| 2023-01-16 | 0.3 | 214.4 | 223.3 | +4.2 % | 139 / 18 |
| 2023-01-30 | −0.5 | 214.4 | 221.6 | +3.4 % | 123 / 16 |
| 2023-02-13 | 3.0 | 173.5 | 175.0 | +0.8 % | 98 / 14 |
| 2023-02-27 | 3.0 | 182.9 | 147.9 | **−19.2 %** | 85 / 12 |
| 2023-03-13 | 0.4 | 206.9 | 183.8 | **−11.2 %** | 118 / 17 |
| **Total of the ten weeks** | | **2,080.7** | **2,082.1** | **+0.1 %** | |

What it shows: in November to mid-February the simulated room never reaches the 24 °C purge limit, so there is no overshoot to remove, and the combined controller spends up to 4.7 % more heat on earlier pre-heating. It cuts cold lesson minutes from 100 to 400 per week to about 20. From late February the sun pushes the legacy room to 25 °C with 1,300 to 2,000 purge minutes, and the combined controller saves 11 to 19 %.

Walk-through of the week from 27 February 2023: the legacy radiator is nearly off from Wednesday, yet the room reaches 25.1 °C each day and the coil spends 33 to 38 kWh a day heating cold air to 21 °C. The combined controller pre-heats Monday earlier (19.4 °C at 07:50 against 18.1 °C), then lowers the coil target from Tuesday, using 24 to 27 kWh a day in the coil. The week total is 147.9 kWh against 182.9 kWh, the peak is 24.2 °C against 25.1 °C, and the minutes at or above the purge limit fall from 2,017 to 178.

### 8.6 Limits of the twin

- Perfect forecast and perfect model: a real controller will do less well.
- All room parameters are assumed, including the 16 °C minimum supply temperature, the gain of 2 K/K, the 60-minute look-ahead and the purge settings.
- Draught or discomfort from colder supply air is not modelled.
- One fixed sun ratio (1.5) for all months: the true ratio is higher in December and lower in March.
- No measured indoor temperature exists in the Oslo data, so the mechanism is shown, not a proven saving.

---

## 9. The dashboard

### 9.1 What it shows

The dashboard is a web page (port 8000) that plays the frozen Oslo window like a live feed.

| Element | What you see | Use |
|---|---|---|
| Replay controls | Play, Restart, speed, chart range | Moves through the data hour by hour |
| **Buildings table** | For each building: floor area, heat now (kW), last 24 h (kWh), last 24 h per m², outdoor temperature | Compare buildings on the same scale |
| **Heat chart** | Measured heat use of the selected building, plus an optional dashed **AI forecast** made 1, 6 or 24 hours before each hour | See how the forecast compares with reality |
| Outdoor chart | Outdoor temperature | Context |
| **Digital twin card** | Choose a Monday and 1 to 7 days, press "Run simulation". Shows a table of totals, the room-temperature chart and the heat-power chart for the legacy and combined controllers, plus the dashed AI benchmark scaled to 60 m² | See where better control would help |

The dashboard states clearly what is simulated (the twin card carries a warning), that the forecast uses the perfect weather, and that the AI benchmark is a rough reference and is not used by any controller.

### 9.2 How it works

The page talks to one server. The server forwards requests to the replay feed, the forecast service and the twin service, and holds no data. New data sources are added as new routes. A data-flow overview is in section 10.

---

## 10. How the components use the data

```
Oslo dataset (SINTEF, hourly, 2012-2023)
      |  ETL: clean, fill short gaps, drop bad rows        (etl/)
      v
silver / gold tables ------------------------------+
      |                                              |
      | freeze 2022-09-24 .. 2023-03-31              | training windows before 2022-03-01
      v                                              v
frozen window + checksum                       AI training (modeling/)
      |                                              |
      v                                              v
replay feed (:8001)  <---- history + weather ---- forecast service (:8003)  <-- saved models (models/ai_v1)
      |   \                                              |
      |    \-- weather only --> twin service (:8002)     |
      |                               |                  |
      +-------------------------------+------------------+
                                      v
                              dashboard (:8000)
```

- The **AI model** learns from the cleaned data before March 2022 and serves forecasts for the replay window.
- The **twin** takes only the weather from the feed; it never sees heat data.
- The **forecast service** takes heat history up to the forecast hour and the next hours' weather.
- The **dashboard** reads the feed (measured heat, weather), the forecast service (AI forecasts) and the twin service (simulations).
- Each part runs as its own program with its own tests and Docker image, and all of them start together with `docker compose up`.

---

## 11. Testing and verification

| Test | Result |
|---|---|
| Automated tests | Root 63, forecast service 9, twin service 6, dashboard 12: all pass |
| No leakage | Changing heat use after the forecast hour does not change the forecast |
| Saved models against the test run | Trees reproduce the test-run predictions exactly (0.00 Wh). The GRU is not bit-reproducible; the saved 50/50 averages score WAPE 0.1276 and 0.1242 at 6 h and 24 h against 0.1270 and 0.1278 in the test run. Both sets of scores are in the manifest. |
| Serving against training | The service path matches the training path for the same GRU within 0.04 Wh |
| End to end on the replay | Error through the service is close to the test run (for example building 8105 at 1 h: WAPE 0.129 against 0.128) |
| Docker | The image builds and returns the same numbers as the local service |
| Dashboard | **[Looked over in a browser by the project lead and judged fine; add screenshots.]** |

---

## 12. Expected heat reduction and cost

### 12.1 What we can and cannot say

The simulation covers heating and ventilation of one classroom on school days. It does not cover hot water, weekends, holidays or the rest of the building. The AI model forecasts demand and does not reduce heat itself; the reduction comes from the control tested in the twin, and the forecast helps to see and plan it.

| Evidence | Heat reduction | Where it applies |
|---|---|---|
| Base case in simulation | 21 % | Weeks with a lot of overshoot |
| Sensitivity (26 cases) | −2.4 % to +40.9 %, positive in 25 of 26 | Depends on sun, wall mass, shading, ventilation |
| Real Oslo weather, late February and mid-March | 19 % and 11 % (35.0 and 23.1 kWh per classroom per week) | Sunny late-winter weeks |
| Real Oslo weather, November to mid-February | −1.6 % to +4.7 % (mostly more heat, fewer cold lessons) | Cold, dark weeks |
| **Ten sampled weeks, November to March** | **0 % (+0.1 %)** | Roughly the heating season |
| Literature: operations optimization in schools | 10 to 30 % | Reported by [1], not our result |

### 12.2 Our estimate

For the classroom's heating and ventilation, we expect a saving **between 0 % and about 20 %**, depending on how many weeks have enough sun and people to cause overshoot. It is largest in spring and autumn (the "shoulder" weeks) and near zero in mid-winter. This is consistent with the lower half of the 10 to 30 % reported in the literature [1], but it is not a measured result.

We cannot give an annual percentage. The Oslo window ends on 31 March, so April to May and autumn were not simulated, and a Trollhättan weather file has not been run **[optional next step]**. The saving of a real building may also differ, since all room parameters are assumed.

### 12.3 Cost equivalent

```
saving in SEK = saved heat (kWh) × variable district-heating price (SEK per kWh)
```

**Price used.** From our early background check on district-heating cost (`report/investigate-on-cost.md`) we use the variable energy charge of **1.10 to 1.35 SEK per kWh** (1,100 to 1,350 SEK per MWh). The fixed annual grid fee (1,500 to 4,500 SEK a year in that note) does not change with the amount of heat used, so it is not part of the saving.

This price is for orientation only. The background note gives no source or year, its figures are for homes and not for municipal buildings, and its seasonal example (about 0.09 USD per kWh in winter) is lower than its own range. **[Confirm the real price and tariff with Kraftstaden before submission.]**

**Per classroom, from the simulation (real Oslo weather, 5 school days):**

| Case | Heat change | At 1.10 SEK/kWh | At 1.35 SEK/kWh |
|---|---|---|---|
| Sunny week from 27 February | −35.0 kWh (−19.2 %) | 38.5 SEK saved | 47.3 SEK saved |
| Sunny week from 13 March | −23.1 kWh (−11.2 %) | 25.4 SEK saved | 31.2 SEK saved |
| Cold mid-winter week, worst case (from 2 January) | +12.9 kWh (+4.7 %) | 14.2 SEK extra | 17.4 SEK extra |
| Ten sampled weeks, net | +1.4 kWh (+0.1 %) | 1.5 SEK extra | 1.9 SEK extra |
| For comparison: legacy heat in the ten weeks | 2,080.7 kWh | 2,289 SEK | 2,809 SEK |

So for one classroom, a sunny overshoot week is worth about 25 to 47 SEK, and the ten sampled weeks together are worth about nothing. These are small amounts per room; any real value comes from many rooms and from the weeks in spring and autumn that the replay window does not cover.

**Per building, as a sensitivity (not a result).** We did not simulate whole buildings, so we cannot say what percentage a school would save. What we can say is what **each 1 % reduction** of a building's heat is worth. The yearly heat of the three Oslo schools, from October 2022 to September 2023, is below (space heating plus hot water; it is a little low because 2 to 5 % of the hours are missing in the cleaned data).

| Building | Floor area | Heat, Oct 2022 to Sep 2023 | Per m² | Value of 1 % at 1.10 SEK/kWh | at 1.35 SEK/kWh |
|---|---|---|---|---|---|
| 8105 | 8,415 m² | 642 MWh | 76 kWh/m² | 7,060 SEK | 8,670 SEK |
| 8107 | 6,063 m² | 551 MWh | 91 kWh/m² | 6,060 SEK | 7,440 SEK |
| 8116 | 13,408 m² | 1,164 MWh | 87 kWh/m² | 12,800 SEK | 15,710 SEK |

Our estimate of 0 to about 20 % applies to one classroom's heating and ventilation on school days, so it cannot be applied directly to these building totals (they include hot water, corridors, offices and weekends). As a rough reading, if the saving reached the building level at even 5 %, the value would be 5 times the figures above, about 30,000 to 80,000 SEK a year for a school of this size; this is an arithmetic example and not a forecast.

To scale to the portfolio, multiply by the number of comparable schools or classrooms **[to be provided by Kraftstaden]**.

**Investment cost: a gap in this study.** We did not estimate the investment cost, and we do not give a payback time. The cost depends on facts that only the client can supply and that we could not reach: which building-management system and controls the schools have, whether the valves and ventilation units can be controlled from outside, how many sensors and which gateway are needed, who does the installation, and what the client pays for integration work. Without these, any figure would be a guess. The proposal lists "investment costs" as one of the points to assess, so this is a limit of the pre-study and is named as such in section 13.

What a follow-up would need to provide: an inventory of the control systems in one or two pilot schools, quotes for cheap sensors and a gateway, and an estimate of the hours for integration. With that and the price of heat above, a simple payback time can be calculated.

---

## 13. Limitations and risks

1. **No real building.** All room parameters are assumed; the overshoot and the saving are demonstrated in simulation only.
2. **No indoor temperature in the Oslo data**, so the twin cannot be calibrated or the saving validated.
3. **Perfect weather.** The AI scores and the controller's preview use measured weather. A real forecast adds error.
4. **Three buildings.** The AI model is less accurate on an unseen building, and the unseen-building test was not run on the test block for the GRU.
5. **What `HtTot` contains.** It includes hot water. We have checked this for one sample building and from the dataset notes, not for each of the three buildings. The AI benchmark in the dashboard is therefore a rough reference.
6. **Benchmark gap.** The scaled AI benchmark is about 48 to 66 % of the simulated classroom's heat. Expected reasons are the south window, the missing hot water in the room, and assumed parameters, but this is not proven.
7. **Data gaps** in building 8107 and in September 2019 and 2021; the school-break rule is approximate.
8. **Training variation.** The GRU is not bit-for-bit repeatable and was tried with one setting and one seed.
9. **Investment cost not estimated.** We could not reach the client for the facts it needs, so the pre-study gives expected savings but no payback time (section 12.3).
10. **Integration complexity.** Real buildings need access to the valve and ventilation controls, which older systems often lack.

---

## 14. Conclusions and reflection

**What did we find?**

- **Q1 (forecasting).** Yes: with past heat, weather and calendar, a building's heat use can be forecast with an error of about 9 % (1 h) to 13 % (6 and 24 h), half to two thirds better than a simple guess. With a real weather forecast it will be somewhat worse.
- **Q2 (control).** In simulation, room-compensated supply-air temperature and forecast pre-heating reduce heat by up to about 20 % in sunny weeks and cut cold lessons, but give no net saving in cold winter weeks.
- **Q3 (overview).** The dashboard brings the buildings, the forecast and the twin result together. It shows when a building's heat use deviates from what is expected and where better control would pay off.

**Is it feasible?** Technically yes: the parts work together and run on open-source tools and public data. Economically the answer is open. The size of the saving, and therefore the payback, depends on the weeks with overshoot, which we could show only in simulation.

**What did we learn?**

- A simple, honest baseline matters. Persistence beats seasonal naive at 1 hour, and the gain of the model is smaller against the stronger baseline.
- More complex models did not automatically help. Tuning gave under 1 %. The GRU alone was worse than the trees, and only the average helped, and only at 6 and 24 hours.
- A saving that appears in a base case can vanish in another season. The weekly table is more informative than one headline number.
- Data limits (no indoor temperature) decide what can be claimed.

**What the client should do next**

1. Provide indoor temperature, valve position, supply and return temperature and the ventilation timer for one room or building, even for a few weeks. This allows calibration of the wall and infiltration parameters and a test of the overshoot claim.
2. Provide the real district-heating price and tariff, a count of comparable classrooms, and the facts needed for an investment cost (control systems in a pilot school, sensors, gateway, installation and integration work). Without them no payback time can be stated.
3. Run the twin on Trollhättan weather for a whole year, including spring and autumn.
4. Repeat the AI test with a real weather forecast.
5. Install cheap sensors in one pilot school and run the supply-temperature control as a trial.

---

## Appendix A. Where things are in the repository

| Item | Location |
|---|---|
| Data cleaning (ETL) | `etl/` |
| AI models, results, saved models | `modeling/`, `results/`, `models/ai_v1/` |
| Forecast service | `forecast_service/` |
| Digital twin and scenarios | `twin/`, `scenarios/`, `config/params.yaml` |
| Twin service | `twin_service/` |
| Replay feed and frozen data | `feed/`, `frozen/` |
| Dashboard | `dashboard/` |
| Decision log | `notebooks/quality_inspect_decision.md` |
| Twin plots | `out/overshoot.png`, `out/combined_comparison.png`, `out/sensitivity.png` |
| AI plots | `results/final/figures/winter_week.png`, `holiday_week.png` |

## References

References are in `references.bib`. The ones used in this draft:

- [1] A. Persson, M. Bratt and S. Ekelin, *Vägen till energieffektiva skolor*, Sveriges Kommuner och Landsting, 2011.
- [2] M. Jangsten, J. Kensby, J.-O. Dalenbäck and A. Trüschel, "Survey of radiator temperatures in buildings supplied by district heating," *Energy*, vol. 137, pp. 292–301, 2017.
- [3] R. Larsson and S. Olsson, "Improved indoor environment and ventilation in schools. A case study in Växjö, Sweden," 13th AIVC Conference, 1992.
- [4] B. Simanic, "Energy use in low-energy schools," Lund University (LTH), SBUF project 13290, 2020.
- Lien et al., 2025, *Data in Brief* 63, 112288 (COFACTOR-SBHUB Oslo dataset, DOI 10.60609/2hvr-wc82).
