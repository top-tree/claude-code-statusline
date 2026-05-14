#!/usr/bin/env python3
"""Claude Code statusline — thin entry point.

Config: ~/.claude/custom-statusline/config.json
Session data stored under ~/.claude/custom-statusline/sessions/
"""
import json
import sys
import os

from scripts.config import load_config
from scripts.session import _to_int, get_summary
from scripts.display import build_statusline


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("...", end="")
        return

    # --- parse input ---
    model_data = data.get("model")
    if isinstance(model_data, dict):
        model_raw = model_data.get("display_name") or model_data.get("id") or "?"
    elif isinstance(model_data, str):
        model_raw = model_data
    else:
        model_raw = "?"
    model = model_raw.split("[")[0].strip()

    effort_data = data.get("effort")
    if isinstance(effort_data, dict):
        effort = effort_data.get("level") or "-"
    elif isinstance(effort_data, str):
        effort = effort_data
    else:
        effort = "-"

    cw_data = data.get("context_window")
    cw = cw_data if isinstance(cw_data, dict) else {}
    ctx_used = max(_to_int(cw.get("total_input_tokens")), 0)
    ctx_total = max(_to_int(cw.get("context_window_size")), 0)

    workspace_data = data.get("workspace")
    workspace_cwd = workspace_data.get("current_dir") if isinstance(workspace_data, dict) else None
    top_cwd = data.get("cwd")
    cwd = workspace_cwd if isinstance(workspace_cwd, str) and workspace_cwd else top_cwd
    if not isinstance(cwd, str) or not cwd:
        cwd = "?"
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    # --- session stats ---
    sid = data.get("session_id", "unknown")
    if not isinstance(sid, str) or not sid or sid in (".", "..") or "/" in sid or "\\" in sid:
        sid = "unknown"

    cfg = load_config()
    transcript_path = data.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        transcript_path = None
    summary = get_summary(sid, transcript_path, cfg)

    total_in = summary["total_cached"] + summary["total_new"]
    hit_rate = summary["total_cached"] / total_in * 100 if total_in > 0 else 0

    # --- cost ---
    cost_str = ""
    if cfg and summary.get("total_cost", 0) > 0:
        c = summary["total_cost"]
        symbol = summary.get("symbol", "$")
        cost_str = f"{symbol}{c:.4f}" if c < 0.01 else f"{symbol}{c:.2f}"

    # --- render ---
    print(build_statusline(
        model=model,
        effort=effort,
        ctx_used=ctx_used,
        ctx_total=ctx_total,
        total_cached=summary["total_cached"],
        total_new=summary["total_new"],
        total_output=summary["total_output"],
        hit_rate=hit_rate,
        cost_str=cost_str,
        cwd=cwd,
    ), end="")


if __name__ == "__main__":
    main()
