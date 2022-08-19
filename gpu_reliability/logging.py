from functools import wraps
from logging import (
    INFO,
    Logger,
    basicConfig,
    getLogger,
)
from typing import Callable, TypeVar


OriginalFunc = TypeVar("OriginalFunc")

class NewLoggingClassStub:
    logger: Logger

def logger(cls) -> Callable[[OriginalFunc], type[NewLoggingClassStub]]:
    """
    Decorate a class with a .logger attribute, which represents a configured
    logger with reasonable default values

    """
    basicConfig(
        level=INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    @wraps(cls, updated=())
    class WrappedClass(cls, NewLoggingClassStub):
        logger = getLogger(cls.__name__)

    return WrappedClass
