"""PLC <-> Modbus tests over real localhost sockets: a fake plant (sensor/actuator registers),
the PLC's own Modbus server + client, and the backend's ModbusClient as the operator side."""
import asyncio

import pytest

from conftest import ST_PROGRAM, FakePlant, wait_for_port
from main import PLCSimulator
from modbus_client import ModbusClient, scale_x10
from modbus_interface import ModbusInterface, decode_x10, encode_x10
from plc_runtime import PLCRuntime
from st_parser import STParser

# backend-side register addresses (4xxxx convention, same as backend/core/config.py)
ENABLE, SP_TEMP, SP_HUM, TEMP_DB, HUM_DB = 40001, 40002, 40003, 40004, 40005
ROOM_T, ROOM_H, FAN, CHILLER, STATUS, ALARM = 40101, 40102, 40103, 40104, 40105, 40106


class Rig:
    """PLC simulator (without its 100 ms loop: tests call scan_once) + fake plant + backend client."""

    def __init__(self, free_port, plant_up=True):
        self.plant = FakePlant(free_port())
        self.plc_port = free_port()
        self.plant_up = plant_up

    async def __aenter__(self):
        self.plc = PLCSimulator()
        self.plc.runtime = PLCRuntime(STParser().parse(open(ST_PROGRAM).read()))
        self.plc.modbus = ModbusInterface(
            self.plc.runtime, plant_host="127.0.0.1", plant_port=self.plant.port,
            server_port=self.plc_port, sensor_fault_limit=3, reconnect_interval=0.05, io_timeout=0.3)
        self.server_task = asyncio.create_task(self.plc.modbus.start_server())
        await wait_for_port(self.plc_port)
        if self.plant_up:
            self.plant.set_sensors(encode_x10(22.0, signed=True), encode_x10(45.0))
            await self.plant.start()
        self.backend = ModbusClient("127.0.0.1", self.plc_port)
        assert await self.backend.connect(max_retries=3, retry_delay=0.1)
        return self

    async def __aexit__(self, *exc):
        await self.backend.disconnect()
        await self.plc.modbus.stop()
        self.server_task.cancel()
        if self.plant.server is not None and not self.plant.task.done():
            await self.plant.stop()

    async def scans(self, n=1, pause=0.06):
        for _ in range(n):
            await self.plc.scan_once()
            await asyncio.sleep(pause)  # lets the reconnect rate limit elapse

    async def reg(self, address):
        return (await self.backend.read_holding_registers(address, 1))[0]


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 20))


def test_sensor_to_actuator_to_status_round_trip(free_port):
    async def scenario():
        async with Rig(free_port) as rig:
            rig.plant.set_sensors(encode_x10(24.0, signed=True), encode_x10(45.0))
            await rig.backend.write_register(ENABLE, 1)
            await rig.backend.write_register(SP_TEMP, scale_x10(22.0))
            await rig.scans(1)
            # error 2.0 -> chiller on, fan 30 + 20*2
            assert rig.plant.actuators() == (70, 1)
            assert await rig.reg(ROOM_T) == 240 and await rig.reg(ROOM_H) == 450
            assert await rig.reg(FAN) == 70 and await rig.reg(CHILLER) == 1
            assert await rig.reg(STATUS) == 1 and await rig.reg(ALARM) == 0
    run(scenario())


def test_command_takes_effect_in_the_same_scan(free_port):
    """Inputs (including backend commands) are all read before the program runs."""
    async def scenario():
        async with Rig(free_port) as rig:
            rig.plant.set_sensors(encode_x10(24.0, signed=True), encode_x10(45.0))
            await rig.scans(1)
            assert rig.plant.actuators() == (0, 0)          # disabled by default
            await rig.backend.write_register(ENABLE, 1)
            await rig.plc.scan_once()                       # exactly one scan later
            assert rig.plant.actuators() == (70, 1)
            await rig.backend.write_register(ENABLE, 0)
            await rig.plc.scan_once()
            assert rig.plant.actuators() == (0, 0)
    run(scenario())


def test_setpoint_scaling_and_defaults(free_port):
    async def scenario():
        async with Rig(free_port) as rig:
            await rig.scans(1)
            inp = rig.plc.runtime.memory.inputs
            assert (inp["SetpointTemp"], inp["SetpointHumidity"], inp["TempDeadband"], inp["HumidityDeadband"]) \
                == (22.0, 45.0, 1.0, 5.0)
            await rig.backend.write_register(SP_TEMP, scale_x10(22.87))
            await rig.scans(1)
            assert inp["SetpointTemp"] == 22.9
    run(scenario())


def test_negative_temperature_is_signed_end_to_end(free_port):
    async def scenario():
        async with Rig(free_port) as rig:
            rig.plant.set_sensors(encode_x10(-5.5, signed=True), encode_x10(45.0))
            await rig.backend.write_register(ENABLE, 1)
            await rig.scans(1)
            assert rig.plc.runtime.memory.inputs["RoomTemperature"] == -5.5
            status = await rig.backend.read_system_status()
            assert status["room_temperature"] == -5.5
            assert status["alarm_active"] is True          # below 10 C
    run(scenario())


def test_sensor_fault_before_plant_is_up_then_recovers(free_port):
    async def scenario():
        async with Rig(free_port, plant_up=False) as rig:
            await rig.backend.write_register(ENABLE, 1)
            await rig.scans(5)
            assert rig.plc.modbus.sensor_fault
            assert rig.plc.runtime.memory.inputs["SensorFault"] is True
            assert await rig.reg(ALARM) == 1 and await rig.reg(FAN) == 0 and await rig.reg(CHILLER) == 0
            # plant comes up later; PLC must find it by itself
            rig.plant.set_sensors(encode_x10(24.0, signed=True), encode_x10(45.0))
            await rig.plant.start()
            await rig.scans(6)
            assert not rig.plc.modbus.sensor_fault
            assert rig.plant.actuators() == (70, 1)
            assert await rig.reg(ALARM) == 0
    run(scenario())


def test_stale_sensor_data_fails_safe_and_reconnects(free_port):
    async def scenario():
        async with Rig(free_port) as rig:
            rig.plant.set_sensors(encode_x10(24.0, signed=True), encode_x10(45.0))
            await rig.backend.write_register(ENABLE, 1)
            await rig.scans(2)
            assert rig.plant.actuators() == (70, 1) and not rig.plc.modbus.sensor_fault

            await rig.plant.stop()                          # plant disappears
            await rig.scans(2)
            assert not rig.plc.modbus.sensor_fault          # fewer than sensor_fault_limit (3) failures so far
            await rig.scans(3)
            assert rig.plc.modbus.sensor_fault
            assert await rig.reg(ALARM) == 1 and await rig.reg(FAN) == 0 and await rig.reg(CHILLER) == 0
            assert await rig.reg(ROOM_T) == 240             # last known value is still published

            await rig.plant.start()                         # plant returns on the same port
            await rig.scans(6)
            assert not rig.plc.modbus.sensor_fault
            assert rig.plant.actuators() == (70, 1)
            assert await rig.reg(ALARM) == 0
    run(scenario())


def test_status_registers_are_clamped_to_register_ranges(free_port):
    async def scenario():
        async with Rig(free_port) as rig:
            await rig.scans(1)
            rig.plc.runtime.memory.outputs["FanSpeed"] = 250.7
            rig.plc.modbus.write_status()
            assert await rig.reg(FAN) == 100
            rig.plc.runtime.memory.outputs["FanSpeed"] = -4
            rig.plc.modbus.write_status()
            assert await rig.reg(FAN) == 0
    run(scenario())
