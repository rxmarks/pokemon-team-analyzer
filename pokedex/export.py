"""Export helpers for sharing Pokémon teams."""

from pokedex.types import Team


def showdown_export(team: Team, move_sets: dict[str, list[str]] | None = None) -> str:
    """Return a Pokémon Showdown-compatible team export.

    Suggested moves are included when supplied. The export intentionally leaves
    items, abilities, EVs, and natures blank for the user to customize.
    """
    move_sets = move_sets or {}
    blocks: list[str] = []

    for name in team:
        display = name.replace("-", " ").title()
        moves = move_sets.get(name, [])
        lines = [display]
        lines.extend(f"- {move.replace('-', ' ').title()}" for move in moves)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) + "\n"
