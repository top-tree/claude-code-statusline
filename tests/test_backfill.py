import json
from pathlib import Path

import pytest


SESSION = Path("sessions/0ab3cba5-0cad-4173-811b-60a70e9010ce")
LOG = SESSION / "log.jsonl"
SUMMARY = SESSION / "summary.json"


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_current_session_uses_single_log_and_removed_legacy_models():
    rows = read_rows(LOG)
    pro_rows = [r for r in rows if r["model"] == "deepseek-v4-pro"]
    flash_rows = [r for r in rows if r["model"] == "deepseek-v4-flash"]
    pro_tuples = {(r["cached"], r["new"], r["output"]) for r in pro_rows}

    assert not (SESSION / "models").exists()
    assert len(rows) == 77
    assert len(pro_rows) == 72
    assert len(flash_rows) == 5
    assert {
        (90624, 887, 629),
        (92032, 203, 382),
        (99072, 1176, 1522),
        (120960, 925, 807),
        (121856, 886, 139),
    }.issubset(pro_tuples)


def test_current_session_summary_matches_cc_switch_totals():
    summary = json.loads(SUMMARY.read_text())

    assert summary["total_cached"] == 7_496_192
    assert summary["total_new"] == 178_603
    assert summary["total_output"] == 132_514
    assert summary["total_cost"] == pytest.approx(1.39360956)
    assert summary["models"]["deepseek-v4-pro"] == {
        "cached": 7_305_344,
        "new": 135_730,
        "output": 123_017,
    }
    assert summary["models"]["deepseek-v4-flash"] == {
        "cached": 190_848,
        "new": 42_873,
        "output": 9_497,
    }


def test_no_legacy_model_directories_remain():
    assert not list(Path("sessions").glob("*/models"))
