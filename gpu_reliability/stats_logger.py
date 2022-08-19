from typing import Union
from pathlib import Path
from dataclasses import dataclass, asdict, field
from json import dumps, JSONEncoder
from datetime import datetime
from gpu_reliability.models import PlatformType, LaunchRequest
from threading import Lock
from uuid import UUID
from typing import Optional, List
from enum import Enum


class StatsEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.name
        if isinstance(obj, UUID):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return JSONEncoder.default(self, obj)


@dataclass
class Stat:
    platform: PlatformType
    create_success: bool
    request: LaunchRequest

    create_seconds: Optional[int] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    warnings: List[str] = field(default_factory=list)


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
                file.write(dumps(asdict(stat), cls=StatsEncoder) + "\n")
