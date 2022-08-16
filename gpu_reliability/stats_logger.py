from typing import Union
from pathlib import Path
from dataclasses import dataclass, asdict
from json import dumps
from datetime import datetime
from gpu_reliability.platforms.base import PlatformType
from threading import Lock


@dataclass
class Stat:
    platform: PlatformType
    launch_identifier: str
    timestamp: datetime
    create_success: bool
    launch_error: str


class StatsLogger:
    """
    Log simple statistics about our launches in a jsonl file

    """
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.lock = Lock()

        if not self.path.exists():
            self.path.touch()

    def write(self, stat: Stat):
        with self.lock:
            with open(self.path, "a") as file:
                file.write(dumps(asdict(stat)) + "\n")
