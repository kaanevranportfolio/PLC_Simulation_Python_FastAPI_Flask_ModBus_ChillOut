import asyncio
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ModbusClient:
    def __init__(self, host: str, port: int = 502):
        self.host = host
        self.port = port
        self.client: Optional[AsyncModbusTcpClient] = None
        
        # PLC Register mapping (matching PLC simulator)
        # Note: Modbus protocol uses 0-based addressing, so subtract 40001
        self.registers = {
            # Commands (from Backend)
            "system_enable": 40001 - 40001,      # 0
            "setpoint_temp": 40002 - 40001,      # 1
            "setpoint_humidity": 40003 - 40001,  # 2
            "temp_deadband": 40004 - 40001,      # 3
            "humidity_deadband": 40005 - 40001,  # 4
            
            # Status (from PLC)
            "room_temperature": 40101 - 40001,   # 100
            "room_humidity": 40102 - 40001,      # 101
            "fan_speed": 40103 - 40001,          # 102
            "chiller_on": 40104 - 40001,         # 103
            "system_status": 40105 - 40001,      # 104
            "alarm_active": 40106 - 40001,       # 105
        }
        
    async def connect(self, max_retries: int = 10, retry_delay: int = 5) -> bool:
        """Connect to Modbus server with retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to connect to Modbus server at {self.host}:{self.port} (attempt {attempt + 1}/{max_retries})")
                self.client = AsyncModbusTcpClient(self.host, self.port)
                await self.client.connect()
                
                # Test if connection is really working
                if self.client.connected:
                    # Try a simple read to verify connection
                    try:
                        result = await self.client.read_holding_registers(0, 1)
                        if not result.isError():
                            logger.info(f"Successfully connected to Modbus server at {self.host}:{self.port}")
                            return True
                    except:
                        pass
                
                # If we're here, connection failed
                if self.client:
                    self.client.close()
                    
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
        
        logger.error(f"Failed to connect to Modbus server after {max_retries} attempts")
        return False
    
    async def ensure_connected(self):
        """Ensure client is connected before operations"""
        if not self.client or not self.client.connected:
            connected = await self.connect()
            if not connected:
                raise ModbusException("Cannot establish connection to Modbus server")
    
    async def disconnect(self):
        """Disconnect from Modbus server"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from Modbus server")
    
    async def test_connection(self) -> bool:
        """Test if connection is active"""
        if not self.client or not self.client.connected:
            return False
        try:
            # Try to read a register
            result = await self.client.read_holding_registers(0, 1)
            return not result.isError()
        except:
            return False
    
    async def read_holding_registers(self, address: int, count: int) -> List[int]:
        """Read multiple holding registers"""
        await self.ensure_connected()
        
        try:
            # Adjust for 0-based addressing
            modbus_address = address - 40001 if address >= 40001 else address
            result = await self.client.read_holding_registers(modbus_address, count)
            
            if result.isError():
                raise ModbusException(f"Error reading registers at {address}")
            
            return result.registers
            
        except Exception as e:
            logger.error(f"Error reading holding registers: {e}")
            self.client = None  # Force reconnection next time
            raise
    
    async def read_system_status(self) -> Dict[str, Any]:
        """Read all system status from PLC"""
        await self.ensure_connected()
        
        try:
            # Read all status registers in one request (40101-40106)
            result = await self.client.read_holding_registers(
                self.registers["room_temperature"], 
                6  # Read 6 consecutive registers
            )
            
            if result.isError():
                raise ModbusException("Error reading status registers")
            
            # Parse results
            status = {
                "room_temperature": result.registers[0] / 10.0,
                "room_humidity": result.registers[1] / 10.0,
                "fan_speed": result.registers[2],
                "chiller_status": bool(result.registers[3]),
                "system_status": result.registers[4],
                "alarm_active": bool(result.registers[5]),
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Error reading system status: {e}")
            self.client = None  # Force reconnection next time
            raise
    
    async def write_register(self, address: int, value: int):
        """Write a single holding register"""
        await self.ensure_connected()
        
        try:
            # Adjust for 0-based addressing
            modbus_address = address - 40001 if address >= 40001 else address
            result = await self.client.write_register(modbus_address, value)
            
            if result.isError():
                raise ModbusException(f"Error writing register {address}")
                
            logger.debug(f"Wrote {value} to register {address} (modbus addr: {modbus_address})")
            
        except Exception as e:
            logger.error(f"Error writing register: {e}")
            self.client = None  # Force reconnection next time
            raise
    
    async def write_registers(self, address: int, values: List[int]):
        """Write multiple holding registers"""
        await self.ensure_connected()
        
        try:
            # Adjust for 0-based addressing
            modbus_address = address - 40001 if address >= 40001 else address
            result = await self.client.write_registers(modbus_address, values)
            
            if result.isError():
                raise ModbusException(f"Error writing registers at {address}")
                
            logger.debug(f"Wrote {values} to registers starting at {address}")
            
        except Exception as e:
            logger.error(f"Error writing registers: {e}")
            self.client = None  # Force reconnection next time
            raise