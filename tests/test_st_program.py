import pytest

from conftest import ST_PROGRAM
from plc_runtime import PLCRuntime
from st_parser import STParser


@pytest.fixture(params=["st", "default"])
def runtime(request):
    """The same behaviour is expected from the ST program and from the Python fallback logic."""
    if request.param == "st":
        program = STParser().parse(open(ST_PROGRAM).read())
        assert program is not None
        return PLCRuntime(program)
    return PLCRuntime(None)


def run(rt, **inputs):
    base = dict(SystemEnable=True, SensorFault=False, RoomTemperature=22.0, RoomHumidity=45.0,
                SetpointTemp=22.0, SetpointHumidity=45.0, TempDeadband=1.0, HumidityDeadband=5.0)
    base.update(inputs)
    rt.memory.inputs.update(base)
    rt.execute_cycle()
    return {k: float(v) for k, v in rt.memory.outputs.items()}


def test_sensor_fault_is_failsafe_and_alarms(runtime):
    out = run(runtime, SensorFault=True, RoomTemperature=30.0)
    assert out["FanSpeed"] == 0 and out["ChillerOn"] == 0 and out["SystemStatus"] == 0
    assert out["AlarmActive"] == 1


def test_fault_is_active_before_first_scan_update(runtime):
    # SensorFault defaults to TRUE: nothing runs until the I/O layer says data is valid
    assert runtime.memory.inputs["SensorFault"] is True


def test_disabled(runtime):
    out = run(runtime, SystemEnable=False, RoomTemperature=30.0)
    assert (out["FanSpeed"], out["ChillerOn"], out["SystemStatus"], out["AlarmActive"]) == (0, 0, 0, 0)


def test_idle_inside_deadband(runtime):
    out = run(runtime, RoomTemperature=22.9)
    assert (out["FanSpeed"], out["ChillerOn"], out["SystemStatus"]) == (20, 0, 2)


def test_cooling_fan_scales_with_error_and_clamps(runtime):
    out = run(runtime, RoomTemperature=24.0)  # error 2.0 -> 30 + 20*2
    assert (out["FanSpeed"], out["ChillerOn"], out["SystemStatus"]) == (70, 1, 1)
    assert run(runtime, RoomTemperature=30.0)["FanSpeed"] == 100


def test_dehumidification(runtime):
    out = run(runtime, RoomHumidity=60.0)
    assert (out["FanSpeed"], out["ChillerOn"], out["SystemStatus"]) == (50, 1, 1)


def test_no_state_chiller_follows_error(runtime):
    assert run(runtime, RoomTemperature=24.0)["ChillerOn"] == 1
    assert run(runtime, RoomTemperature=22.9)["ChillerOn"] == 0  # deadband threshold only, no latch


def test_st_program_alarm_limits():
    rt = PLCRuntime(STParser().parse(open(ST_PROGRAM).read()))
    assert run(rt, RoomTemperature=36.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=9.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=22.0, RoomHumidity=85.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=22.0, RoomHumidity=45.0)["AlarmActive"] == 0
