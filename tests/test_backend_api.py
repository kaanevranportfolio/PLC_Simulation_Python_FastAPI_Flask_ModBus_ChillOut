"""Backend HTTP routes against a fake Modbus client (no network)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dependencies
from routes import status, system


class FakeModbus:
    def __init__(self, connected=True):
        self.connected = connected
        self.writes = []
        self.regs = {40001: 1, 40002: 235, 40003: 450, 40004: 10, 40005: 50,
                     40101: 0xFFC9, 40102: 455, 40103: 70, 40104: 1, 40105: 1, 40106: 0}  # 40101 = -5.5 C

    async def test_connection(self):
        return self.connected

    async def write_register(self, address, value):
        self.writes.append((address, value))
        self.regs[address] = value

    async def read_holding_registers(self, address, count):
        return [self.regs[address + i] for i in range(count)]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(system.router)
    app.include_router(status.router)
    dependencies.system_state.update(plc_running=False, setpoint_temperature=22.0, setpoint_humidity=45.0)
    fake = FakeModbus()
    dependencies.modbus_client = fake
    yield TestClient(app), fake
    dependencies.modbus_client = None


def post(c, command, value=None):
    body = {"command": command}
    if value is not None:
        body["value"] = value
    return c.post("/api/control", json=body)


def test_setpoints_are_rounded_to_register_values(client):
    c, fake = client
    assert post(c, "set_temperature", 22.87).status_code == 200
    assert post(c, "set_humidity", 45).status_code == 200
    assert fake.writes == [(40002, 229), (40003, 450)]


@pytest.mark.parametrize("command,value", [
    ("set_temperature", 14.9), ("set_temperature", 30.1), ("set_temperature", -5),
    ("set_humidity", 29.0), ("set_humidity", 71.0), ("set_humidity", 1e6),
    ("set_temperature", None), ("set_humidity", None),
])
def test_out_of_range_or_missing_setpoints_are_rejected_without_a_write(client, command, value):
    c, fake = client
    assert post(c, command, value).status_code == 422
    assert fake.writes == []


@pytest.mark.parametrize("command,value", [("set_temperature", 15), ("set_temperature", 30),
                                           ("set_humidity", 30), ("set_humidity", 70)])
def test_range_limits_are_inclusive(client, command, value):
    c, fake = client
    assert post(c, command, value).status_code == 200


def test_start_stop_write_enable_register(client):
    c, fake = client
    post(c, "start"), post(c, "stop")
    assert fake.writes == [(40001, 1), (40001, 0)]


def test_plc_unreachable_gives_503_not_400(client):
    c, fake = client
    fake.connected = False
    assert post(c, "start").status_code == 503


def test_status_reads_enable_flag_setpoints_and_signed_temperature_from_the_plc(client):
    c, fake = client
    body = c.get("/api/status").json()
    assert body["plc_running"] is True                 # from register 40001, not backend memory
    assert body["setpoint_temperature"] == 23.5 and body["setpoint_humidity"] == 45.0
    assert body["room_temperature"] == -5.5 and body["room_humidity"] == 45.5
    assert body["fan_speed"] == 70 and body["chiller_status"] is True


def test_status_falls_back_to_cached_values_when_plc_is_down(client):
    c, fake = client
    fake.connected = False
    dependencies.system_state.update(plc_running=True, setpoint_temperature=21.0)
    body = c.get("/api/status").json()
    assert body["plc_running"] is True and body["setpoint_temperature"] == 21.0
