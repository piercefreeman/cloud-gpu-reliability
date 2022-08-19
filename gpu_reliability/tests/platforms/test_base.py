from gpu_reliability.platforms.base import PlatformBase
from gpu_reliability.models import PlatformType, LaunchRequest
from time import sleep
from gpu_reliability.stats_logger import StatsLogger, Stat
from json import loads
import pytest

WORK_TIME = 1

class FakeException(Exception):
    pass

class CrashingPlatform(PlatformBase):
    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.GCP

    def launch_instance(self, _):
        raise FakeException("I crashed")

    def cleanup_resources(self):
        pass

class SuccessfulPlatform(PlatformBase):
    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.GCP

    def launch_instance(self, request):
        sleep(WORK_TIME)
        self.storage.write(
            Stat(
                platform=self.platform_type,
                request=request,
                create_success=True,
            )
        )

    def cleanup_resources(self):
        pass


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_keepalive_threads(stats_path):
    """
    Ensure that if one thread crashes, the others will stay alive
    """
    logger = StatsLogger(stats_path)
    crashing = CrashingPlatform(logger)
    successful = SuccessfulPlatform(logger)

    for platform in [crashing, successful]:
        platform.set_should_launch(True)
        platform.spawn()

    # Give them sufficient time to do work
    sleep(WORK_TIME+1)

    # Ensure the crashing platform has crashed
    assert not crashing.is_spawned
    assert successful.is_spawned

    with open(stats_path) as file:
        logs = [loads(line) for line in file]

    error_values = [(log["create_success"], log["error"]) for log in logs]
    assert error_values == [(False, "I crashed"), (True, None)]

    # Cleanup the running resources
    successful.quit()
