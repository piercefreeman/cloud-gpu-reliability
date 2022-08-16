from tempfile import TemporaryDirectory
import pytest
from pathlib import Path

@pytest.fixture(scope="function")
def output_dir():
    with TemporaryDirectory() as directory:
        yield Path(directory)

@pytest.fixture()
def stats_path(output_dir):
    return output_dir / "stats.jsonl"
