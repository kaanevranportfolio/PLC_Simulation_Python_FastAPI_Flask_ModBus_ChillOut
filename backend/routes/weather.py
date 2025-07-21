from fastapi import APIRouter, HTTPException
import httpx
import logging
from models import WeatherConditions
from core.config import get_settings

router = APIRouter(prefix="/api", tags=["weather"])
logger = logging.getLogger(__name__)
settings = get_settings()

@router.post("/weather")
async def set_weather(conditions: WeatherConditions):
    """Set outside weather conditions"""
    try:
        # Send to physical model
        logger.info(f"Sending weather data to physical model: {conditions.dict()}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.PHYSICAL_MODEL_URL}/api/weather",
                json=conditions.dict()
            )
            response.raise_for_status()
        
        return {"status": "success", "message": "Weather conditions updated"}
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from physical model: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Physical model error: {e.response.text}")
    except Exception as e:
        logger.error(f"Error setting weather: {e}")
        raise HTTPException(status_code=500, detail=str(e))