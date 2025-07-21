import asyncio
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymodbus.server.async_io import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from thermal_model import ThermalModel
import threading
import time
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for REST API
app = Flask(__name__)
CORS(app)

# Global variables
thermal_model = ThermalModel()
modbus_context = None
running = True

# Weather conditions with sensible defaults
weather_conditions = {
    "temperature": 25.0,
    "humidity": 60.0
}

# Modbus register mapping (matching PLC expectations)
# Physical Model acts as Modbus SERVER on port 503
REGISTER_MAP = {
    # Sensor data (PLC reads these)
    "sensor_temp": 40201 - 40001,      # 200 - Temperature sensor
    "sensor_humidity": 40202 - 40001,   # 201 - Humidity sensor
    
    # Actuator commands (PLC writes these)
    "actuator_fan": 40301 - 40001,      # 300 - Fan speed (0-100%)
    "actuator_chiller": 40302 - 40001,   # 301 - Chiller state (0/1)
}

def setup_modbus_server():
    """Setup Modbus server datastore"""
    global modbus_context
    
    # Create data blocks
    store = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 500),  # Holding registers
        zero_mode=True
    )
    
    modbus_context = ModbusServerContext(slaves=store, single=True)
    
    logger.info("Modbus server datastore initialized")

async def update_modbus_data():
    """Update Modbus registers with sensor data and read actuator commands"""
    global running, modbus_context
    
    # Initialize thermal model
    thermal_model.room_temperature = 22.0
    thermal_model.room_humidity = 50.0
    thermal_model.set_outside_conditions(
        weather_conditions["temperature"],
        weather_conditions["humidity"]
    )
    
    while running:
        try:
            if not modbus_context:
                await asyncio.sleep(1)
                continue
            
            # Get the datastore
            context = modbus_context[1]
            
            # Read actuator commands from Modbus registers (written by PLC)
            fan_speed = context.getValues(3, REGISTER_MAP["actuator_fan"], 1)[0]
            chiller_state = context.getValues(3, REGISTER_MAP["actuator_chiller"], 1)[0]
            
            # Apply actuator commands to thermal model
            thermal_model.set_fan_speed(fan_speed)
            thermal_model.set_chiller_state(bool(chiller_state))
            
            # Update thermal model with current weather
            thermal_model.set_outside_conditions(
                weather_conditions["temperature"],
                weather_conditions["humidity"]
            )
            
            # Step the simulation
            thermal_model.step(1.0)  # 1 second time step
            
            # Get current room conditions
            room_temp, room_humidity = thermal_model.get_room_conditions()
            
            # Ensure reasonable bounds
            room_temp = max(10.0, min(50.0, room_temp))
            room_humidity = max(20.0, min(90.0, room_humidity))
            
            # Write sensor data to Modbus registers (for PLC to read)
            context.setValues(3, REGISTER_MAP["sensor_temp"], [int(room_temp * 10)])
            context.setValues(3, REGISTER_MAP["sensor_humidity"], [int(room_humidity * 10)])
            
            # Log current state
            logger.info(f"Room: {room_temp:.1f}°C, {room_humidity:.0f}% | "
                       f"Fan: {fan_speed}% | Chiller: {'ON' if chiller_state else 'OFF'} | "
                       f"Outside: {weather_conditions['temperature']:.1f}°C, "
                       f"{weather_conditions['humidity']:.0f}%")
            
        except Exception as e:
            logger.error(f"Error updating Modbus data: {e}", exc_info=True)
        
        await asyncio.sleep(1)

async def run_modbus_server():
    """Run the Modbus TCP server"""
    setup_modbus_server()
    
    # Set device identification
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Physical Model Simulator'
    identity.ProductCode = 'PM-SIM'
    identity.VendorUrl = 'http://github.com/hvac-simulator'
    identity.ProductName = 'HVAC Physical Model'
    identity.ModelName = 'PM-1000'
    identity.MajorMinorRevision = '1.0'
    
    # Create update task
    update_task = asyncio.create_task(update_modbus_data())
    
    # Start server - in pymodbus 3.x, minimal parameters
    server = await StartAsyncTcpServer(
        context=modbus_context,
        identity=identity,
        address=("0.0.0.0", 503)
    )
    
    logger.info("Modbus server started on port 503")
    
    # Keep running
    await asyncio.gather(update_task)

# Flask Routes
@app.route('/health')
def health_check():
    """Health check endpoint"""
    room_temp, room_humidity = thermal_model.get_room_conditions()
    return jsonify({
        "status": "healthy",
        "model_running": thermal_model is not None,
        "room_temperature": room_temp,
        "room_humidity": room_humidity,
        "outside_temperature": weather_conditions["temperature"],
        "outside_humidity": weather_conditions["humidity"]
    })

@app.route('/api/weather', methods=['POST'])
def set_weather():
    """Set weather conditions via REST API"""
    global weather_conditions
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "message": "No JSON data provided"
            }), 400
            
        temp = float(data.get("temperature", 25.0))
        humidity = float(data.get("humidity", 60.0))
        
        # Validate input
        if temp < -20 or temp > 50:
            raise ValueError(f"Temperature {temp} out of valid range (-20 to 50)")
        if humidity < 0 or humidity > 100:
            raise ValueError(f"Humidity {humidity} out of valid range (0 to 100)")
        
        weather_conditions["temperature"] = temp
        weather_conditions["humidity"] = humidity
        
        logger.info(f"Weather updated via API: {temp}°C, {humidity}%")
        
        return jsonify({
            "status": "success",
            "weather": weather_conditions
        })
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        return jsonify({
            "status": "error",
            "message": str(ve)
        }), 400
    except Exception as e:
        logger.error(f"Error in set_weather: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/status')
def get_status():
    """Get current simulation status"""
    room_temp, room_humidity = thermal_model.get_room_conditions()
    
    status_data = {
        "room_temperature": room_temp,
        "room_humidity": room_humidity,
        "outside_temperature": weather_conditions["temperature"],
        "outside_humidity": weather_conditions["humidity"],
        "fan_speed": thermal_model.fan_speed,
        "chiller_on": thermal_model.chiller_on,
        "timestamp": time.time()
    }
    logger.info(f"/api/status response: {status_data}")
    return jsonify(status_data)

def run_flask():
    """Run Flask server in a separate thread"""
    port = int(os.getenv("API_PORT", 8001))
    app.run(host='0.0.0.0', port=port, debug=False)

async def main():
    """Main async function"""
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    logger.info("Starting HVAC Physical Model Simulation")
    logger.info("REST API on port 8001")
    logger.info("Modbus server on port 503")
    
    # Run Modbus server
    try:
        await run_modbus_server()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        global running
        running = False

if __name__ == "__main__":
    asyncio.run(main())