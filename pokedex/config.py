from pathlib import Path

# Team rules
MAX_TEAM_SIZE = 6
MAX_MOVES = 4
DEFAULT_TEAM = ["dragonite", "gyarados", "garchomp", "ferrothorn", "togekiss", "tyranitar"]

# Analysis thresholds
MIN_BST = 500
FAST_SPEED = 100
TOP_N_SWAPS = 5
EXCLUDED_FORM_TAGS = ("-gmax", "-totem")

# PokeAPI
BASE_URL = "https://pokeapi.co/api/v2"
REQUEST_TIMEOUT = 20
RETRY_TOTAL = 3
RETRY_BACKOFF = 0.5
RETRY_STATUSES = (429, 500, 502, 503, 504)

# Caching
CACHE_TTL_SECONDS = 60 * 60 * 24

# Data files
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TYPE_CHART_PATH = DATA_DIR / "types.json"
POKEMON_CACHE_PATH = DATA_DIR / "pokemon.json"
MOVES_CACHE_PATH = DATA_DIR / "moves.json"
SMOGON_PATH = DATA_DIR / "smogon_usage.json"
