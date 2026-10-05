"""Pure presentation helpers: names, type badges, and table cell formatting."""

TYPE_COLORS: dict[str, str] = {
    "normal": "#A8A77A",
    "fire": "#EE8130",
    "water": "#6390F0",
    "electric": "#F7D02C",
    "grass": "#7AC74C",
    "ice": "#96D9D6",
    "fighting": "#C22E28",
    "poison": "#A33EA1",
    "ground": "#E2BF65",
    "flying": "#A98FF3",
    "psychic": "#F95587",
    "bug": "#A6B91A",
    "rock": "#B6A136",
    "ghost": "#735797",
    "dragon": "#6F35FC",
    "dark": "#705746",
    "steel": "#B7B7CE",
    "fairy": "#D685AD",
}
LIGHT_TYPES = frozenset(
    {"normal", "electric", "grass", "ice", "ground", "bug", "rock", "steel", "fairy"}
)
FALLBACK_COLOR = "#68A090"

MULTIPLIER_LABELS: dict[float, str] = {
    4: "4× ▲▲",
    2: "2× ▲",
    1: "1×",
    0.5: "½× ▼",
    0.25: "¼× ▼▼",
    0: "0× ✕",
}


def display_name(name: str) -> str:
    return name.replace("-", " ").title()


def type_badge(type_name: str) -> str:
    t = type_name.lower()
    bg = TYPE_COLORS.get(t, FALLBACK_COLOR)
    fg = "#1f2937" if t in LIGHT_TYPES else "#ffffff"
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:999px;'
        f'font-size:0.75rem;font-weight:600;margin-right:4px;display:inline-block">'
        f"{t.title()}</span>"
    )


def type_badges(types: list[str]) -> str:
    return "".join(type_badge(t) for t in types)


def format_multiplier(value: float) -> str:
    return MULTIPLIER_LABELS.get(value, f"{value:g}×")


def color_multiplier(value: float) -> str:
    if value >= 4:
        return "background-color: #b91c1c; color: white"
    if value >= 2:
        return "background-color: #f87171"
    if value == 0:
        return "background-color: #60a5fa"
    if value < 1:
        return "background-color: #86efac"
    return ""
