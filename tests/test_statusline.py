import io
import json
import os
import re
import runpy
import sys
from pathlib import Path

import statusline


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(value):
    return ANSI_RE.sub("", value)


def run_main(monkeypatch, payload):
    stdin = io.StringIO(payload)
    stdout = io.StringIO()
    monkeypatch.setattr(statusline.sys, "stdin", stdin)
    monkeypatch.setattr(statusline.sys, "stdout", stdout)
    statusline.main()
    return stdout.getvalue()


def fake_zero_summary():
    return {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0,
        "symbol": "$",
    }


def test_main_prints_ellipsis_for_invalid_json(monkeypatch):
    assert run_main(monkeypatch, "{") == "..."


def test_main_parses_full_claude_payload(monkeypatch):
    calls = []

    def fake_get_summary(sid, transcript_path, cfg):
        calls.append((sid, transcript_path, cfg))
        return {
            "total_cached": 23424,
            "total_new": 23848,
            "total_output": 510,
            "total_cost": 0.0123,
            "symbol": "¥",
        }

    monkeypatch.setattr(statusline, "load_config", lambda: {"pricing": {}})
    monkeypatch.setattr(statusline, "get_summary", fake_get_summary)
    payload = Path("tests/fixtures/statusline_full.json").read_text()

    rendered = run_main(monkeypatch, payload)

    assert calls == [("fixture-session", "tests/fixtures/transcript_session.jsonl", {"pricing": {}})]
    assert "deepseek-v4-pro" in rendered
    assert "[1m]" not in rendered
    assert "¥0.01" in rendered
    assert "~/project" in rendered


def test_main_renders_only_total_cost_for_multi_model_summary(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: {"pricing": {}})
    monkeypatch.setattr(statusline, "get_summary", lambda *args: {
        "total_cached": 200,
        "total_new": 300,
        "total_output": 40,
        "total_cost": 0.604,
        "symbol": "¥",
        "models": {
            "deepseek-v4-pro": {"cached": 100, "new": 200, "output": 30},
            "deepseek-v4-flash": {"cached": 100, "new": 100, "output": 10},
        },
    })
    payload = json.dumps({
        "model": {"display_name": "deepseek-v4-pro"},
        "session_id": "sid",
        "cwd": "/tmp/work",
    })

    rendered = strip_ansi(run_main(monkeypatch, payload))

    assert "¥0.60" in rendered
    assert "+flash" not in rendered
    assert "deepseek-v4-flash" not in rendered


def test_main_uses_model_id_and_hides_zero_cost(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": {"id": "model-id"},
        "context_window": {"current_usage": {}},
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "model-id" in rendered
    assert "$" not in rendered
    assert "/tmp/work" in rendered


def test_main_accepts_string_model(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": "claude-sonnet-4-6 [1m]",
        "session_id": "sid",
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "claude-sonnet-4-6" in rendered
    assert "[1m]" not in rendered


def test_main_handles_unexpected_model_shape(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": ["not", "a", "model"],
        "session_id": "sid",
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "?" in rendered
    assert "/tmp/work" in rendered


def test_main_accepts_string_effort(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": {"id": "model-id"},
        "effort": "high",
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "high" in rendered
    assert "model-id" in rendered


def test_main_handles_unexpected_effort_context_and_workspace_shapes(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": {"id": "model-id"},
        "effort": ["not", "a", "level"],
        "context_window": "not-a-dict",
        "workspace": "not-a-dict",
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "model-id" in rendered
    assert "0/0" in strip_ansi(rendered)
    assert "/tmp/work" in rendered


def test_main_coerces_string_context_tokens(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": "test",
        "context_window": {
            "total_input_tokens": "10",
            "context_window_size": "100",
        },
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "test" in rendered
    assert "10" in strip_ansi(rendered)
    assert "100" in strip_ansi(rendered)


def test_main_coerces_null_and_negative_context_tokens(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": "test",
        "context_window": {
            "total_input_tokens": None,
            "context_window_size": -5,
        },
        "cwd": "/tmp/work",
    })

    rendered = run_main(monkeypatch, payload)

    assert "test" in rendered
    assert "0/0" in strip_ansi(rendered)


def test_main_rejects_path_traversal_session_id(monkeypatch):
    calls = []

    def fake_get_summary(sid, transcript_path, cfg):
        calls.append(sid)
        return fake_zero_summary()

    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", fake_get_summary)

    for bad_sid in ("", "../outside", "/etc/passwd", "sub/../../../root", "..", "."):
        calls.clear()
        payload = json.dumps({
            "model": "test",
            "session_id": bad_sid,
            "cwd": "/tmp/work",
        })
        run_main(monkeypatch, payload)
        assert calls == ["unknown"], f"session_id {bad_sid!r} not sanitized"


def test_main_accepts_safe_session_ids(monkeypatch):
    calls = []

    def fake_get_summary(sid, transcript_path, cfg):
        calls.append(sid)
        return fake_zero_summary()

    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", fake_get_summary)

    payload = json.dumps({
        "model": "test",
        "session_id": "abc-123_ghi.jkl",
        "cwd": "/tmp/work",
    })
    run_main(monkeypatch, payload)
    assert calls == ["abc-123_ghi.jkl"]


def test_main_handles_non_string_transcript_path(monkeypatch):
    calls = []

    def fake_get_summary(sid, transcript_path, cfg):
        calls.append((sid, transcript_path))
        return fake_zero_summary()

    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", fake_get_summary)

    for bad_path in (123, [], True):
        calls.clear()
        payload = json.dumps({
            "model": "test",
            "session_id": "sid",
            "transcript_path": bad_path,
            "cwd": "/tmp/work",
        })
        run_main(monkeypatch, payload)
        assert calls[0] == ("sid", None), f"transcript_path {bad_path!r} not coerced to None"


def test_main_handles_non_string_cwd(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: None)
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())
    payload = json.dumps({
        "model": {"id": "model-id"},
        "workspace": {"current_dir": 123},
        "cwd": ["not", "a", "path"],
    })

    rendered = run_main(monkeypatch, payload)

    assert "model-id" in rendered
    assert "\033[37m?\033[0m" in rendered


def test_main_handles_minimal_payload(monkeypatch):
    monkeypatch.setattr(statusline, "load_config", lambda: {"symbol": "$"})
    monkeypatch.setattr(statusline, "get_summary", lambda *args: fake_zero_summary())

    rendered = run_main(monkeypatch, Path("tests/fixtures/statusline_minimal.json").read_text())

    assert "?" in rendered
    assert os.path.basename(os.getcwd()) not in rendered


def test_module_main_guard_invokes_main(monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO("{"))
    monkeypatch.setattr(sys, "stdout", stdout)

    runpy.run_path("statusline.py", run_name="__main__")

    assert stdout.getvalue() == "..."
