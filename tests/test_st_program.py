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


def scans(rt, n, **inputs):
    out = None
    for _ in range(n):
        out = run(rt, **inputs)
    return out


MIN_SCANS = 100  # MinOnScans / MinOffScans in hvac_control.st and PLCRuntime.MIN_*_SCANS


def test_hysteresis_keeps_cooling_until_below_lower_threshold(runtime):
    assert run(runtime, RoomTemperature=24.0)["ChillerOn"] == 1
    # inside the band (error between -1 and +1) the previous demand is kept, even after the minimum on time
    assert scans(runtime, MIN_SCANS + 20, RoomTemperature=22.5)["ChillerOn"] == 1
    assert scans(runtime, 1, RoomTemperature=21.5)["ChillerOn"] == 1
    # below setpoint - deadband the demand ends
    assert run(runtime, RoomTemperature=20.9)["ChillerOn"] == 0


def test_minimum_on_time(runtime):
    assert run(runtime, RoomTemperature=24.0)["ChillerOn"] == 1       # starts, timer = 0
    assert scans(runtime, MIN_SCANS - 1, RoomTemperature=20.0)["ChillerOn"] == 1
    out = run(runtime, RoomTemperature=20.0)
    assert out["ChillerOn"] == 0 and out["SystemStatus"] == 2
    assert out["FanSpeed"] == 20


def test_minimum_off_time(runtime):
    run(runtime, RoomTemperature=24.0)
    scans(runtime, MIN_SCANS, RoomTemperature=20.0)                    # chiller stops
    assert scans(runtime, MIN_SCANS - 1, RoomTemperature=25.0)["ChillerOn"] == 0   # demand again, too early
    assert run(runtime, RoomTemperature=25.0)["ChillerOn"] == 1


def test_disable_stops_immediately_and_restart_respects_minimum_off(runtime):
    run(runtime, RoomTemperature=24.0)
    out = run(runtime, SystemEnable=False, RoomTemperature=24.0)
    assert out["ChillerOn"] == 0 and out["FanSpeed"] == 0                 # operator stop ignores minimum on time
    assert scans(runtime, MIN_SCANS - 1, RoomTemperature=24.0)["ChillerOn"] == 0
    assert run(runtime, RoomTemperature=24.0)["ChillerOn"] == 1


def test_dehumidification_hysteresis(runtime):
    assert run(runtime, RoomHumidity=60.0)["ChillerOn"] == 1
    assert scans(runtime, MIN_SCANS + 5, RoomHumidity=42.0)["ChillerOn"] == 1   # inside band
    out = run(runtime, RoomHumidity=39.0)                                       # below setpoint - deadband
    assert out["ChillerOn"] == 0


def test_python_fallback_matches_st_program():
    """Same random input sequence into both implementations: identical outputs every scan."""
    import random
    for seed in range(6):
        rnd = random.Random(seed)
        st = PLCRuntime(STParser().parse(open(ST_PROGRAM).read()))
        py = PLCRuntime(None)
        inputs = dict(SystemEnable=True, SensorFault=False, RoomTemperature=22.0, RoomHumidity=45.0,
                      SetpointTemp=22.0, SetpointHumidity=45.0, TempDeadband=1.0, HumidityDeadband=5.0)
        for scan in range(3000):
            if scan % 40 == 0:
                inputs["RoomTemperature"] = rnd.choice([8.0, 20.5, 21.5, 22.0, 22.8, 23.5, 25.0, 31.0, 36.0])
                inputs["RoomHumidity"] = rnd.choice([18.0, 38.0, 42.0, 46.0, 52.0, 58.0, 85.0])
            if scan % 150 == 0:
                inputs["SystemEnable"] = rnd.random() > 0.2
                inputs["SensorFault"] = rnd.random() < 0.15
            a, b = run(st, **inputs), run(py, **inputs)
            assert a["ChillerOn"] == b["ChillerOn"], (seed, scan, a, b)
            assert a["SystemStatus"] == b["SystemStatus"] and a["AlarmActive"] == b["AlarmActive"], (seed, scan, a, b)
            assert abs(a["FanSpeed"] - b["FanSpeed"]) <= 1, (seed, scan, a, b)


def test_st_program_alarm_limits():
    rt = PLCRuntime(STParser().parse(open(ST_PROGRAM).read()))
    assert run(rt, RoomTemperature=36.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=9.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=22.0, RoomHumidity=85.0)["AlarmActive"] == 1
    assert run(rt, RoomTemperature=22.0, RoomHumidity=45.0)["AlarmActive"] == 0
