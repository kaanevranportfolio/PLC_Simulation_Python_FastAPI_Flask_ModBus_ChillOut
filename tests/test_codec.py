from modbus_interface import decode_x10, encode_uint, encode_x10
from modbus_client import scale_x10, to_signed16


def test_rounding_not_truncation():
    # int() truncation gives 228 for 22.87; rounding to nearest gives 229
    assert int(22.87 * 10) == 228
    assert encode_x10(22.87) == 229
    assert scale_x10(22.87) == 229
    # values with 0.1 resolution survive either way (checked for every register value)
    assert all(encode_x10(decode_x10(r)) == r for r in range(0x10000))


def test_unsigned_roundtrip_and_saturation():
    assert decode_x10(encode_x10(45.0)) == 45.0
    assert encode_x10(-1.0) == 0
    assert encode_x10(1e9) == 0xFFFF


def test_signed_temperature_roundtrip():
    for t in (-30.0, -5.5, -0.1, 0.0, 22.8, 80.0):
        assert decode_x10(encode_x10(t, signed=True), signed=True) == t
    assert encode_x10(-5.5, signed=True) == 0x10000 - 55
    assert to_signed16(encode_x10(-5.5, signed=True)) == -55
    assert encode_x10(-1e9, signed=True) == 0x8000  # saturates at int16 min


def test_encode_uint_clamps():
    assert encode_uint(70.4, maximum=100) == 70
    assert encode_uint(250, maximum=100) == 100
    assert encode_uint(-3, maximum=100) == 0
    assert encode_uint(True, maximum=1) == 1
