from datetime import date

from scripts.build_smogon_cache import parse_usage, previous_month, to_pokeapi_name


def test_previous_month_normal():
    assert previous_month(date(2026, 10, 3)) == "2026-09"


def test_previous_month_january_wraps_year():
    assert previous_month(date(2027, 1, 3)) == "2026-12"


def test_name_fixes():
    assert to_pokeapi_name("Great Tusk") == "great-tusk"
    assert to_pokeapi_name("Ogerpon-Wellspring") == "ogerpon-wellspring-mask"


def test_parse_usage_skips_headers():
    text = (
        " + ---- + ------- +\n"
        " | Rank | Pokemon | Usage % |\n"
        " | 1    | Great Tusk | 33.9% |\n"
        " | 2    | Kingambit  | 28.4% |\n"
    )
    rows = parse_usage(text, top_n=1)
    assert rows == [
        {"rank": 1, "smogon_name": "Great Tusk", "name": "great-tusk", "usage": 33.9}
    ]