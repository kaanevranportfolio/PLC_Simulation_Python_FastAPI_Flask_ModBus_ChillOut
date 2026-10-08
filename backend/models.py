from pydantic import BaseModel, Field, model_validator
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

# Setpoint ranges (same as the frontend sliders and SystemStatus above)
SETPOINT_TEMP_RANGE = (15.0, 30.0)
SETPOINT_HUMIDITY_RANGE = (30.0, 70.0)


class ControlCommand(BaseModel):
    command: str = Field(..., pattern="^(start|stop|set_temperature|set_humidity)$")  # Changed from regex to pattern
    value: Optional[float] = None

    @model_validator(mode="after")
    def check_setpoint_range(self):
        ranges = {"set_temperature": SETPOINT_TEMP_RANGE, "set_humidity": SETPOINT_HUMIDITY_RANGE}
        if self.command in ranges:
            low, high = ranges[self.command]
            if self.value is None:
                raise ValueError(f"{self.command} requires a value")
            if not low <= self.value <= high:
                raise ValueError(f"{self.command} value must be between {low} and {high}")
        return self

class WeatherConditions(BaseModel):
    temperature: float = Field(..., ge=-20, le=50)
    humidity: float = Field(..., ge=0, le=100)

class HealthCheck(BaseModel):
    status: str
    checks: dict
    timestamp: datetime