import asyncio
import os
import socket
import sys

import pytest
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server.async_io import ModbusTcpServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("plc", "backend", "physical-model"):
    sys.path.insert(0, os.path.join(ROOT, sub))

ST_PROGRAM = os.path.join(ROOT, "plc", "programs", "hvac_control.st")


@pytest.fixture
def free_port():
    def _free():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    return _free


class FakePlant:
    """Minimal stand-in for the physical model's Modbus server: sensor registers can be set by
    the test, actuator registers can be inspected. Same addresses as physical_simulation.py."""

    SENSOR_TEMP, SENSOR_HUMIDITY, ACT_FAN, ACT_CHILLER = 200, 201, 300, 301

    def __init__(self, port):
        self.port = port
        self.store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 500), zero_mode=True)
        self.context = ModbusServerContext(slaves=self.store, single=True)
        self.server = None
        self.task = None

    def set_sensors(self, raw_temp, raw_humidity):
        self.store.setValues(3, self.SENSOR_TEMP, [raw_temp, raw_humidity])

    def actuators(self):
        return tuple(self.store.getValues(3, self.ACT_FAN, 2))

    async def start(self):
        self.server = ModbusTcpServer(context=self.context, address=("127.0.0.1", self.port))
        self.task = asyncio.create_task(self.server.serve_forever())
        await wait_for_port(self.port)

    async def stop(self):
        await self.server.shutdown()
        await asyncio.wait_for(self.task, 2)


async def wait_for_port(port, timeout=3.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            return
        except OSError:
            await asyncio.sleep(0.02)
    raise TimeoutError(f"port {port} never opened")
