import os
from functools import lru_cache

class Settings:
    # PLC Configuration
    PLC_HOST: str = os.getenv("PLC_HOST", "plc")
    PLC_PORT: int = int(os.getenv("PLC_PORT", 502))
    
    # Physical Model Configuration
    PHYSICAL_MODEL_URL: str = os.getenv("PHYSICAL_MODEL_URL", "http://physical-model:8001")
    
    # Default Values
    DEFAULT_SETPOINT_TEMP: float = 22.0
    DEFAULT_SETPOINT_HUMIDITY: float = 50.0
    DEFAULT_TEMP_DEADBAND: float = 1.0
    DEFAULT_HUMIDITY_DEADBAND: float = 5.0
    
    # PLC Register Addresses
    REG_SYSTEM_ENABLE = 40001
    REG_SETPOINT_TEMP = 40002
    REG_SETPOINT_HUMIDITY = 40003
    REG_TEMP_DEADBAND = 40004
    REG_HUMIDITY_DEADBAND = 40005
    
    REG_ROOM_TEMP = 40101
    REG_ROOM_HUMIDITY = 40102
    REG_FAN_SPEED = 40103
    REG_CHILLER_ON = 40104
    REG_SYSTEM_STATUS = 40105
    REG_ALARM_ACTIVE = 40106

@lru_cache()
def get_settings():
    return Settings()