from enum import Enum, unique

@unique
class PlatformType(Enum):
    GCP = "GCP"
    AWS = "AWS"

