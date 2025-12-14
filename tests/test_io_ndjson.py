import io, json
from core.io_ndjson import _coerce_ms, _round_floats, write_rows

def test_coerce_ms_various():
    assert _coerce_ms("12") == 12
    assert _coerce_ms(12.7) == 13
    assert _coerce_ms(None) == 0
    assert _coerce_ms("bad") == 0

def test_round_floats_nested():
    obj = {"a": 1.2349, "b": [2.3456, {"c": 3.999}], "d": "x"}
    out = _round_floats(obj)
    assert out["a"] == 1.23
    assert out["b"][0] == 2.35
    assert out["b"][1]["c"] == 4.0
    assert out["d"] == "x"

def test_write_rows_rounds_and_coerces():
    buf = io.StringIO()
    rows = [
        {"x": 1.2345, "y_latency": "15"},
        {"x": 2.0, "z_latency": 9.6},
    ]
    write_rows(rows, out=buf)
    lines = buf.getvalue().strip().splitlines()
    assert len(lines) == 2
    a = json.loads(lines[0])
    b = json.loads(lines[1])
    assert a["x"] == 1.23 and a["y_latency"] == 15
    assert b["x"] == 2.0 and b["z_latency"] == 10
