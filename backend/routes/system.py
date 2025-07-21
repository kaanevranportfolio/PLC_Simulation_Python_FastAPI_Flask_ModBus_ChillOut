from fastapi import APIRouter, HTTPException, Depends
from models import ControlCommand
from core.dependencies import get_modbus_client, get_system_state
from core.config import get_settings
import logging

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger(__name__)
settings = get_settings()

@router.post("/control")
async def control_system(
    command: ControlCommand,
    modbus_client=Depends(get_modbus_client),
    system_state=Depends(get_system_state)
):
    """Send control commands to PLC"""
    try:
        if not modbus_client or not await modbus_client.test_connection():
            raise HTTPException(status_code=503, detail="PLC connection not available")
        
        if command.command == "start":
            system_state["plc_running"] = True
            await modbus_client.write_register(settings.REG_SYSTEM_ENABLE, 1)
            return {"status": "success", "message": "System started"}
            
        elif command.command == "stop":
            system_state["plc_running"] = False
            await modbus_client.write_register(settings.REG_SYSTEM_ENABLE, 0)
            return {"status": "success", "message": "System stopped"}
            
        elif command.command == "set_temperature":
            if command.value is None:
                raise ValueError("Temperature value required")
            system_state["setpoint_temperature"] = command.value
            await modbus_client.write_register(settings.REG_SETPOINT_TEMP, int(command.value * 10))
            return {"status": "success", "message": f"Temperature setpoint: {command.value}°C"}
            
        elif command.command == "set_humidity":
            if command.value is None:
                raise ValueError("Humidity value required")
            system_state["setpoint_humidity"] = command.value
            await modbus_client.write_register(settings.REG_SETPOINT_HUMIDITY, int(command.value * 10))
            return {"status": "success", "message": f"Humidity setpoint: {command.value}%"}
            
    except Exception as e:
        logger.error(f"Error in control command: {e}")
        raise HTTPException(status_code=400, detail=str(e))