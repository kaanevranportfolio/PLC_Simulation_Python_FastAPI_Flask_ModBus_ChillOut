import pytest
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext

import physical_simulation as sim
from conftest import ST_PROGRAM
from modbus_interface import decode_x10
from plc_runtime import PLCRuntime
from st_parser import STParser
from thermal_model import ThermalModel


def closed_loop(outside_temp, hours=2.0, start=22.0):
    """ST program + thermal model, one PLC decision per 1 s model step."""
    rt = PLCRuntime(STParser().parse(open(ST_PROGRAM).read()))
    m = ThermalModel()
    m.room_temperature, m.room_humidity = start, 50.0
    m.set_outside_conditions(outside_temp, 50.0)
    lo = hi = start
    for _ in range(int(hours * 3600)):
        rt.memory.inputs.update(SystemEnable=True, SensorFault=False, RoomTemperature=float(m.room_temperature),
                                RoomHumidity=float(m.room_humidity), SetpointTemp=22.0,
                                SetpointHumidity=50.0, TempDeadband=1.0, HumidityDeadband=5.0)
        rt.execute_cycle()
        m.set_fan_speed(int(rt.memory.outputs["FanSpeed"]))
        m.set_chiller_state(bool(rt.memory.outputs["ChillerOn"]))
        m.step(1.0)
        lo, hi = min(lo, m.room_temperature), max(hi, m.room_temperature)
    return lo, hi


def test_step_is_one_second_explicit_euler():
    m = ThermalModel()
    m.room_temperature, m.outside_temperature = 20.0, 20.0
    m.step(1.0)
    # only internal gains (100 W) act when there is no gradient and no HVAC
    expected = 100 / (m.room_volume * m.air_density * m.air_specific_heat)
    assert m.room_temperature == pytest.approx(20.0 + expected)


def test_chiller_is_not_absurdly_strong():
    m = ThermalModel()
    m.room_temperature = 22.0
    m.set_outside_conditions(25.0, 50.0)
    m.set_chiller_state(True)
    for _ in range(60):
        m.step(1.0)
    assert m.room_temperature > 10.0  # was about -4 C after one minute at 20 kW


@pytest.mark.parametrize("outside", [25.0, 28.0, 30.0])
def test_closed_loop_holds_setpoint_band_when_outside_is_warmer(outside):
    lo, hi = closed_loop(outside)
    assert lo > 20.0, (lo, hi)
    assert hi < 24.5, (lo, hi)


def test_update_once_publishes_signed_unclamped_temperature():
    ctx = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 500), zero_mode=True)
    sim.thermal_model.room_temperature = -3.7
    sim.thermal_model.room_humidity = 50.0
    sim.weather_conditions.update(temperature=-3.7, humidity=50.0)
    ctx.setValues(3, sim.REGISTER_MAP["actuator_fan"], [0, 0])
    t, h, fan, chiller = sim.update_once(ctx)
    raw_t = ctx.getValues(3, sim.REGISTER_MAP["sensor_temp"], 1)[0]
    raw_h = ctx.getValues(3, sim.REGISTER_MAP["sensor_humidity"], 1)[0]
    assert decode_x10(raw_t, signed=True) == pytest.approx(round(t, 1))
    assert decode_x10(raw_t, signed=True) < 0  # not clamped to 10..50
    assert decode_x10(raw_h) == pytest.approx(round(h, 1))


def test_update_once_applies_actuator_registers():
    ctx = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 500), zero_mode=True)
    ctx.setValues(3, sim.REGISTER_MAP["actuator_fan"], [180, 1])
    sim.update_once(ctx)
    assert sim.thermal_model.fan_speed == 100   # clamped by the model
    assert sim.thermal_model.chiller_on is True


def test_no_heating_room_drifts_to_outside_when_colder():
    """The plant is cooling-only: below the setpoint nothing warms the room (documented limitation)."""
    lo, hi = closed_loop(15.0, hours=1.0)
    assert lo < 18.0
