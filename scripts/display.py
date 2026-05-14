"""ANSI formatting and statusline rendering."""
RESET = "\033[0m"

WHITE  = "37"
PURPLE = "38;5;141"
GREEN  = "38;5;114"
YELLOW = "33"
RED    = "31"
GRAY   = "90"


def ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}{RESET}"


def fmt(n: int) -> str:
    if n >= 999_950: return f"{n / 1_000_000:.1f}M"
    if n >= 1000:      return f"{n / 1000:.1f}K"
    return str(n)


def ctx_bar(used: int, total: int, width: int = 10) -> str:
    if total == 0:
        return ""
    r = min(used / total, 1.0)
    if r < 0.5:   col = GREEN
    elif r < 0.8: col = YELLOW
    else:         col = RED

    n = round(r * width)
    if r > 0 and n == 0:
        n = 1

    out  = ansi(col, '█' * n)
    out += ansi(GRAY, '░' * (width - n))
    return f"{ansi(GRAY, '[')}{out}{ansi(GRAY, ']')}"


def ctx_col(used: int, total: int) -> str:
    if total == 0: return GRAY
    r = used / total
    if r < 0.5:   return GREEN
    elif r < 0.8: return YELLOW
    else:         return RED


def build_statusline(
    model: str,
    effort: str,
    ctx_used: int,
    ctx_total: int,
    total_cached: int,
    total_new: int,
    total_output: int,
    hit_rate: float,
    cost_str: str,
    cwd: str,
) -> str:
    sep = f" {ansi(GRAY, '│')} "

    parens = (
        f"{ansi(GRAY, '(cached')} {ansi(PURPLE, fmt(total_cached))} "
        f"{ansi(GRAY, 'new')} {ansi(PURPLE, fmt(total_new))}"
        f"{ansi(GRAY, ',')} {ansi(PURPLE, f'{hit_rate:.1f}%')}"
    )
    if cost_str:
        parens += f"{ansi(GRAY, ',')} {ansi(PURPLE, cost_str)}"
    parens += ansi(GRAY, ')')

    total_in = total_cached + total_new

    parts = [
        ansi(WHITE, model),
        ansi(WHITE, effort),
        f"{ctx_bar(ctx_used, ctx_total)} {ansi(ctx_col(ctx_used, ctx_total), fmt(ctx_used))}{ansi(GRAY, '/')}{ansi(WHITE, fmt(ctx_total))}",
        f"{ansi(GRAY, 'in:')}{ansi(PURPLE, fmt(total_in))} {parens}",
        f"{ansi(GRAY, 'out:')}{ansi(PURPLE, fmt(total_output))}",
        ansi(WHITE, cwd),
    ]

    return sep.join(parts)
