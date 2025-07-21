from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class SystemStatus(BaseModel):
    plc_running: bool
    timestamp: datetime
    room_temperature: float = Field(..., ge=-50, le=100)
    room_humidity: float = Field(..., ge=0, le=100)
    outside_temperature: float = Field(..., ge=-50, le=100)
    outside_humidity: float = Field(..., ge=0, le=100)
    fan_speed: int = Field(..., ge=0, le=100)  # 0-100%
    chiller_status: bool
    setpoint_temperature: float = Field(..., ge=15, le=30)
    setpoint_humidity: float = Field(..., ge=30, le=70)

class ControlCommand(BaseModel):
    command: str = Field(..., pattern="^(start|stop|set_temperature|set_humidity)$")  # Changed from regex to pattern
    value: Optional[float] = None

class WeatherConditions(BaseModel):
    temperature: float = Field(..., ge=-20, le=50)
    humidity: float = Field(..., ge=0, le=100)

class HealthCheck(BaseModel):
    status: str
    checks: dict
    timestamp: datetime