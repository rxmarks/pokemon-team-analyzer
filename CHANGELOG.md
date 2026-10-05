# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Pokémon Showdown team import with a tested paste parser (#29)
- Shareable team URLs via query parameters (#28)
- Property-based tests (Hypothesis), parametrized matchup tests, and Streamlit AppTest UI tests (#27)
- Strict mypy type checking in CI and shared type aliases (#26)
- Retry with exponential backoff for PokeAPI requests and 24-hour cache TTLs (#25)
- Dependabot for pip and GitHub Actions (#22)
- CI test matrix across Python 3.12–3.14
- Sidebar About panel, help expanders, and loading spinners
- Pre-commit hooks for Ruff lint and format
- Smogon top-30 meta threats table with scheduled data refresh
- Move-based coverage analysis (up to 4 moves per Pokémon)
- Base-stat role checks
- Mocked PokeAPI tests and a 90% coverage floor

### Changed
- Pinned runtime dependencies; split `requirements.txt` and `requirements-dev.txt` (#20)

### Removed
- Stale `main.py` CLI script (#20)