import logging
import asyncio
import os
from pymodbus.server.async_io import ModbusTcpServer
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.pdu import ExceptionResponse

logger = logging.getLogger(__name__)

REGISTER_BASE = 40001  # register_map addresses are 4xxxx style; the wire address is address - REGISTER_BASE


def encode_x10(value, signed=False):
    """Scale a physical value by 10 and encode it as a 16-bit register value.

    Rounds to nearest (not truncation) and saturates at the register range.
    signed=True uses two's complement (int16), unsigned uses 0..65535.
    """
    raw = int(round(float(value) * 10))
    if signed:
        return max(-32768, min(32767, raw)) & 0xFFFF
    return max(0, min(0xFFFF, raw))


def decode_x10(raw, signed=False):
    """Inverse of encode_x10."""
    raw = int(raw)
    if signed and raw >= 0x8000:
        raw -= 0x10000
    return raw / 10.0


def encode_uint(value, maximum=0xFFFF):
    """Encode an integer-valued quantity (percent, status code, flag) as a register value."""
    return max(0, min(maximum, int(round(float(value)))))


class ModbusInterface:
    """Modbus interface for the PLC.

    - Server (default port 502): holds the registers the backend reads and writes.
    - Client: connects to the physical model's Modbus server to read sensors and write actuators.
      The client reconnects automatically (at most once per `reconnect_interval`) and the
      interface reports a sensor fault when plant data has not been readable for
      `sensor_fault_limit` consecutive scans (or has never been read).
    """

    def __init__(self, plc_runtime, plant_host=None, plant_port=None, server_port=None,
                 sensor_fault_limit=10, reconnect_interval=1.0, io_timeout=1.0):
        self.plc_runtime = plc_runtime
        self.plant_host = plant_host or os.getenv('PHYSICAL_MODEL_HOST', 'physical-model')
        self.plant_port = int(plant_port or os.getenv('PHYSICAL_MODEL_PORT', 503))
        self.server_port = int(server_port or os.getenv('PLC_MODBUS_PORT', 502))
        self.sensor_fault_limit = sensor_fault_limit
        self.reconnect_interval = reconnect_interval
        self.io_timeout = io_timeout

        self.server = None
        self.client = None
        self.server_context = None
        self.running = False

        self._last_connect_attempt = None
        self._plant_link_up = None          # None = not yet known, for transition logging
        self.sensor_failures = 0            # consecutive failed sensor reads
        self.sensor_valid = False           # True once at least one sensor read has succeeded

        # Properly initialize identity for Modbus server
        self.identity = ModbusDeviceIdentification()
        self.identity.VendorName = 'CustomPLC'
        self.identity.ProductCode = 'PLC'
        self.identity.VendorUrl = 'http://localhost'
        self.identity.ProductName = 'Python PLC Simulator'
        self.identity.ModelName = 'HVAC PLC'
        self.identity.MajorMinorRevision = '1.0'

        # Modbus register mapping (holding registers, 4xxxx addressing)
        self.register_map = {
            # From Backend (Commands)
            'SystemEnable': 40001,      # 0=Off, 1=On
            'SetpointTemp': 40002,      # Temperature setpoint (x10, unsigned)
            'SetpointHumidity': 40003,  # Humidity setpoint (x10, unsigned)
            'TempDeadband': 40004,      # Temperature deadband (x10, unsigned)
            'HumidityDeadband': 40005,  # Humidity deadband (x10, unsigned)

            # To Backend (Status)
            'RoomTemperature': 40101,   # Current temperature (x10, signed int16)
            'RoomHumidity': 40102,      # Current humidity (x10, unsigned)
            'FanSpeed': 40103,          # Fan speed 0-100%
            'ChillerOn': 40104,         # 0=Off, 1=On
            'SystemStatus': 40105,      # 0=Off, 1=Cooling, 2=Idle
            'AlarmActive': 40106,       # 0=No alarm, 1=Alarm

            # From Physical Model (Sensors) - addresses on the physical model's server
            'SensorTemp': 40201,        # Temperature from sensor (x10, signed int16)
            'SensorHumidity': 40202,    # Humidity from sensor (x10, unsigned)

            # To Physical Model (Actuators) - addresses on the physical model's server
            'ActuatorFanSpeed': 40301,  # Fan speed command 0-100%
            'ActuatorChiller': 40302,   # Chiller command 0=Off, 1=On
        }

        self._initialize_datastore()

    # ------------------------------------------------------------------ server side

    def _offset(self, name):
        return self.register_map[name] - REGISTER_BASE

    def _initialize_datastore(self):
        """Initialize Modbus server datastore"""
        holding_registers = ModbusSequentialDataBlock(0, [0] * 1000)

        slave_context = ModbusSlaveContext(
            hr=holding_registers,  # Holding registers
            zero_mode=True
        )

        self.server_context = ModbusServerContext(slaves=slave_context, single=True)

        # Default values for command registers
        context = self.server_context[1]
        context.setValues(3, self._offset('SetpointTemp'), [encode_x10(22.0)])
        context.setValues(3, self._offset('SetpointHumidity'), [encode_x10(45.0)])
        context.setValues(3, self._offset('TempDeadband'), [encode_x10(1.0)])
        context.setValues(3, self._offset('HumidityDeadband'), [encode_x10(5.0)])

    async def start_server(self, port=None):
        """Run the Modbus TCP server until stop() is called (or the task is cancelled)."""
        port = int(port or self.server_port)
        logger.info(f"Starting Modbus server on port {port}")
        self.server = ModbusTcpServer(
            context=self.server_context,
            identity=self.identity,
            address=("0.0.0.0", port),
        )
        self.running = True
        try:
            await self.server.serve_forever()
        finally:
            self.running = False

    def read_commands(self):
        """Copy the backend's command registers (40001-40005) into the ST inputs."""
        context = self.server_context[1]
        inputs = self.plc_runtime.memory.inputs

        inputs['SystemEnable'] = bool(context.getValues(3, self._offset('SystemEnable'), 1)[0])
        inputs['SetpointTemp'] = decode_x10(context.getValues(3, self._offset('SetpointTemp'), 1)[0])
        inputs['SetpointHumidity'] = decode_x10(context.getValues(3, self._offset('SetpointHumidity'), 1)[0])
        inputs['TempDeadband'] = decode_x10(context.getValues(3, self._offset('TempDeadband'), 1)[0])
        inputs['HumidityDeadband'] = decode_x10(context.getValues(3, self._offset('HumidityDeadband'), 1)[0])

    def write_status(self):
        """Publish the status registers (40101-40106) for the backend."""
        memory = self.plc_runtime.memory
        self._write_register('RoomTemperature',
                             encode_x10(memory.inputs.get('RoomTemperature', 0.0), signed=True))
        self._write_register('RoomHumidity', encode_x10(memory.inputs.get('RoomHumidity', 0.0)))
        self._write_register('FanSpeed', encode_uint(memory.outputs.get('FanSpeed', 0), maximum=100))
        self._write_register('ChillerOn', encode_uint(bool(memory.outputs.get('ChillerOn', False)), maximum=1))
        self._write_register('SystemStatus', encode_uint(memory.outputs.get('SystemStatus', 0)))
        self._write_register('AlarmActive', encode_uint(bool(memory.outputs.get('AlarmActive', False)), maximum=1))

    def _write_register(self, name, value):
        """Write a raw 16-bit value to a holding register of the PLC server."""
        self.server_context[1].setValues(3, self._offset(name), [value])

    def _read_register(self, name):
        """Read a raw 16-bit value from a holding register of the PLC server."""
        return self.server_context[1].getValues(3, self._offset(name), 1)[0]

    # ------------------------------------------------------------------ plant (client) side

    @property
    def sensor_fault(self):
        """True when plant sensor data is currently untrustworthy."""
        return (not self.sensor_valid) or self.sensor_failures >= self.sensor_fault_limit

    def _set_link(self, up, detail=""):
        if self._plant_link_up != up:
            if up:
                logger.info(f"Link to physical model {self.plant_host}:{self.plant_port} is up")
            else:
                logger.error(f"Link to physical model {self.plant_host}:{self.plant_port} is down {detail}".rstrip())
            self._plant_link_up = up

    def _drop_connection(self, reason):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # closing a broken client must not break the scan
                pass
            self.client = None
        self._set_link(False, f"({reason})")

    async def _ensure_connected(self):
        """Return True if a connected client is available; otherwise try to (re)connect, rate-limited."""
        if self.client is not None and self.client.connected:
            return True

        loop = asyncio.get_event_loop()
        now = loop.time()
        if (self._last_connect_attempt is not None
                and now - self._last_connect_attempt < self.reconnect_interval):
            return False
        self._last_connect_attempt = now

        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        # reconnect_delay=0 disables pymodbus' own reconnect task: reconnecting is done here.
        self.client = AsyncModbusTcpClient(
            host=self.plant_host, port=self.plant_port,
            timeout=self.io_timeout, reconnect_delay=0,
        )
        try:
            connected = await asyncio.wait_for(self.client.connect(), timeout=self.io_timeout + 1)
        except Exception as e:
            connected = False
            logger.debug(f"Connect to physical model failed: {e}")
        if connected and self.client.connected:
            self._set_link(True)
            return True
        self._drop_connection("connect failed")
        return False

    async def connect_to_physical_model(self, host=None, port=None):
        """Make one connection attempt. The scan loop keeps retrying through read_inputs/write_outputs."""
        if host:
            self.plant_host = host
        if port:
            self.plant_port = int(port)
        logger.info(f"Connecting to physical model at {self.plant_host}:{self.plant_port}")
        self._last_connect_attempt = None
        return await self._ensure_connected()

    async def read_inputs(self):
        """Read sensor values from the physical model and update the sensor-fault state."""
        ok = False
        if await self._ensure_connected():
            try:
                result = await self.client.read_holding_registers(
                    address=self._offset('SensorTemp'), count=2, slave=1)
                if not result.isError():
                    inputs = self.plc_runtime.memory.inputs
                    inputs['RoomTemperature'] = decode_x10(result.registers[0], signed=True)
                    inputs['RoomHumidity'] = decode_x10(result.registers[1])
                    ok = True
                elif isinstance(result, ExceptionResponse):
                    logger.warning(f"Physical model rejected sensor read: {result}")
                else:
                    self._drop_connection(f"sensor read error: {result}")
            except Exception as e:
                self._drop_connection(f"sensor read exception: {e}")

        if ok:
            self.sensor_failures = 0
            self.sensor_valid = True
        else:
            self.sensor_failures += 1
        fault = self.sensor_fault
        if fault and self.sensor_failures == self.sensor_fault_limit:
            logger.error(f"Sensor fault: no valid plant data for {self.sensor_failures} scans")
        self.plc_runtime.memory.inputs['SensorFault'] = fault
        return ok

    async def write_outputs(self):
        """Write actuator commands to the physical model."""
        if not await self._ensure_connected():
            return False
        try:
            fan_speed = encode_uint(self.plc_runtime.memory.outputs.get('FanSpeed', 0), maximum=100)
            chiller_on = encode_uint(bool(self.plc_runtime.memory.outputs.get('ChillerOn', False)), maximum=1)
            result = await self.client.write_registers(
                address=self._offset('ActuatorFanSpeed'), values=[fan_speed, chiller_on], slave=1)
            if result.isError():
                if isinstance(result, ExceptionResponse):
                    logger.warning(f"Physical model rejected actuator write: {result}")
                else:
                    self._drop_connection(f"actuator write error: {result}")
                return False
            return True
        except Exception as e:
            self._drop_connection(f"actuator write exception: {e}")
            return False

    # ------------------------------------------------------------------ lifecycle / info

    async def stop(self):
        """Stop Modbus connections"""
        self.running = False

        if self.client:
            self.client.close()
            self.client = None

        if self.server:
            await self.server.shutdown()

        logger.info("Modbus interface stopped")

    def get_register_map_info(self):
        """Get information about register mapping"""
        return {
            'commands': {k: v for k, v in self.register_map.items() if 40001 <= v <= 40099},
            'status': {k: v for k, v in self.register_map.items() if 40101 <= v <= 40199},
            'sensors': {k: v for k, v in self.register_map.items() if 40201 <= v <= 40299},
            'actuators': {k: v for k, v in self.register_map.items() if 40301 <= v <= 40399}
        }
