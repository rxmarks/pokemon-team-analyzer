"""Readable selected-move metadata independent of Streamlit."""

from typing import TypedDict

from pokedex.types import MoveCache


class MoveDetail(TypedDict):
    Move: str
    Type: str
    Category: str
    Power: int | None
    Coverage: str


def selected_move_details(
    moves: list[str],
    move_cache: MoveCache,
) -> list[MoveDetail]:
    """Describe selected moves in order without altering selections."""
    rows: list[MoveDetail] = []

    for move in moves:
        info = move_cache.get(move)

        if info is None:
            rows.append(
                {
                    "Move": move.replace("-", " ").title(),
                    "Type": "Unknown",
                    "Category": "Unknown",
                    "Power": None,
                    "Coverage": "Unavailable — selection preserved",
                }
            )
            continue

        category = info["damage_class"]
        power = info.get("power")

        rows.append(
            {
                "Move": move.replace("-", " ").title(),
                "Type": info["type"].title(),
                "Category": category.title(),
                "Power": power,
                "Coverage": (
                    "Not counted — status move"
                    if category == "status"
                    else "Counted — damaging move type"
                ),
            }
        )

    return rows
