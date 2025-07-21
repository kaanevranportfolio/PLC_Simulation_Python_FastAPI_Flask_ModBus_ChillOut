from fastapi import APIRouter, Depends
from datetime import datetime
import httpx
from models import HealthCheck
from core.dependencies import get_modbus_client
from core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()

@router.get("/api/health", response_model=HealthCheck)
async def health_check(modbus_client=Depends(get_modbus_client)):
    """Health check endpoint"""
    checks = {
        "backend": "healthy",
        "plc_connection": "unknown",
        "physical_model": "unknown"
    }
    
    # Check PLC connection
    try:
        if modbus_client and await modbus_client.test_connection():
            checks["plc_connection"] = "healthy"
        else:
            checks["plc_connection"] = "unhealthy"
    except:
        checks["plc_connection"] = "unhealthy"
    
    # Check physical model
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.PHYSICAL_MODEL_URL}/health", 
                timeout=2.0
            )
            if response.status_code == 200:
                checks["physical_model"] = "healthy"
            else:
                checks["physical_model"] = "unhealthy"
    except:
        checks["physical_model"] = "unhealthy"
    
    overall_health = all(v == "healthy" for v in checks.values())
    return HealthCheck(
        status="healthy" if overall_health else "degraded",
        checks=checks,
        timestamp=datetime.now()
    )

@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "HVAC Control System Backend", "status": "running"}