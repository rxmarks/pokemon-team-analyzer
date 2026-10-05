from pokedex.export import showdown_export


def test_export_has_one_block_per_pokemon():
    team = {"garchomp": ["dragon", "ground"], "gengar": ["ghost", "poison"]}

    result = showdown_export(team)

    assert result == "Garchomp\n\nGengar\n"


def test_export_includes_suggested_moves():
    team = {"garchomp": ["dragon", "ground"]}
    moves = {"garchomp": ["earthquake", "dragon-claw"]}

    result = showdown_export(team, moves)

    assert result == "Garchomp\n- Earthquake\n- Dragon Claw\n"


def test_export_omits_missing_move_sets():
    team = {"garchomp": ["dragon", "ground"], "gengar": ["ghost", "poison"]}
    moves = {"garchomp": ["earthquake"]}

    result = showdown_export(team, moves)

    assert "Garchomp\n- Earthquake" in result
    assert "\n\nGengar\n" in result
