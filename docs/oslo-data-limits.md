# What the Oslo data can and cannot do for the heat model

The frozen Oslo window (`frozen/`) is the common data source of the three parts. This note says what it is good for in the digital twin and what it is not. The room model (`twin/room_model.py`) is physics-based with assumed parameters; it is not fitted to this data.

## The mismatch

| Aspect | Oslo data (buildings 8105, 8107, 8116) | Room model |
|---|---|---|
| Object | Whole schools: 8,415 m² (built 2011), 6,063 m² (1982), 13,408 m² (1959) | One 60 m² classroom |
| Heat signal | `HtTot` = space heating + hot water, hourly, one number per building | Radiator kW and ventilation coil kW, 60 s, separate |
| Ventilation | Not separated from the total | Modelled explicitly (the coil is most of the heat in the scenarios) |
| Indoor temperature | None | The main output |
| Occupancy, valve, supply temperature | None | Inputs and controller actions |
| Sun | `SolGlob`, on a **horizontal** surface | Needs sun on the **south facade** |
| Step | Hourly | 60 s |

Consequences:

1. The room temperature, and so the overshoot itself, cannot be checked against this data.
2. `HtTot` cannot be split into radiator, ventilation and hot water, so the "paying twice" part is not visible in it.
3. Sun on a horizontal surface has to be converted for the south window. The twin uses one fixed, assumed ratio (`solar.horizontal_to_south_facade_ratio` in `config/params.yaml`, default 1.5). Low winter sun gives a higher true ratio than autumn or spring, so one number is crude.
4. A whole school is many rooms, orientations, a boiler and pumps in one number; it is not one classroom.

## What each use is worth

| Use of the Oslo data | Viable? |
|---|---|
| Real weather to drive the twin (`twin/feed_weather.py`, `twin_service/`) | Yes, with the sun conversion above |
| Train the AI model on heat load | Yes (`modeling/`) |
| Order-of-magnitude check of energy per m² | Yes, but not a validation |
| Calibrate wall U-value, thermal mass, infiltration | No: no indoor temperature, no heat split |
| Show that the overshoot exists in real buildings | No: needs indoor temperature or valve and supply logs |
| Prove the saving | No |

## Order-of-magnitude check (not a validation)

Average heat per m² over the Oslo window (Oct to Mar, including hot water) is about 15 to 16 W/m² for the three buildings. The simulated classroom in the cold test week (5 days, mean 2 °C) uses about 24 W/m². Same order of magnitude; not the same quantity (different weather period, hot water included in Oslo, whole building against one room).

## Clock

The data is on a fixed UTC+1 clock all year. The twin reads its schedule on that same clock, so before 30 October (Norwegian summer time) the school day sits one hour earlier than the wall clock. The twin service defaults to a start after that date.

## What would make it a real validation

Indoor temperature, valve position, supply and return temperatures and the ventilation timer for one room or building from the client (Kraftstaden), even a few weeks. With that, the wall U-value and infiltration can be fitted and the overshoot claim tested.

## Wording for the report

"The model is physics-based and uses assumed parameters. Oslo data supplies real weather and a heat-per-m² plausibility check but contains no indoor temperature, so the overshoot and the saving are demonstrated in simulation only. Validation requires indoor temperature and plant data from the client."
