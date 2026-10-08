

## System in Action (Click the Image)
[![Watch the video](pngs/screen.png)](https://www.youtube.com/watch?v=5jvwHJAcYsU&ab_channel=No_Name)


## System Connections Diagram

![System Connections](pngs/connections_resized.png)

> The Modbus role labels inside this image ("Modbus Slave" on the backend, "Master:502" on the PLC, "Master:503" on the physical model) do not match the code. The arrows and ports are right; for the real client/server roles use the [topology tables](#communication-topology) below. The image has not been regenerated.

# HVAC PLC Simulation

This project simulates a Heating, Ventilation, and Air Conditioning (HVAC) control loop using a PLC-style architecture: a Python "PLC" that parses and runs a small Structured Text (ST) program, a Python thermal model standing in for the room and its sensors/actuators, a FastAPI backend that acts as the operator interface to the PLC, and a static web frontend. Everything is orchestrated with Docker Compose.

> **This is a software simulation.** There is no vendor PLC hardware, no IEC 61131-3 toolchain and no real fieldbus device involved. See [Limitations](#limitations).

## Project Structure

```
docker-compose.yml
README.md
backend/
    app.py
    Dockerfile
    modbus_client.py
    models.py
    requirements.txt
    core/
        __init__.py
        config.py
        dependencies.py
    routes/
        __init__.py
        health.py
        status.py
        system.py
        weather.py
frontend/
    Dockerfile
    nginx.conf
    package.json
    src/
        app.js
        index.html
        style.css
physical-model/
    __init__.py
    Dockerfile
    physical_simulation.py
    requirements.txt
    thermal_model.py
plc/
    Dockerfile
    entrypoint.sh
    main.py
    modbus_interface.py
    plc_runtime.py
    requirements.txt
    st_parser.py
    programs/
        hvac_control.st
pngs/
    connections_resized.png
    screen.png
```

## Components

### 1. Backend
- **Framework:** Python (FastAPI)
- **Purpose:** HTTP API for the frontend. Translates operator commands into Modbus writes to the PLC, reads PLC status registers, and forwards simulated weather to the physical model over HTTP.
- **Key Files:**
  - `app.py`: Main FastAPI application. On startup it connects to the PLC (up to 20 attempts, 3 s apart) and writes the default setpoints.
  - `modbus_client.py`: Modbus TCP client used to talk to the PLC.
  - `models.py`: Pydantic models for the API.
  - `core/`: Configuration (env vars, register addresses, defaults) and shared state.
  - `routes/`: API endpoints for health, status, system control, and weather.
- **Dockerized:** Yes (`backend/Dockerfile`)

### 2. Frontend
- **Framework:** HTML/CSS/JavaScript (single page, served by Nginx)
- **Purpose:** Operator UI. Shows status and lets the user start/stop the system, change setpoints, and change the simulated outside weather.
- **Key Files:** `src/app.js`, `src/index.html`, `src/style.css`, `nginx.conf`
- **Dockerized:** Yes (`frontend/Dockerfile`)
- The browser calls the backend directly at the hard-coded `http://localhost:8000` (`API_URL` in `src/app.js`); Nginx only serves static files. The `REACT_APP_API_URL` variable in `docker-compose.yml` is not read by any code in `frontend/`.

### 3. Physical Model
- **Framework:** Python (Flask + pymodbus + numpy)
- **Purpose:** Plays the role of the plant: a thermal model of one room plus its temperature/humidity sensors and fan/chiller actuators, exposed to the PLC as a Modbus server.
- **Key Files:** `physical_simulation.py` (Modbus server, Flask API, simulation loop), `thermal_model.py` (the model)
- **Dockerized:** Yes (`physical-model/Dockerfile`)

### 4. PLC
- **Framework:** Python (pymodbus + lark)
- **Purpose:** Parses an ST program, executes it in a 100 ms scan loop, talks to the plant over Modbus as a client, and exposes a Modbus server for the backend.
- **Key Files:** `main.py` (scan loop), `modbus_interface.py` (server + client), `plc_runtime.py` (interpreter), `st_parser.py` (lark grammar), `programs/hvac_control.st`
- **Dockerized:** Yes (`plc/Dockerfile`)

## Communication Topology

A Modbus **server** (slave) listens on a port and holds registers; a Modbus **client** (master) opens the connection and initiates every read/write. The tables below are derived from the code; "host" is the Docker Compose service name.

### (a) Control-relevant links

These carry what a real installation would also have: operator commands/setpoints and the PLC's sensor/actuator I/O.

| # | Protocol | Client / master (initiates) | Server / slave (listens) | Host : port | What flows |
|---|---|---|---|---|---|
| A1 | HTTP | Browser (frontend JS) | Backend (FastAPI) | `localhost:8000` (published by Compose) | `POST /api/control` (start/stop, temperature/humidity setpoint), `GET /api/status` polled every 2 s |
| A2 | Modbus TCP | Backend (`ModbusClient`) | PLC (`ModbusInterface` server, holding registers) | `plc:502` | Writes commands/setpoints to 40001–40005; reads status 40101–40106 |
| A3 | Modbus TCP | PLC (`ModbusInterface` client) | Physical model (pymodbus server) | `physical-model:503` | Every scan: reads sensors 40201–40202; writes actuator commands 40301–40302 |

The static files for the frontend are served by Nginx (container port 80, published as host port 3000); that is not a control link.

### (b) Simulation-only links

These exist only because the plant is simulated. In a real plant, outside conditions would be physical conditions, not data pushed in by software.

| # | Protocol | Client | Server | Host : port | What flows |
|---|---|---|---|---|---|
| B1 | HTTP | Browser (frontend JS) | Backend | `localhost:8000` | `POST /api/weather` with the outside temperature/humidity typed into the GUI |
| B2 | HTTP | Backend | Physical model (Flask) | `physical-model:8001` | `POST /api/weather` (forward of B1) |
| B3 | HTTP | Backend | Physical model (Flask) | `physical-model:8001` | `GET /api/status` (backend reads back `outside_temperature` / `outside_humidity` for the GUI); `GET /health` (used by the backend health check) |
| B4 | in-process | Physical-model loop | Physical-model thermal model | same process | The loop copies the stored weather into the thermal model every second |

Nothing in the PLC, the ST program, or any Modbus register carries outside weather.

### How the outside temperature travels

Traced through the code:

1. **GUI:** the user enters a value in the `weather-temp` field (`frontend/src/index.html`) and clicks update. `updateWeatherConditions()` in `frontend/src/app.js` sends `POST http://localhost:8000/api/weather` with JSON `{temperature, humidity}`.
2. **Backend:** `backend/routes/weather.py` validates it against `WeatherConditions` (`models.py`: temperature −20…50, humidity 0…100) and forwards the same JSON with `httpx` to `PHYSICAL_MODEL_URL + "/api/weather"` (default `http://physical-model:8001`). The backend does not store it and does not write it to Modbus.
3. **Physical model, REST:** `set_weather()` in `physical-model/physical_simulation.py` validates it again (same ranges) and stores it in the global `weather_conditions` dict.
4. **Physical model, loop:** `update_modbus_data()` runs about once per second and calls `thermal_model.set_outside_conditions(...)` with that dict before each `thermal_model.step(1.0)`. The outside temperature is therefore used directly by the wall-conduction and ventilation terms of the thermal model.
5. **Readback for display:** the frontend polls `GET /api/status` on the backend every 2 s; the backend calls `GET physical-model:8001/api/status` and copies `outside_temperature` / `outside_humidity` into its response.

The PLC never receives the outside temperature. It sees its effect only indirectly, through the room temperature/humidity sensor registers (40201/40202).

## Register Map

All registers are 16-bit **holding registers** (function codes 3/6/16). Addresses are written in the 4xxxx convention used by the code; the address on the wire is `address − 40001` (e.g. 40001 → 0, 40101 → 100). Both servers are created with `zero_mode=True` and a single slave context (`single=True`).

### PLC server (`plc:502`) — backend ↔ PLC (link A2)

| Address | Name | Direction | Data type | Unit | Scaling |
|---|---|---|---|---|---|
| 40001 | SystemEnable | backend → PLC | BOOL as uint16 | – | 0 = off, 1 = on (PLC treats any non-zero as on) |
| 40002 | SetpointTemp | backend → PLC | uint16 | °C | ×10 (220 = 22.0). Backend sends `int(value × 10)`, PLC divides by 10 |
| 40003 | SetpointHumidity | backend → PLC | uint16 | % | ×10 (450 = 45.0) |
| 40004 | TempDeadband | backend → PLC | uint16 | °C | ×10 |
| 40005 | HumidityDeadband | backend → PLC | uint16 | % | ×10 |
| 40101 | RoomTemperature | PLC → backend | uint16 | °C | ×10; copy of the sensor value (`int(temp × 10)`) |
| 40102 | RoomHumidity | PLC → backend | uint16 | % | ×10 |
| 40103 | FanSpeed | PLC → backend | uint16 | % | 1:1, 0–100 (`int()` of the ST output) |
| 40104 | ChillerOn | PLC → backend | BOOL as uint16 | – | 0/1 |
| 40105 | SystemStatus | PLC → backend | uint16 | – | 0 = Off, 1 = Cooling, 2 = Idle |
| 40106 | AlarmActive | PLC → backend | BOOL as uint16 | – | 0/1 |

The PLC pre-loads the setpoint/deadband registers with 22.0 °C, 45.0 %, 1.0 °C, 5.0 %. At startup the backend then overwrites them with its own defaults: 22.0 °C, **50.0 %**, 1.0 °C, 5.0 % (`backend/core/config.py`).

### Physical-model server (`physical-model:503`) — PLC ↔ plant (link A3)

| Address | Name | Direction | Data type | Unit | Scaling |
|---|---|---|---|---|---|
| 40201 | SensorTemp | plant → PLC | uint16 | °C | ×10. Written by the model loop as `int(temp × 10)` after clamping to 10–50 °C |
| 40202 | SensorHumidity | plant → PLC | uint16 | % | ×10, clamped to 20–90 % |
| 40301 | ActuatorFanSpeed | PLC → plant | uint16 | % | 1:1, 0–100 (clamped to 0–100 by the model) |
| 40302 | ActuatorChiller | PLC → plant | BOOL as uint16 | – | 0/1 |

The PLC reads 40201–40202 with one request (2 registers) and writes 40301–40302 with one request. Both requests use unit id 1.

The PLC's own server datastore also defines addresses 40201–40302 in its register map, but those are used only as the *addresses* for the physical-model client; the PLC server never populates them for anyone.

## PLC Scan Cycle

`PLCSimulator.run_cycle()` in `plc/main.py` repeats the following, targeting a **100 ms** cycle (`asyncio.sleep` for the remainder; a warning is logged if a cycle overruns):

1. **Read inputs** — `read_inputs()`: Modbus read of 40201–40202 from the physical model; values are divided by 10 and stored as the ST inputs `RoomTemperature` / `RoomHumidity` (also copied into the PLC's own 40101/40102). If the read fails, the previous values are kept.
2. **Run the ST program** — `PLCRuntime.execute_cycle()` executes the top-level statements of `hvac_control.st` once, top to bottom, against the in-memory input/output/internal variables.
3. **Write outputs** — `write_outputs()`: writes `FanSpeed` and `ChillerOn` (as 40301–40302) to the physical model.
4. **Update server registers** — `update_server_registers()`: *reads* the backend's command registers (40001–40005) from the PLC's own datastore into the ST inputs `SystemEnable`, `SetpointTemp`, `SetpointHumidity`, `TempDeadband`, `HumidityDeadband`, then *writes* `FanSpeed`, `ChillerOn`, `SystemStatus`, `AlarmActive` to 40103–40106.

Consequence: because command registers are sampled in step 4, a command written by the backend takes effect in the ST program on the **next** scan (≈ one scan of latency). Sensor values and outputs are not double-buffered beyond that; this is a software loop on an asyncio event loop, not a deterministic real-time scan.

The physical model is not synchronised to the PLC scan: its loop runs about once per second (see below) and the PLC simply reads whatever is currently in the registers.

### What `hvac_control.st` does

`plc/programs/hvac_control.st` (program `HVAC_Control`) is **deadband threshold control**, not hysteresis with memory, not PID, and not a state machine:

- If `SystemEnable` is false: `FanSpeed := 0`, `ChillerOn := FALSE`, `SystemStatus := 0`, `AlarmActive := FALSE`.
- Otherwise:
  - `TempError := RoomTemperature − SetpointTemp`, `HumidityError := RoomHumidity − SetpointHumidity`.
  - `CoolingRequired` = `TempError > TempDeadband`. `DehumidRequired` = `HumidityError > HumidityDeadband` and not cooling.
  - **Cooling:** `ChillerOn := TRUE`, `SystemStatus := 1`, `FanSpeed := 30 + 20·TempError`, limited to 30–100.
  - **Dehumidification:** `ChillerOn := TRUE`, `SystemStatus := 1`, `FanSpeed := 50`.
  - **Otherwise (idle):** `ChillerOn := FALSE`, `SystemStatus := 2`, `FanSpeed := 20`.
  - **Alarm:** `AlarmActive := TRUE` if `RoomTemperature > 35` or `< 10`, or `RoomHumidity > 80` or `< 20`; otherwise FALSE. (Evaluated only while enabled; limits are hard-coded.)

The decision is recomputed from scratch every scan from the current inputs, so the chiller turns off again as soon as `TempError` is no longer above the deadband; there is no separate lower switch-off threshold. `TempLow` is computed but never used. The program has no integral or derivative terms and no stored state beyond the output variables themselves.

If the ST file is missing or fails to parse, `PLCRuntime` falls back to `_execute_default_logic()` in `plc_runtime.py`, a hard-coded Python version of similar logic (no alarm output; dehumidification is not mutually exclusive with cooling).

### ST features supported by `st_parser.py`

Defined by the lark grammar `ST_GRAMMAR` and executed by `plc_runtime.py`:

- Structure: `PROGRAM name … END_PROGRAM`; `VAR`, `VAR_INPUT`, `VAR_OUTPUT` blocks.
- Types: `BOOL`, `INT`, `REAL`, `TIME` (declaration only; there are no time literals). Initial values must be a number, `TRUE` or `FALSE`. All numbers are parsed as Python floats and the runtime does not enforce types (an `INT` variable can hold a float).
- Statements: assignment `:=`; `IF … THEN … ELSIF … ELSE … END_IF;`; function-call statements (parsed, but the runtime only logs them — there are no built-in functions or function blocks).
- Expressions: `+ − * /` (division by zero yields 0), comparisons `> < >= <= = <>`, `AND`, `OR`, `NOT`, unary `−`, parentheses, `TRUE`/`FALSE`.
- Comments: `// …` only.
- Parser quirk: `NOT` is parsed at the unary level, so it binds tighter than a comparison (`NOT a > b` is `(NOT a) > b`), unlike IEC 61131-3.

Not in the grammar: `CASE`, `FOR`, `WHILE`, `REPEAT`, `EXIT`, `RETURN`, `XOR`, `MOD`, `**`, `(* … *)` comments, `VAR_IN_OUT`/`VAR_GLOBAL`/`CONSTANT`, other data types (`SINT`, `DINT`, `STRING`, arrays, structs …), `FUNCTION`/`FUNCTION_BLOCK`, timers, counters, PID blocks, direct addresses (`%IX0.0`). Keywords are uppercase literals in the grammar. Assigning to an input variable is ignored with a warning.

## Physical Model

`physical-model/thermal_model.py` is a single-zone, lumped-air-mass model integrated with an explicit Euler step. `physical_simulation.py` calls `thermal_model.step(1.0)` — a **fixed time step of 1.0 s** — once per loop iteration, followed by `asyncio.sleep(1)`. The step size is a constant and does not measure real elapsed time, so simulated time runs at roughly (a little slower than) wall-clock time.

Each step computes, for temperature and humidity:

- **Wall conduction:** `(T_out − T_room) / R · dt`, with `R = wall_thickness / (k · wall_area)`; room 10 m² × 2 m high, 0.1 m wall, k = 1.7 W/(m·K), wall area `4·√10·2` m². The heat is turned into a temperature change by dividing by the air's thermal mass `V·ρ·cp` (ρ = 1.225 kg/m³, cp = 1005 J/(kg·K)).
- **Ventilation (fan):** air exchange with the outside, `flow = 0.1 m³/s × fan%`; `ΔT = (ṁ / m_air)·(T_out − T_room)·dt`; humidity moves toward outside humidity the same way, ×0.5.
- **Chiller (when on):** a fixed `−20 000 W · dt / thermal mass` temperature change and `−0.02 %/s` humidity — the chiller is on/off at full capacity; the fan only affects outside-air exchange.
- **Internal gains:** constant +100 W and +0.001 %/s humidity.
- Humidity is clamped to 20–90 % inside the model. Temperature is *not* clamped in the model; `physical_simulation.py` only clamps the value it *publishes* to 40201 (10–50 °C).

Initial state set by `physical_simulation.py`: room 22.0 °C / 50 %, outside 25 °C / 60 % (until changed via the weather API). Temperature and humidity are independent quantities (no psychrometric coupling). `get_energy_consumption()` exists but nothing calls it.

The physical model also exposes `GET /health`, `GET /api/status` and `POST /api/weather` on port 8001 (Flask, not published to the host by default).

## Running the Project

### Prerequisites
- Docker and Docker Compose installed.

### Quick Start
1. Clone the repository.
2. Run the following command in the project root:
   ```bash
   docker-compose up --build
   ```
3. Access the frontend at [http://localhost:3000](http://localhost:3000). The backend API is published on [http://localhost:8000](http://localhost:8000) (the frontend calls it from the browser, so this port must be reachable).

Only `frontend` (3000→80) and `backend` (8000) publish ports. The PLC (502) and physical model (503, 8001) are reachable only on the Compose network `hvac-network`.

### Stopping the Project
```bash
docker-compose down
```

## API Endpoints (Backend)
- `POST /api/control`: body `{"command": "start"|"stop"|"set_temperature"|"set_humidity", "value": <number>}`.
- `POST /api/weather`: body `{"temperature": …, "humidity": …}` — simulation-only (see above).
- `GET /api/status`: room temperature/humidity, fan speed and chiller state (read from the PLC), outside conditions (from the physical model), and the setpoints and `plc_running` flag (held in backend memory, not read back from the PLC).
- `GET /api/health`: checks the PLC Modbus connection and the physical model's `/health`.
- `GET /`: trivial status message.

`SystemStatus` (40105) and `AlarmActive` (40106) are read by the backend's Modbus layer but are not returned by `GET /api/status`.

## Frontend Features
- Status polling every 2 s (room/outside temperature and humidity, fan speed, chiller status, setpoints).
- Start/stop, temperature and humidity setpoints.
- Change the simulated outside weather.
- Fan and chiller indicators; room colour based on temperature; event log.

## Limitations

- **Software simulation only.** There is no vendor PLC hardware and no IEC 61131-3 toolchain (no PLCopen/TIA/CODESYS-style compiler or runtime). The "PLC" is a Python interpreter for a small ST subset (see above), run on an asyncio loop. Scan timing is best-effort 100 ms, not deterministic or real-time. Behaviour has not been compared with any real PLC.
- Modbus here is plain Modbus TCP via pymodbus, between containers on one Docker network: no authentication, encryption, or access control; the backend API has none either (CORS allows all origins).
- The ST dialect is a subset (see "ST features supported"); programs written for real IEC 61131-3 systems will generally not parse. There are no timers, PID, function blocks or user functions.
- `hvac_control.st` is simple deadband control; there is no PID, hysteresis memory, anti-short-cycle protection, minimum on/off times, or fault handling beyond the fixed alarm limits.
- The thermal model is a coarse single-zone model with invented parameters (taken from the code, not validated against any real room or equipment). Running `ThermalModel` directly with the chiller on at full capacity cools the unclamped internal temperature far below the 10 °C published to the PLC within a minute of simulated time, so the plant response is not realistic and the published sensor value saturates at its clamp.
- The PLC makes a single connection attempt to the physical model at startup (`connect_to_physical_model`); there is no explicit reconnect loop in the PLC code. The PLC's physical-model host/port are hard-coded in `plc/main.py` (`physical-model`, 503) — the `PHYSICAL_MODEL_HOST`/`PHYSICAL_MODEL_PORT` variables in `docker-compose.yml` are not read.
- Registers are 16-bit unsigned; scaling truncates (`int()`), and negative values are not handled in any register.
- No automated tests exist in the repository, and none were run for this README.
- **What was actually verified for this document:** the ST program parses with `st_parser.py`; `PLCRuntime` outputs for several input combinations (idle, cooling at 24 °C and 30 °C, dehumidification, over-temperature alarm, disabled) matched the description above; `ThermalModel` was stepped directly; and the physical model, PLC and backend were started natively (not in Docker — no Docker daemon was available, so `docker-compose up --build` has **not** been run) with `/api/health` reporting all three healthy and `/api/control` `start` followed by `/api/status` showing the PLC idle (fan 20 %, chiller off at ≈22.8 °C). The frontend, Nginx image, the weather endpoint through the full stack, and cooling mode through the full stack were not exercised.

## Development
- Each component can be developed and tested independently.
- Use Dockerfiles for isolated environments.
- Modify source files as needed and rebuild containers.
