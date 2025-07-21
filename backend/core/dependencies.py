from modbus_client import ModbusClient
from core.config import get_settings

# Global instances
modbus_client: ModbusClient = None
system_state = {
    "plc_running": False,
    "setpoint_temperature": 22.0,
    "setpoint_humidity": 50.0,
}

def get_modbus_client() -> ModbusClient:
    return modbus_client

def get_system_state() -> dict:
    return system_state