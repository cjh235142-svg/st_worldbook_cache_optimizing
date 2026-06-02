import json
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"
INTEGRATION_FIXTURES_DIR = FIXTURES_DIR / "integration"


def load_fixture_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def tmp_world_book_path(tmp_path) -> Path:
    return tmp_path / "test_world_book.json"


@pytest.fixture
def integration_fixtures_dir() -> Path:
    return INTEGRATION_FIXTURES_DIR


@pytest.fixture
def full_pipeline_input(integration_fixtures_dir) -> dict:
    return load_fixture_json(str(integration_fixtures_dir / "full_pipeline_input.json"))


@pytest.fixture
def full_pipeline_expected(integration_fixtures_dir) -> dict:
    return load_fixture_json(str(integration_fixtures_dir / "full_pipeline_expected.json"))


@pytest.fixture
def pipeline_tmpdir(tmp_path) -> Path:
    d = tmp_path / "pipeline_test"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture
def static_wb(fixtures_dir) -> dict:
    return load_fixture_json(str(fixtures_dir / "static_entry.json"))


@pytest.fixture
def dynamic_wb(fixtures_dir) -> dict:
    return load_fixture_json(str(fixtures_dir / "dynamic_entry.json"))


@pytest.fixture
def mixed_wb(fixtures_dir) -> dict:
    return load_fixture_json(str(fixtures_dir / "mixed_entry.json"))


@pytest.fixture
def small_wb(fixtures_dir) -> dict:
    return load_fixture_json(str(fixtures_dir / "small_world_book.json"))


@pytest.fixture
def empty_wb(fixtures_dir) -> dict:
    return load_fixture_json(str(fixtures_dir / "empty_entries.json"))
