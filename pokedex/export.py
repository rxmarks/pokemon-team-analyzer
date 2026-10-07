"""Export helpers for sharing supported Pokémon team builds."""

from pokedex.display import display_name
from pokedex.pokemon_names import showdown_species_name
from pokedex.team_state import TeamState
from pokedex.types import Team


def showdown_export(
    team: Team | TeamState,
    move_sets: dict[str, list[str]] | None = None,
) -> str:
    """Return species and supplied moves in Showdown-style text.

    TeamState exports its current selected moves. Legacy type mappings
    optionally accept a separate move mapping.

    Items, abilities, EVs, IVs, natures, and legality checks are not included.
    """
    blocks: list[str] = []

    if isinstance(team, TeamState):
        if move_sets is not None:
            raise ValueError("Do not supply separate move sets when exporting a TeamState.")

        entries = [(member.species, member.moves) for member in team.members]
    else:
        supplied_moves = move_sets if move_sets is not None else {}
        entries = [(name, tuple(supplied_moves.get(name, []))) for name in team]

    for species, moves in entries:
        lines = [showdown_species_name(species)]
        lines.extend(f"- {display_name(move)}" for move in moves)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) + "\n" if blocks else ""
