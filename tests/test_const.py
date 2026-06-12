"""Tests for date-based season handling."""
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "openligadb_team"
    / "const.py"
)
SPEC = spec_from_file_location("openligadb_team_const", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
current_season = MODULE.current_season


def test_current_season_before_july_uses_previous_year() -> None:
    """Seasons ending in summer should still map to the previous start year."""
    assert current_season(date(2026, 6, 12)) == 2025


def test_current_season_from_july_uses_current_year() -> None:
    """The new season should start with July."""
    assert current_season(date(2026, 7, 1)) == 2026
