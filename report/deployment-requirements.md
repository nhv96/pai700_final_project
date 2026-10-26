# Requirements for installing the combined controller in a real building

This is a general list of what a real school would need before the combined controller (forecast heating plus supply-air temperature control) could run outside the simulation. It is based on what the controller reads, what it commands, and which parts of the twin are still assumed. See `docs/controllers-and-scenario.md` for the controller design and the modelled results.

## What the controller is made of

1. **Forecast heating** (`twin/predictive_controller.py`). Decides the radiator valve every 5 minutes.
   - *Optimal start:* heats as late as possible and still reaches 21 °C at the first lesson.
   - *Look-ahead thermostat:* during the day, opens the valve according to where the room will be in 60 minutes, not where it is now.
2. **Supply-temperature control** (`twin/supply_controller.py`). Lowers the target temperature of the ventilation heating coil when the room is warm: `target = 21 − 2 × (T_room − 21)`, kept between 16 and 21 °C.
3. **Preview of the future** (`DigitalTwin.preview`). A copy of the room model plus a weather forecast. The forecast part asks it "what happens if I do this?" before it acts.

Inputs: room air temperature, outdoor temperature, number of occupants.
Outputs: radiator valve command, radiator supply temperature, ventilation on/off, coil target temperature.

## Requirements

### 1. Sensors and data
- A room air temperature sensor in each controlled room. Both controller layers depend on it.
- An outdoor temperature measurement (sensor or weather feed).
- Occupancy information: the school timetable, or presence or CO₂ sensors.
- Solar data for the building's facades, because sun is a main cause of overheating.
- A heat meter (or equivalent) to measure energy use, so that savings can be checked.

### 2. Actuators the controller can command
- **Ventilation coil setpoint.** The air-handling unit must accept an external supply-air temperature setpoint, down to about 16 °C. Most of the saving comes from here (about 90 % of heat in the legacy simulation is in the coil). If the unit's setpoint is fixed, the supply-temperature part cannot work.
- **Radiator valve or zone control.** The controller must be allowed to open and close the room's valve and to override the existing timers.
- The existing timers and thermostat settings must be kept, so the legacy behaviour is available as a fallback.

### 3. A calibrated room model
- The simulation uses assumed parameters (wall U-value, thermal mass, infiltration, window and sun gain, radiator power). These must be identified from measured data for each room or room type.
- The forecast layer is only as good as this model. A wrong model gives wrong pre-heat times.

### 4. A real weather forecast
- The simulation uses a perfect forecast. A real installation needs a forecast service for temperature and sun over the next several hours, and the controller must cope with forecast errors.
- The saving figures in the report are therefore a best case.

### 5. Integration with the building
- A link to the building management system (for example BACnet or Modbus) to read sensors and write setpoints.
- A runtime that runs the control loop every 5 minutes, with logging of inputs, decisions and results.

### 6. Safety and fallback
- If a sensor fails, data is missing, or the forecast is unavailable, the system must return to the legacy controller.
- The 16 °C minimum supply temperature and the limits on valve and coil must be hard limits that nothing can override.
- Staff must be able to switch the controller off and see what it is doing.

### 7. Validation before trust
- Compare measured room temperatures with the model's.
- Run in shadow mode first: compute decisions but do not apply them.
- Pilot in one room or one air-handling zone, with a comparable room as a reference.
- Check comfort, including draught from colder supply air, which the simulation does not model.
- Confirm the saving with measured energy data.

## Known limits that affect a real installation

- **The saving depends on overshoot.** In mid-winter on Oslo weather the room never overheated, and the combined controller used 1–5 % more heat (while greatly reducing cold lesson minutes). The saving of 11–19 % appeared only from late February.
- **One air-handling unit often serves several rooms.** A single supply-temperature setpoint is then a compromise between rooms. The simulation models one room only.
- **No real indoor temperatures exist** in the Oslo dataset, so the results show the mechanism, not a proven saving in a real building.
- The AI heat-load forecast in this project is a benchmark only. The controller does not use it, so it is not needed for an installation.
