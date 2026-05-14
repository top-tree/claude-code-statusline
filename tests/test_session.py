import json
import os
from multiprocessing import Process, Queue
from pathlib import Path

import pytest

from scripts import session
from tests.conftest import read_jsonl, write_json


@pytest.fixture()
def isolated_sessions(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    monkeypatch.setattr(session, "SESSIONS", str(root))
    return root


def write_transcript(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def assistant_line(
    message_id,
    model,
    input_tokens,
    cache_creation,
    cache_read,
    output,
    *,
    timestamp="2026-05-08T12:00:00.000Z",
    row_type="assistant",
):
    return json.dumps({
        "type": row_type,
        "timestamp": timestamp,
        "uuid": f"row-{message_id}-{output}",
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output,
            },
        },
    })


def session_dir(root, sid="sid"):
    return root / sid


def log_path(root, sid="sid"):
    return session_dir(root, sid) / "log.jsonl"


def summary_path(root, sid="sid"):
    return session_dir(root, sid) / "summary.json"


def test_get_summary_returns_empty_without_transcript_or_existing_summary(isolated_sessions):
    summary = session.get_summary("sid", None, {"symbol": "¥"})

    assert summary == {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0.0,
        "symbol": "¥",
        "models": {},
    }
    assert not log_path(isolated_sessions).exists()


def test_get_summary_uses_existing_summary_when_transcript_missing(isolated_sessions):
    write_json(summary_path(isolated_sessions), {
        "total_cached": 1,
        "total_new": 2,
        "total_output": 3,
        "total_cost": 4.0,
        "symbol": "¥",
        "models": {"m": {"cached": 1, "new": 2, "output": 3}},
    })

    assert session.get_summary("sid", "/no/such/transcript.jsonl", None)["total_cached"] == 1


def test_get_summary_ignores_existing_summary_with_wrong_shape(isolated_sessions):
    summary_path(isolated_sessions).parent.mkdir(parents=True)
    summary_path(isolated_sessions).write_text("[]", encoding="utf-8")

    summary = session.get_summary("sid", "/no/such/transcript.jsonl", {"symbol": "¥"})

    assert summary == {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0.0,
        "symbol": "¥",
        "models": {},
    }


def test_get_summary_ignores_corrupt_existing_summary(isolated_sessions):
    summary_path(isolated_sessions).parent.mkdir(parents=True)
    summary_path(isolated_sessions).write_text("{", encoding="utf-8")

    assert session.get_summary("sid", None, None) == {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0.0,
        "symbol": "$",
        "models": {},
    }


def test_empty_transcript_preserves_existing_summary_and_log(isolated_sessions, tmp_path):
    existing_summary = {
        "total_cached": 11,
        "total_new": 22,
        "total_output": 33,
        "total_cost": 0.44,
        "symbol": "¥",
        "models": {"deepseek-v4-pro": {"cached": 11, "new": 22, "output": 33}},
    }
    existing_log = [{
        "ts": "2026-05-08T12:00:00.000Z",
        "message_id": "old",
        "model": "deepseek-v4-pro",
        "cached": 11,
        "new": 22,
        "output": 33,
    }]
    write_json(summary_path(isolated_sessions), existing_summary)
    log_path(isolated_sessions).write_text(
        "\n".join(json.dumps(row) for row in existing_log) + "\n",
        encoding="utf-8",
    )
    transcript = write_transcript(tmp_path / "empty.jsonl", [])

    summary = session.get_summary("sid", str(transcript), {"symbol": "$"})

    assert summary == existing_summary
    assert read_jsonl(log_path(isolated_sessions)) == existing_log


def test_transcript_with_no_valid_assistant_usage_preserves_existing_cache(isolated_sessions, tmp_path):
    existing_summary = {
        "total_cached": 1,
        "total_new": 2,
        "total_output": 3,
        "total_cost": 4.0,
        "symbol": "¥",
        "models": {"m": {"cached": 1, "new": 2, "output": 3}},
    }
    existing_log = [{"message_id": "old", "model": "m", "cached": 1, "new": 2, "output": 3}]
    write_json(summary_path(isolated_sessions), existing_summary)
    log_path(isolated_sessions).write_text(json.dumps(existing_log[0]) + "\n", encoding="utf-8")
    transcript = write_transcript(tmp_path / "invalid-only.jsonl", [
        "{bad json",
        json.dumps({"type": "user", "message": {"role": "user"}}),
        assistant_line("synthetic", "<synthetic>", 1, 0, 0, 1),
        assistant_line("all-zero", "deepseek-v4-pro", 0, 0, 0, 0),
        json.dumps({"type": "assistant", "message": {"id": "missing-usage", "model": "m"}}),
    ])

    summary = session.get_summary("sid", str(transcript), {"symbol": "$"})

    assert summary == existing_summary
    assert read_jsonl(log_path(isolated_sessions)) == existing_log


def test_new_session_empty_transcript_does_not_write_empty_cache(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "empty.jsonl", [])

    summary = session.get_summary("sid", str(transcript), {"symbol": "¥"})

    assert summary == {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0.0,
        "symbol": "¥",
        "models": {},
    }
    assert not log_path(isolated_sessions).exists()
    assert not summary_path(isolated_sessions).exists()


def test_empty_transcript_does_not_delete_legacy_models_directory(isolated_sessions, tmp_path):
    legacy = session_dir(isolated_sessions) / "models" / "old-model"
    legacy.mkdir(parents=True)
    (legacy / "interactions.jsonl").write_text("{}\n", encoding="utf-8")
    transcript = write_transcript(tmp_path / "empty.jsonl", [])

    session.get_summary("sid", str(transcript), {"pricing": {}})

    assert (session_dir(isolated_sessions) / "models").exists()


def test_transcript_sync_writes_single_log_and_summary(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "session.jsonl", [
        "{bad json",
        json.dumps({"type": "user", "message": {"role": "user"}}),
        assistant_line("m1", "deepseek-v4-pro", 10, 2, 3, 4, timestamp="2026-05-08T12:00:01.000Z"),
        assistant_line("m2", "deepseek-v4-flash", 20, 0, 7, 8, timestamp="2026-05-08T12:00:02.000Z"),
    ])

    summary = session.get_summary("sid", str(transcript), {
        "symbol": "¥",
        "pricing": {
            "deepseek-v4-pro": {"input": 3.0, "cached_input": 0.5, "output": 6.0},
            "deepseek-v4-flash": {"input": 1.0, "cached_input": 0.2, "output": 2.0},
        },
    })

    assert read_jsonl(log_path(isolated_sessions)) == [
        {
            "ts": "2026-05-08T12:00:01.000Z",
            "message_id": "m1",
            "model": "deepseek-v4-pro",
            "cached": 3,
            "new": 12,
            "output": 4,
        },
        {
            "ts": "2026-05-08T12:00:02.000Z",
            "message_id": "m2",
            "model": "deepseek-v4-flash",
            "cached": 7,
            "new": 20,
            "output": 8,
        },
    ]
    assert summary["models"] == {
        "deepseek-v4-flash": {"cached": 7, "new": 20, "output": 8},
        "deepseek-v4-pro": {"cached": 3, "new": 12, "output": 4},
    }
    assert summary["total_cached"] == 10
    assert summary["total_new"] == 32
    assert summary["total_output"] == 12
    assert summary["total_cost"] == pytest.approx(0.0000989)


def test_to_int_handles_float_values_and_invalid_values():
    assert session._to_int("5.7") == 5
    assert session._to_int(5.7) == 5
    assert session._to_int("6") == 6
    assert session._to_int("") == 0
    assert session._to_int(None) == 0
    assert session._to_int("bad") == 0


def test_transcript_sync_coerces_float_token_strings(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "session.jsonl", [
        assistant_line("float-tokens", "deepseek-v4-pro", "5.7", "2.2", "3.9", "4.8"),
    ])

    summary = session.get_summary("sid", str(transcript), {"pricing": {}})

    assert read_jsonl(log_path(isolated_sessions)) == [{
        "ts": "2026-05-08T12:00:00.000Z",
        "message_id": "float-tokens",
        "model": "deepseek-v4-pro",
        "cached": 3,
        "new": 7,
        "output": 4,
    }]
    assert summary["models"]["deepseek-v4-pro"] == {"cached": 3, "new": 7, "output": 4}


def test_zero_output_with_billable_input_tokens_is_recorded(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "session.jsonl", [
        assistant_line("input-only", "deepseek-v4-pro", 100, 50, 25, 0),
    ])

    summary = session.get_summary("sid", str(transcript), {
        "pricing": {
            "deepseek-v4-pro": {"input": 3.0, "cached_input": 0.5, "output": 6.0},
        },
    })

    assert read_jsonl(log_path(isolated_sessions)) == [{
        "ts": "2026-05-08T12:00:00.000Z",
        "message_id": "input-only",
        "model": "deepseek-v4-pro",
        "cached": 25,
        "new": 150,
        "output": 0,
    }]
    assert summary["models"]["deepseek-v4-pro"] == {"cached": 25, "new": 150, "output": 0}
    assert summary["total_cached"] == 25
    assert summary["total_new"] == 150
    assert summary["total_output"] == 0
    assert summary["total_cost"] == pytest.approx(0.0004625)


def test_same_message_id_keeps_last_usage_and_does_not_duplicate(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "session.jsonl", [
        assistant_line("m1", "deepseek-v4-pro", 10, 0, 0, 4, timestamp="2026-05-08T12:00:01.000Z"),
        assistant_line("m1", "deepseek-v4-pro", 10, 5, 2, 9, timestamp="2026-05-08T12:00:02.000Z"),
        assistant_line("m1", "deepseek-v4-pro", 10, 5, 2, 9, timestamp="2026-05-08T12:00:03.000Z"),
    ])

    session.get_summary("sid", str(transcript), {"pricing": {}})

    assert read_jsonl(log_path(isolated_sessions)) == [{
        "ts": "2026-05-08T12:00:03.000Z",
        "message_id": "m1",
        "model": "deepseek-v4-pro",
        "cached": 2,
        "new": 15,
        "output": 9,
    }]


def test_model_switch_display_name_cannot_create_duplicate_usage(isolated_sessions, tmp_path):
    transcript = write_transcript(tmp_path / "session.jsonl", [
        assistant_line("pro-1", "deepseek-v4-pro", 10, 0, 0, 1),
        assistant_line("flash-1", "deepseek-v4-flash", 20, 0, 5, 2),
        assistant_line("flash-1", "deepseek-v4-flash", 20, 0, 5, 2),
        assistant_line("pro-2", "deepseek-v4-pro", 30, 0, 7, 3),
    ])

    summary = session.get_summary("sid", str(transcript), {"pricing": {}})

    assert [row["message_id"] for row in read_jsonl(log_path(isolated_sessions))] == [
        "pro-1",
        "flash-1",
        "pro-2",
    ]
    assert summary["models"]["deepseek-v4-pro"] == {"cached": 7, "new": 40, "output": 4}
    assert summary["models"]["deepseek-v4-flash"] == {"cached": 5, "new": 20, "output": 2}


def test_transcript_sync_includes_subagent_usage(isolated_sessions, tmp_path):
    project_dir = tmp_path / "project"
    transcript = write_transcript(project_dir / "sid.jsonl", [
        assistant_line("main-pro", "deepseek-v4-pro", 100, 10, 20, 30),
    ])
    write_transcript(project_dir / "sid" / "subagents" / "agent-1.jsonl", [
        assistant_line("sub-flash", "deepseek-v4-flash", 25, 0, 7, 8),
    ])

    summary = session.get_summary("sid", str(transcript), {
        "symbol": "¥",
        "pricing": {
            "deepseek-v4-pro": {"input": 3.0, "cached_input": 0.5, "output": 6.0},
            "deepseek-v4-flash": {"input": 1.0, "cached_input": 0.2, "output": 2.0},
        },
    })

    assert read_jsonl(log_path(isolated_sessions)) == [
        {
            "ts": "2026-05-08T12:00:00.000Z",
            "message_id": "main-pro",
            "model": "deepseek-v4-pro",
            "cached": 20,
            "new": 110,
            "output": 30,
        },
        {
            "ts": "2026-05-08T12:00:00.000Z",
            "message_id": "sub-flash",
            "model": "deepseek-v4-flash",
            "cached": 7,
            "new": 25,
            "output": 8,
        },
    ]
    assert summary["models"] == {
        "deepseek-v4-pro": {"cached": 20, "new": 110, "output": 30},
        "deepseek-v4-flash": {"cached": 7, "new": 25, "output": 8},
    }
    assert summary["total_cached"] == 27
    assert summary["total_new"] == 135
    assert summary["total_output"] == 38
    assert summary["total_cost"] == pytest.approx(0.0005624)


def test_transcript_sync_includes_subagent_usage_when_path_contains_glob_metacharacters(isolated_sessions, tmp_path):
    project_dir = tmp_path / "project[one]"
    transcript = write_transcript(project_dir / "sid.jsonl", [
        assistant_line("main-pro", "deepseek-v4-pro", 100, 0, 0, 10),
    ])
    write_transcript(project_dir / "sid" / "subagents" / "agent-1.jsonl", [
        assistant_line("sub-flash", "deepseek-v4-flash", 20, 0, 5, 6),
    ])

    summary = session.get_summary("sid", str(transcript), {"pricing": {}})

    assert [row["message_id"] for row in read_jsonl(log_path(isolated_sessions))] == [
        "main-pro",
        "sub-flash",
    ]
    assert summary["models"] == {
        "deepseek-v4-pro": {"cached": 0, "new": 100, "output": 10},
        "deepseek-v4-flash": {"cached": 5, "new": 20, "output": 6},
    }
    assert summary["total_cached"] == 5
    assert summary["total_new"] == 120
    assert summary["total_output"] == 16


def test_transcript_sync_deduplicates_message_ids_across_main_and_subagents(isolated_sessions, tmp_path):
    project_dir = tmp_path / "project"
    transcript = write_transcript(project_dir / "sid.jsonl", [
        assistant_line("shared", "deepseek-v4-pro", 10, 0, 1, 2),
    ])
    write_transcript(project_dir / "sid" / "subagents" / "agent-1.jsonl", [
        assistant_line("shared", "deepseek-v4-flash", 20, 0, 3, 4),
    ])

    summary = session.get_summary("sid", str(transcript), {"pricing": {}})

    assert read_jsonl(log_path(isolated_sessions)) == [{
        "ts": "2026-05-08T12:00:00.000Z",
        "message_id": "shared",
        "model": "deepseek-v4-flash",
        "cached": 3,
        "new": 20,
        "output": 4,
    }]
    assert summary["total_cached"] == 3
    assert summary["total_new"] == 20
    assert summary["total_output"] == 4


def test_transcript_sync_skips_non_billable_and_incomplete_rows(isolated_sessions, tmp_path):
    missing_id = json.dumps({
        "type": "assistant",
        "timestamp": "2026-05-08T12:00:01.000Z",
        "message": {
            "role": "assistant",
            "model": "deepseek-v4-pro",
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 1,
            },
        },
    })
    missing_usage = json.dumps({
        "type": "assistant",
        "timestamp": "2026-05-08T12:00:01.000Z",
        "message": {"id": "missing-usage", "role": "assistant", "model": "deepseek-v4-pro"},
    })
    transcript = write_transcript(tmp_path / "session.jsonl", [
        "",
        "[]",
        json.dumps({"type": "assistant", "message": "not-a-dict"}),
        assistant_line("user-ish", "deepseek-v4-pro", 1, 0, 0, 1, row_type="user"),
        assistant_line("synthetic", "<synthetic>", 1, 0, 0, 1),
        assistant_line("all-zero", "deepseek-v4-pro", 0, 0, 0, 0),
        missing_id,
        missing_usage,
        assistant_line("coerced", "deepseek-v4-pro", "bad", None, "6", "7"),
        assistant_line("kept", "deepseek-v4-pro", 2, 3, 4, 5),
    ])

    session.get_summary("sid", str(transcript), {"pricing": {}})

    rows = read_jsonl(log_path(isolated_sessions))
    assert [row["message_id"] for row in rows] == ["coerced", "kept"]
    assert rows[0] == {
        "ts": "2026-05-08T12:00:00.000Z",
        "message_id": "coerced",
        "model": "deepseek-v4-pro",
        "cached": 6,
        "new": 0,
        "output": 7,
    }


def test_transcript_sync_deletes_legacy_models_directory(isolated_sessions, tmp_path):
    legacy = session_dir(isolated_sessions) / "models" / "old-model"
    legacy.mkdir(parents=True)
    (legacy / "interactions.jsonl").write_text("{}\n", encoding="utf-8")
    transcript = write_transcript(tmp_path / "session.jsonl", [
        assistant_line("m1", "deepseek-v4-pro", 1, 2, 3, 4),
    ])

    session.get_summary("sid", str(transcript), {"pricing": {}})

    assert not (session_dir(isolated_sessions) / "models").exists()
    assert log_path(isolated_sessions).exists()


def test_build_summary_from_records_handles_missing_pricing_and_fallback_cached_price():
    records = [
        {"model": "priced", "cached": 10, "new": 20, "output": 30},
        {"model": "unpriced", "cached": 1, "new": 2, "output": 3},
    ]

    summary = session._build_summary_from_records(records, {
        "pricing": {"priced": {"input": 3.0, "output": 6.0}},
    })

    assert summary["symbol"] == "$"
    assert summary["models"] == {
        "priced": {"cached": 10, "new": 20, "output": 30},
        "unpriced": {"cached": 1, "new": 2, "output": 3},
    }
    assert summary["total_cost"] == pytest.approx(0.00027)


def worker_sync(root, transcript_path, queue):
    from scripts import session as worker_session

    worker_session.SESSIONS = str(root)
    try:
        worker_session.get_summary("sid", str(transcript_path), {"pricing": {}})
        queue.put(None)
    except Exception as exc:
        queue.put(repr(exc))


@pytest.mark.parametrize("run_index", range(20))
def test_concurrent_transcript_sync_is_stable(isolated_sessions, tmp_path, run_index):
    transcript = write_transcript(tmp_path / f"session-{run_index}.jsonl", [
        assistant_line(f"m{i}", "deepseek-v4-pro", i + 1, 0, i, i + 2)
        for i in range(30)
    ])
    queue = Queue()
    processes = [
        Process(target=worker_sync, args=(isolated_sessions, transcript, queue))
        for _ in range(4)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(10)

    errors = [queue.get(timeout=1) for _ in processes]
    assert errors == [None, None, None, None]
    assert all(process.exitcode == 0 for process in processes)
    assert len(read_jsonl(log_path(isolated_sessions))) == 30
    assert json.loads(summary_path(isolated_sessions).read_text())["total_output"] == sum(i + 2 for i in range(30))


def test_get_summary_handles_non_string_transcript_path(isolated_sessions):
    for bad_path in (123, [], True):
        summary = session.get_summary("sid", bad_path, {"symbol": "¥"})
        assert summary == {
            "total_cached": 0, "total_new": 0, "total_output": 0,
            "total_cost": 0.0, "symbol": "¥", "models": {},
        }


def test_empty_summary_handles_non_dict_config():
    for bad_cfg in ([], "str", 123):
        summary = session._empty_summary(bad_cfg)
        assert summary == {
            "total_cached": 0, "total_new": 0, "total_output": 0,
            "total_cost": 0.0, "symbol": "$", "models": {},
        }


def test_build_summary_ignores_non_dict_pricing_entry():
    records = [
        {"model": "int-price", "cached": 1000, "new": 1000, "output": 100},
        {"model": "ok", "cached": 500, "new": 500, "output": 50},
    ]

    summary = session._build_summary_from_records(records, {
        "pricing": {"int-price": 3, "ok": {"input": 1.0, "output": 2.0}},
    })

    assert summary["models"]["int-price"] == {"cached": 1000, "new": 1000, "output": 100}
    # Only the "ok" model contributes to cost
    # ok: cached 500/1M * 1.0 + new 500/1M * 1.0 + output 50/1M * 2.0 = 0.0005 + 0.0005 + 0.0001
    assert summary["total_cost"] == pytest.approx(0.0011)


def test_build_summary_handles_non_dict_pricing_value():
    records = [{"model": "m", "cached": 1000, "new": 1000, "output": 100}]

    summary = session._build_summary_from_records(records, {"pricing": "not-a-dict"})
    assert summary["total_cost"] == 0.0
    assert summary["models"]["m"] == {"cached": 1000, "new": 1000, "output": 100}


def test_build_summary_handles_non_dict_config():
    records = [{"model": "m", "cached": 1000, "new": 1000, "output": 100}]

    for bad_cfg in ([], "str", 123):
        summary = session._build_summary_from_records(records, bad_cfg)
        assert summary["total_cost"] == 0.0
        assert summary["symbol"] == "$"
