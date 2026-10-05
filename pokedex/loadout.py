from pokedex.config import LOADOUT_SIZE, MIN_MOVE_POWER, MOVE_BLOCKLIST
from pokedex.types import MoveCache, Team, TypeChart

COVERAGE_WEIGHT = 1000
STAB_WEIGHT = 50
OFF_STAT_PENALTY = 0.6


def hits_super_effectively(move_type: str, chart: TypeChart) -> set[str]:
    return set(chart[move_type]["double_damage_to"])


def usable_moves(learnable: list[str], move_cache: MoveCache) -> list[str]:
    return [
        m
        for m in learnable
        if m in move_cache
        and m not in MOVE_BLOCKLIST
        and move_cache[m].get("damage_class") != "status"
        and (move_cache[m].get("power") or 0) >= MIN_MOVE_POWER
    ]


def preferred_class(stats: dict[str, int]) -> str:
    return "physical" if stats.get("attack", 0) >= stats.get("special-attack", 0) else "special"


def move_score(
    move: str,
    types: list[str],
    stats: dict[str, int],
    move_cache: MoveCache,
    chart: TypeChart,
    covered: set[str],
) -> float:
    data = move_cache[move]
    move_type: str = data["type"]
    base_power = float(data["power"])
    new = hits_super_effectively(move_type, chart) - covered
    stab = move_type in types
    multiplier = 1.0 if data["damage_class"] == preferred_class(stats) else OFF_STAT_PENALTY
    return len(new) * COVERAGE_WEIGHT + stab * STAB_WEIGHT + base_power * multiplier


def suggest_loadouts(
    team: Team,
    learnsets: dict[str, list[str]],
    stats: dict[str, dict[str, int]],
    move_cache: MoveCache,
    chart: TypeChart,
) -> dict[str, list[str]]:
    """Greedy pick of up to 4 moves per member that maximize new team coverage.

    Each member gets its best STAB move first, then coverage-weighted picks.
    """
    covered: set[str] = set()
    loadouts: dict[str, list[str]] = {}
    for name, types in team.items():
        pool = usable_moves(learnsets.get(name, []), move_cache)
        picked: list[str] = []
        used_types: set[str] = set()

        stab = [m for m in pool if move_cache[m]["type"] in types]
        if stab:
            best = max(
                stab, key=lambda m: (move_score(m, types, stats[name], move_cache, chart, set()), m)
            )
            picked.append(best)
            used_types.add(move_cache[best]["type"])
            covered |= hits_super_effectively(move_cache[best]["type"], chart)

        while len(picked) < LOADOUT_SIZE:
            options = [
                m for m in pool if m not in picked and move_cache[m]["type"] not in used_types
            ]
            if not options:
                break
            best = max(
                options,
                key=lambda m: (move_score(m, types, stats[name], move_cache, chart, covered), m),
            )
            picked.append(best)
            used_types.add(move_cache[best]["type"])
            covered |= hits_super_effectively(move_cache[best]["type"], chart)

        loadouts[name] = picked
    return loadouts


def loadout_coverage(
    loadouts: dict[str, list[str]], move_cache: MoveCache, chart: TypeChart
) -> set[str]:
    return {
        target
        for moves in loadouts.values()
        for m in moves
        for target in hits_super_effectively(move_cache[m]["type"], chart)
    }
