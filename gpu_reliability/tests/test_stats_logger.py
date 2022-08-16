from gpu_reliability.stats_logger import StatsLogger, Stat
from json import dumps, loads
from gpu_reliability.platforms.base import PlatformType
from uuid import uuid4

def test_init_file(stats_path):
    assert not stats_path.exists()
    StatsLogger(stats_path)
    assert stats_path.exists()

def test_extend_existing_file(stats_path):
    with open(stats_path, "w") as file:
        file.write(dumps({"test": True}) + "\n")

    stats_logger = StatsLogger(stats_path)
    stats_logger.write(
        Stat(
            platform=PlatformType.GCP,
            launch_identifier=uuid4(),
            create_success=True,
        )
    )

    with open(stats_path) as file:
        lines = [loads(line) for line in file]
    assert len(lines) == 2
