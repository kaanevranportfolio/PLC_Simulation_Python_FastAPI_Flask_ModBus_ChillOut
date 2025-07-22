# HVAC PLC Simulation

This project simulates a Heating, Ventilation, and Air Conditioning (HVAC) control system using a PLC (Programmable Logic Controller) architecture. It consists of three main components: backend, frontend, and a physical model, all orchestrated via Docker Compose for easy deployment and management.

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
    __pycache__/
        thermal_model.cpython-311.pyc
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
    off.png
    on.png
    outside.png
```

## Components

### 1. Backend
- **Framework:** Python (FastAPI)
- **Purpose:** Handles API requests, system control, status updates, and Modbus communication with the PLC.
- **Key Files:**
  - `app.py`: Main FastAPI application.
  - `modbus_client.py`: Modbus protocol client for PLC communication.
  - `models.py`: Data models for API and system state.
  - `core/`: Configuration and dependency management.
  - `routes/`: API endpoints for health, status, system control, and weather.
- **Dockerized:** Yes (`backend/Dockerfile`)

### 2. Frontend
- **Framework:** HTML/CSS/JavaScript (Single Page App)
- **Purpose:** User interface for monitoring and controlling the HVAC system. Visualizes system state, temperature, humidity, and actuator status.
- **Key Files:**
  - `src/app.js`: Main application logic and UI updates.
  - `src/index.html`: Main HTML page.
  - `src/style.css`: Stylesheet.
  - `nginx.conf`: Nginx configuration for serving the frontend.
- **Dockerized:** Yes (`frontend/Dockerfile`)

### 3. Physical Model
- **Framework:** Python
- **Purpose:** Simulates the physical environment (room, thermal model) and interacts with the PLC via Modbus.
- **Key Files:**
  - `physical_simulation.py`: Main simulation logic.
  - `thermal_model.py`: Thermal model calculations.
- **Dockerized:** Yes (`physical-model/Dockerfile`)

### 4. PLC
- **Framework:** Python
- **Purpose:** Simulates a PLC runtime, parses Structured Text (ST) programs, and exposes Modbus registers for control.
- **Key Files:**
  - `main.py`: PLC runtime entry point.
  - `modbus_interface.py`: Modbus server implementation.
  - `plc_runtime.py`: PLC logic and execution.
  - `st_parser.py`: Structured Text parser.
  - `programs/hvac_control.st`: Example HVAC control program.
- **Dockerized:** Yes (`plc/Dockerfile`)

## Running the Project

### Prerequisites
- Docker and Docker Compose installed.

### Quick Start
1. Clone the repository.
2. Run the following command in the project root:
   ```bash
   docker-compose up --build
   ```
3. Access the frontend at [http://localhost:8080](http://localhost:8080).

### Stopping the Project
```bash
docker-compose down
```

## API Endpoints (Backend)
- `POST /api/control`: Start/stop system, set temperature/humidity setpoints.
- `POST /api/weather`: Update outside weather conditions.
- `GET /api/status`: Get current system status.
- `GET /api/health`: Health check.

## Frontend Features
- Real-time system status updates (temperature, humidity, fan speed, chiller status).
- Control system start/stop.
- Set temperature and humidity setpoints.
- Update outside weather conditions.
- Visual indicators for fan and chiller.
- Room color changes based on temperature.
- Logging of system events.

## Physical Model
- Simulates room temperature and humidity dynamics.
- Interacts with PLC via Modbus protocol.

## PLC
- Parses and executes Structured Text programs for HVAC control.
- Exposes Modbus registers for backend and physical model communication.

## PNGs
- Contains images for UI indicators (on/off/outside).

## Development
- Each component can be developed and tested independently.
- Use Dockerfiles for isolated environments.
- Modify source files as needed and rebuild containers.

## License
Specify your license here.

## Authors
List authors and contributors here.
