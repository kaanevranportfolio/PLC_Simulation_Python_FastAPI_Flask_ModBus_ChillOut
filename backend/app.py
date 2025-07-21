from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from contextlib import asynccontextmanager

# Import routers
from routes import system, status, weather, health
from core.config import get_settings
from core import dependencies
from modbus_client import ModbusClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info("Starting HVAC Control System Backend")
    
    # Initialize Modbus client
    dependencies.modbus_client = ModbusClient(settings.PLC_HOST, settings.PLC_PORT)
    
    # Try to connect with retries
    connected = await dependencies.modbus_client.connect(max_retries=20, retry_delay=3)
    
    if not connected:
        logger.error("Failed to establish Modbus connection. API will start but may have issues.")
    else:
        logger.info("Modbus connection established successfully")
        
        # Initialize default setpoints
        try:
            await dependencies.modbus_client.write_register(
                settings.REG_SETPOINT_TEMP, 
                int(settings.DEFAULT_SETPOINT_TEMP * 10)
            )
            await dependencies.modbus_client.write_register(
                settings.REG_SETPOINT_HUMIDITY, 
                int(settings.DEFAULT_SETPOINT_HUMIDITY * 10)
            )
            await dependencies.modbus_client.write_register(
                settings.REG_TEMP_DEADBAND, 
                int(settings.DEFAULT_TEMP_DEADBAND * 10)
            )
            await dependencies.modbus_client.write_register(
                settings.REG_HUMIDITY_DEADBAND, 
                int(settings.DEFAULT_HUMIDITY_DEADBAND * 10)
            )
            logger.info("Default setpoints initialized")
        except Exception as e:
            logger.error(f"Failed to initialize setpoints: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down HVAC Control System Backend")
    if dependencies.modbus_client:
        await dependencies.modbus_client.disconnect()

# Create FastAPI app
app = FastAPI(
    title="HVAC Control System Backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(system.router)
app.include_router(status.router)
app.include_router(weather.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)