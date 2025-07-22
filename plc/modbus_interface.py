import logging
import asyncio
from pymodbus.server.async_io import StartAsyncTcpServer
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from typing import Optional

logger = logging.getLogger(__name__)

class ModbusInterface:
    """Modbus interface for PLC communication"""
    
    def __init__(self, plc_runtime):
        self.plc_runtime = plc_runtime
        self.server = None
        self.client = None
        self.server_context = None
        # Properly initialize identity for Modbus server
        self.identity = ModbusDeviceIdentification()
        self.identity.VendorName = 'CustomPLC'
        self.identity.ProductCode = 'PLC'
        self.identity.VendorUrl = 'http://localhost'
        self.identity.ProductName = 'Python PLC Simulator'
        self.identity.ModelName = 'HVAC PLC'
        self.identity.MajorMinorRevision = '1.0'
        self.running = False
        
        # Modbus register mapping
        # Holding Registers (40001-40999)
        self.register_map = {
            # From Backend (Commands)
            'SystemEnable': 40001,      # 0=Off, 1=On
            'SetpointTemp': 40002,      # Temperature setpoint (x10)
            'SetpointHumidity': 40003,  # Humidity setpoint (x10)
            'TempDeadband': 40004,      # Temperature deadband (x10)
            'HumidityDeadband': 40005, # Humidity deadband (x10)
            
            # To Backend (Status)
            'RoomTemperature': 40101,   # Current temperature (x10)
            'RoomHumidity': 40102,      # Current humidity (x10)
            'FanSpeed': 40103,          # Fan speed 0-100%
            'ChillerOn': 40104,         # 0=Off, 1=On
            'SystemStatus': 40105,      # 0=Off, 1=Cooling, 2=Idle
            'AlarmActive': 40106,       # 0=No alarm, 1=Alarm
            
            # From Physical Model (Sensors)
            'SensorTemp': 40201,        # Temperature from sensor (x10)
            'SensorHumidity': 40202,    # Humidity from sensor (x10)
            
            # To Physical Model (Actuators)
            'ActuatorFanSpeed': 40301,  # Fan speed command 0-100%
            'ActuatorChiller': 40302,   # Chiller command 0=Off, 1=On
        }
        
        # Initialize Modbus data blocks
        self._initialize_datastore()
    
    def _initialize_datastore(self):
        """Initialize Modbus server datastore"""
        # Create data blocks with enough space
        holding_registers = ModbusSequentialDataBlock(0, [0] * 1000)
        
        slave_context = ModbusSlaveContext(
            hr=holding_registers,  # Holding registers
            zero_mode=True
        )
        
        self.server_context = ModbusServerContext(slaves=slave_context, single=True)
        
        # Initialize default values for command registers
        context = self.server_context[1]
        # Set default setpoints
        context.setValues(3, self.register_map['SetpointTemp'] - 40001, [220])  # 22.0°C
        context.setValues(3, self.register_map['SetpointHumidity'] - 40001, [450])  # 45.0%
        context.setValues(3, self.register_map['TempDeadband'] - 40001, [10])  # 1.0°C
        context.setValues(3, self.register_map['HumidityDeadband'] - 40001, [50])  # 5.0%
        
        # ... rest of initialization ...
    
    async def start_server(self, port=502):
        """Start Modbus TCP server"""
        try:
            logger.info(f"Starting Modbus server on port {port}")
            # Await the server coroutine and store the server reference
            self.server = await StartAsyncTcpServer(
                context=self.server_context,
                identity=self.identity,
                address=("0.0.0.0", port)
            )
            self.running = True
            logger.info("Modbus server started successfully")
            # Keep this task running
            while self.running:
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to start Modbus server: {e}")
            raise
    
    async def _server_update_loop(self):
        """Background task to keep server running"""
        while self.running:
            await asyncio.sleep(0.1)
    
    async def connect_to_physical_model(self, host='physical-model', port=503):
        """Connect to physical model Modbus server"""
        try:
            logger.info(f"Connecting to physical model at {host}:{port}")
            
            # Wait a bit for physical model to start
            await asyncio.sleep(2)
            
            self.client = AsyncModbusTcpClient(host=host, port=port)
            connected = await self.client.connect()
            
            if connected:
                logger.info("Connected to physical model successfully")
            else:
                logger.error("Failed to connect to physical model")
                
        except Exception as e:
            logger.error(f"Error connecting to physical model: {e}")
    
    async def read_inputs(self):
        """Read sensor values from physical model"""
        if not self.client:
            return
        
        try:
            # Read temperature and humidity from physical model
            result = await self.client.read_holding_registers(
                address=self.register_map['SensorTemp'] - 40001,
                count=2,
                slave=1
            )
            
            if not result.isError():
                # Update PLC inputs with sensor values
                temp = result.registers[0] / 10.0  # Convert from x10
                humidity = result.registers[1] / 10.0
                
                self.plc_runtime.memory.inputs['RoomTemperature'] = temp
                self.plc_runtime.memory.inputs['RoomHumidity'] = humidity
                
                # Also update status registers for backend
                self._write_register('RoomTemperature', int(temp * 10))
                self._write_register('RoomHumidity', int(humidity * 10))
            
        except Exception as e:
            logger.error(f"Error reading from physical model: {e}")
    
    async def write_outputs(self):
        """Write actuator commands to physical model"""
        if not self.client:
            return
        
        try:
            # Get output values from PLC
            fan_speed = int(self.plc_runtime.memory.outputs.get('FanSpeed', 0))
            chiller_on = int(self.plc_runtime.memory.outputs.get('ChillerOn', False))
            
            # Write to physical model
            await self.client.write_registers(
                address=self.register_map['ActuatorFanSpeed'] - 40001,
                values=[fan_speed, chiller_on],
                slave=1
            )
            
        except Exception as e:
            logger.error(f"Error writing to physical model: {e}")
    
    async def update_server_registers(self):
        """Update Modbus server registers for backend access"""
        try:
            # Get the slave context properly for pymodbus 3.x
            context = self.server_context[1]  # or self.server_context[0x00] for slave 0
            
            # System Enable
            system_enable = context.getValues(3, self.register_map['SystemEnable'] - 40001, 1)[0]
            self.plc_runtime.memory.inputs['SystemEnable'] = bool(system_enable)
            logger.debug(f"Read SystemEnable: {system_enable}")
            
            # Temperature Setpoint
            setpoint_temp = context.getValues(3, self.register_map['SetpointTemp'] - 40001, 1)[0]
            self.plc_runtime.memory.inputs['SetpointTemp'] = setpoint_temp / 10.0  # Convert from x10
            logger.debug(f"Read SetpointTemp: {setpoint_temp / 10.0}°C")
            
            # Humidity Setpoint
            setpoint_humidity = context.getValues(3, self.register_map['SetpointHumidity'] - 40001, 1)[0]
            self.plc_runtime.memory.inputs['SetpointHumidity'] = setpoint_humidity / 10.0
            logger.debug(f"Read SetpointHumidity: {setpoint_humidity / 10.0}%")
            
            # Temperature Deadband
            temp_deadband = context.getValues(3, self.register_map['TempDeadband'] - 40001, 1)[0]
            self.plc_runtime.memory.inputs['TempDeadband'] = temp_deadband / 10.0
            logger.debug(f"Read TempDeadband: {temp_deadband / 10.0}°C")
            
            # Humidity Deadband
            humidity_deadband = context.getValues(3, self.register_map['HumidityDeadband'] - 40001, 1)[0]
            self.plc_runtime.memory.inputs['HumidityDeadband'] = humidity_deadband / 10.0
            logger.debug(f"Read HumidityDeadband: {humidity_deadband / 10.0}%")
            
            # Update status registers for backend
            fan_speed = int(self.plc_runtime.memory.outputs.get('FanSpeed', 0))
            chiller_on = int(self.plc_runtime.memory.outputs.get('ChillerOn', False))
            system_status = int(self.plc_runtime.memory.outputs.get('SystemStatus', 0))
            alarm_active = int(self.plc_runtime.memory.outputs.get('AlarmActive', False))
            
            logger.debug(f"Writing outputs - FanSpeed: {fan_speed}, ChillerOn: {chiller_on}, SystemStatus: {system_status}")
            
            self._write_register('FanSpeed', fan_speed)
            self._write_register('ChillerOn', chiller_on)
            self._write_register('SystemStatus', system_status)
            self._write_register('AlarmActive', alarm_active)
            
        except Exception as e:
            logger.error(f"Error updating server registers: {e}")


 
    def _write_register(self, name: str, value: int):
        """Write value to Modbus holding register"""
        if name in self.register_map:
            address = self.register_map[name] - 40001
            context = self.server_context[1]
            context.setValues(3, address, [value])
    
    def _read_register(self, name: str) -> int:
        """Read value from Modbus holding register"""
        if name in self.register_map:
            address = self.register_map[name] - 40001
            context = self.server_context[1]
            return context.getValues(3, address, 1)[0]
        return 0
    
    async def stop(self):
        """Stop Modbus connections"""
        self.running = False
        
        if self.client:
            self.client.close()
            
        if self.server:
            self.server.server_close()
        
        logger.info("Modbus interface stopped")
    
    def get_register_map_info(self):
        """Get information about register mapping"""
        return {
            'commands': {k: v for k, v in self.register_map.items() if 40001 <= v <= 40099},
            'status': {k: v for k, v in self.register_map.items() if 40101 <= v <= 40199},
            'sensors': {k: v for k, v in self.register_map.items() if 40201 <= v <= 40299},
            'actuators': {k: v for k, v in self.register_map.items() if 40301 <= v <= 40399}
        }