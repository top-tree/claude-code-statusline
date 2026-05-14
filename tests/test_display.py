from scripts import display


def strip_ansi_fragment(value):
    for code in ("\033[0m", "\033[37m", "\033[38;5;141m", "\033[38;5;114m", "\033[33m", "\033[31m", "\033[90m"):
        value = value.replace(code, "")
    return value


def test_fmt_boundaries():
    assert display.fmt(0) == "0"
    assert display.fmt(999) == "999"
    assert display.fmt(1000) == "1.0K"
    assert display.fmt(999949) == "999.9K"
    assert display.fmt(999950) == "1.0M"
    assert display.fmt(999999) == "1.0M"
    assert display.fmt(1_000_000) == "1.0M"


def test_ctx_bar_empty_when_total_is_zero():
    assert display.ctx_bar(10, 0) == ""
    assert display.ctx_col(10, 0) == display.GRAY


def test_ctx_bar_thresholds_and_minimum_visible_segment():
    assert "█" in strip_ansi_fragment(display.ctx_bar(1, 1000))
    assert "\033[38;5;114m" in display.ctx_bar(49, 100)
    assert "\033[33m" in display.ctx_bar(50, 100)
    assert "\033[31m" in display.ctx_bar(80, 100)
    assert strip_ansi_fragment(display.ctx_bar(150, 100)) == "[██████████]"


def test_build_statusline_without_cost():
    rendered = strip_ansi_fragment(display.build_statusline(
        model="m",
        effort="-",
        ctx_used=0,
        ctx_total=0,
        total_cached=0,
        total_new=0,
        total_output=0,
        hit_rate=0.0,
        cost_str="",
        cwd="/tmp",
    ))

    assert "m │ - │  0/0 │ in:0 (cached 0 new 0, 0.0%) │ out:0 │ /tmp" == rendered


def test_build_statusline_with_cost():
    rendered = strip_ansi_fragment(display.build_statusline(
        model="deepseek",
        effort="high",
        ctx_used=900,
        ctx_total=1000,
        total_cached=700,
        total_new=300,
        total_output=42,
        hit_rate=70.0,
        cost_str="¥0.01",
        cwd="~/repo",
    ))

    assert "deepseek" in rendered
    assert "¥0.01" in rendered
    assert "[█████████░]" in rendered
    assert "in:1.0K" in rendered
