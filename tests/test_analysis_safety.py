import pytest

from pokedex.analysis_safety import has_complete_team


@pytest.mark.parametrize(
    ("selected", "loaded", "expected"),
    [
        pytest.param([], [], False, id="empty"),
        pytest.param(["garchomp"], [], False, id="none-loaded"),
        pytest.param(
            ["garchomp", "tyranitar"],
            ["garchomp"],
            False,
            id="partial",
        ),
        pytest.param(
            ["garchomp", "tyranitar"],
            ["garchomp", "tyranitar"],
            True,
            id="complete",
        ),
        pytest.param(
            ["garchomp", "tyranitar"],
            ["tyranitar", "garchomp"],
            True,
            id="order-independent",
        ),
        pytest.param(
            ["garchomp"],
            ["garchomp", "tyranitar"],
            False,
            id="unexpected-extra-member",
        ),
        pytest.param(
            ["garchomp", "tyranitar"],
            ["garchomp", "dragonite"],
            False,
            id="same-count-wrong-members",
        ),
    ],
)
def test_has_complete_team(selected, loaded, expected):
    assert has_complete_team(selected, loaded) is expected
