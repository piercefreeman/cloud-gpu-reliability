from enum import Enum, unique
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@unique
class PlatformType(Enum):
    GCP = "GCP"
    AWS = "AWS"


@dataclass
class LaunchRequest:
    """
    Requested device launch. Intended for use only by one provider.

    """
    spot: bool
    # Corresponds to region/zone where instance is spawned. AWS and GCP have different levels
    # of granularity required here during spawning so we keep this key generic.
    geography: str

    identifier: UUID = field(default_factory=uuid4)
