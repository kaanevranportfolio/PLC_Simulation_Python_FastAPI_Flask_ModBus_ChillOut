from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import httpx
import logging
from models import SystemStatus
from modbus_client import to_signed16
from core.dependencies import get_modbus_client, get_system_state
from core.config import get_settings

router = APIRouter(prefix="/api", tags=["status"])
logger = logging.getLogger(__name__)
settings = get_settings()

@router.get("/status", response_model=SystemStatus)
async def get_status(
    modbus_client=Depends(get_modbus_client),
    system_state=Depends(get_system_state)
):
    """Get current system status"""
    try:
        # Default values
        status_data = {
            "room_temperature": 20.0,
            "room_humidity": 50.0,
            "fan_speed": 0,
            "chiller_status": False,
            "outside_temperature": 25.0,
            "outside_humidity": 60.0
        }
        
        # Enable flag and setpoints: PLC values when readable, else last backend-cached values
        plc_state = dict(system_state)

        # Try to read from PLC via Modbus
        if modbus_client and await modbus_client.test_connection():
            try:
                registers = await modbus_client.read_holding_registers(settings.REG_ROOM_TEMP, 6)
                if registers:
                    status_data["room_temperature"] = to_signed16(registers[0]) / 10.0
                    status_data["room_humidity"] = registers[1] / 10.0
                    status_data["fan_speed"] = registers[2]
                    status_data["chiller_status"] = bool(registers[3])
                # Command registers as currently held by the PLC (40001-40005)
                commands = await modbus_client.read_holding_registers(settings.REG_SYSTEM_ENABLE, 5)
                if commands:
                    plc_state["plc_running"] = bool(commands[0])
                    plc_state["setpoint_temperature"] = commands[1] / 10.0
                    plc_state["setpoint_humidity"] = commands[2] / 10.0
            except Exception as e:
                logger.warning(f"Failed to read PLC status: {e}")
        
        # Get outside conditions from physical model
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.PHYSICAL_MODEL_URL}/api/status", 
                    timeout=2.0
                )
                if response.status_code == 200:
                    pm_status = response.json()
                    #logger.info(f"Received /api/status from physical-model: {pm_status}")
                    status_data["outside_temperature"] = pm_status.get("outside_temperature", 25.0)
                    status_data["outside_humidity"] = pm_status.get("outside_humidity", 60.0)
                    '''
                    # Fallback for room values if PLC values are missing or zero
                    if (not status_data["room_temperature"] or status_data["room_temperature"] == 0.0):
                        status_data["room_temperature"] = pm_status.get("room_temperature", 20.0)
                    if (not status_data["room_humidity"] or status_data["room_humidity"] == 0.0):
                        status_data["room_humidity"] = pm_status.get("room_humidity", 50.0)
                    '''
        except Exception as e:
        
            logger.warning(f"Physical model unavailable: {e}")
        
        final_status = SystemStatus(
            plc_running=plc_state["plc_running"],
            timestamp=datetime.now(),
            **status_data,
            setpoint_temperature=plc_state["setpoint_temperature"],
            setpoint_humidity=plc_state["setpoint_humidity"]
        )
        #logger.info(f"Sending status to frontend: {final_status}")
        return final_status
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))