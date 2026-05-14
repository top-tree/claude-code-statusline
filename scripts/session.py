"""Transcript-backed session usage log and summary."""
from contextlib import contextmanager
import fcntl
import json
import os
import shutil
from pathlib import Path

from . import SESSIONS


def _session_dir(sid):
    return os.path.join(SESSIONS, sid)


def _log_path(sid):
    return os.path.join(_session_dir(sid), "log.jsonl")


def _summary_path(sid):
    return os.path.join(_session_dir(sid), "summary.json")


def _legacy_models_dir(sid):
    return os.path.join(_session_dir(sid), "models")


@contextmanager
def _session_lock(sid):
    """Serialize all writes for one Claude Code session."""
    session_dir = _session_dir(sid)
    os.makedirs(session_dir, exist_ok=True)
    lock_path = os.path.join(session_dir, ".lock")
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _to_int(value):
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _empty_summary(cfg):
    if not isinstance(cfg, dict):
        cfg = None
    return {
        "total_cached": 0,
        "total_new": 0,
        "total_output": 0,
        "total_cost": 0.0,
        "symbol": (cfg or {}).get("symbol", "$"),
        "models": {},
    }


def _assistant_usage_record(obj):
    if obj.get("type") != "assistant":
        return None

    message = obj.get("message")
    if not isinstance(message, dict):
        return None

    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    message_id = message.get("id")
    model = message.get("model")
    cached = _to_int(usage.get("cache_read_input_tokens"))
    new = (
        _to_int(usage.get("input_tokens")) +
        _to_int(usage.get("cache_creation_input_tokens"))
    )
    output = _to_int(usage.get("output_tokens"))
    if not message_id or not model or model == "<synthetic>":
        return None
    if cached == 0 and new == 0 and output == 0:
        return None

    return {
        "ts": obj.get("timestamp", ""),
        "message_id": message_id,
        "model": model,
        "cached": cached,
        "new": new,
        "output": output,
    }


def _records_from_transcript(transcript_path):
    by_message_id = {}
    order = []

    for record in _iter_transcript_records(transcript_path):
        message_id = record["message_id"]
        if message_id not in by_message_id:
            order.append(message_id)
        by_message_id[message_id] = record

    return [by_message_id[message_id] for message_id in order]


def _iter_transcript_records(transcript_path):
    with open(transcript_path, encoding="utf-8") as transcript:
        for line in transcript:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue

            record = _assistant_usage_record(obj)
            if record is None:
                continue
            yield record


def _transcript_paths(transcript_path):
    yield transcript_path

    base, ext = os.path.splitext(transcript_path)
    if ext != ".jsonl":
        return

    subagents = Path(base, "subagents")
    for path in sorted(subagents.glob("*.jsonl")):
        if path.is_file():
            yield str(path)


def _records_from_transcripts(transcript_paths):
    by_message_id = {}
    order = []

    for transcript_path in transcript_paths:
        for record in _iter_transcript_records(transcript_path):
            message_id = record["message_id"]
            if message_id not in by_message_id:
                order.append(message_id)
            by_message_id[message_id] = record

    return [by_message_id[message_id] for message_id in order]


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _load_summary_or_empty(sid, cfg):
    try:
        with open(_summary_path(sid), encoding="utf-8") as f:
            summary = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _empty_summary(cfg)
    if not isinstance(summary, dict):
        return _empty_summary(cfg)
    return summary


def _build_summary_from_records(records, cfg):
    if not isinstance(cfg, dict):
        cfg = None
    models = {}
    total_cached = total_new = total_output = 0
    total_cost = 0.0
    pricing = (cfg or {}).get("pricing", {})
    if not isinstance(pricing, dict):
        pricing = {}

    for record in records:
        model = record["model"]
        model_totals = models.setdefault(model, {"cached": 0, "new": 0, "output": 0})
        model_totals["cached"] += record["cached"]
        model_totals["new"] += record["new"]
        model_totals["output"] += record["output"]

        total_cached += record["cached"]
        total_new += record["new"]
        total_output += record["output"]

        prices = pricing.get(model)
        if isinstance(prices, dict):
            total_cost += (
                record["cached"] / 1_000_000 * prices.get("cached_input", prices.get("input", 0)) +
                record["new"] / 1_000_000 * prices.get("input", 0) +
                record["output"] / 1_000_000 * prices.get("output", 0)
            )

    return {
        "total_cached": total_cached,
        "total_new": total_new,
        "total_output": total_output,
        "total_cost": total_cost,
        "symbol": (cfg or {}).get("symbol", "$"),
        "models": models,
    }


def get_summary(sid, transcript_path, cfg):
    """Sync usage from Claude Code's transcript_path and return the aggregate summary."""
    with _session_lock(sid):
        if not isinstance(transcript_path, str) or not transcript_path or not os.path.isfile(transcript_path):
            return _load_summary_or_empty(sid, cfg)

        records = _records_from_transcripts(_transcript_paths(transcript_path))
        if not records:
            return _load_summary_or_empty(sid, cfg)

        summary = _build_summary_from_records(records, cfg)
        _write_jsonl(_log_path(sid), records)
        _write_json(_summary_path(sid), summary)

        legacy_models = _legacy_models_dir(sid)
        if os.path.isdir(legacy_models):
            shutil.rmtree(legacy_models)

        return summary
