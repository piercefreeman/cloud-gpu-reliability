from click import command, option, Path as ClickPath, secho
from gpu_reliability.platforms.gcp import GCPPlatform
from gpu_reliability.stats_logger import StatsLogger
from time import sleep
from random import random
from contextlib import contextmanager


@contextmanager
def sample_timing(samples: int, sleep_interval_seconds: int, total_time_seconds: int) -> bool:
    """
    On expectation, runs `samples` per `total_time_seconds` period given this
    function is called once every `sleep_interval`.

    For a simplified example let's consider a minute instead of a day:

    - samples = 10
    - sleep_interval = 2 (only 30 trials per minute)
    - total_time = 60 seconds
    - every second we want a 1/3 (10/30) likelihood of running

    E[samples / (total_time/sleep_interval)]

    """
    should_run = (samples / (total_time_seconds / sleep_interval_seconds)) < random()
    yield should_run
    sleep(sleep_interval_seconds)


@command()
@option("--aws-service-account", type=ClickPath(exists=True), required=False)
@option("--gcp-project", type=str, required=True)
@option("--gcp-service-account", type=ClickPath(exists=True), required=True)
@option("--output-path", type=ClickPath(exists=False), required=True)
@option("--daily-samples", type=int, required=True)
def benchmark(
    aws_service_account,
    gcp_project,
    gcp_service_account,
    output_path,
    daily_samples,
    sleep_interval=10,
):
    storage = StatsLogger(output_path)

    gcp = GCPPlatform(
        project_id=gcp_project,
        zone="us-central1-b",
        machine_type="n1-standard-1",
        accelerator_type="nvidia-tesla-t4",
        spot=False,
        service_account_path=gcp_service_account,
    )

    platforms = [gcp]

    while True:
        # Healthcheck of threads; if they have quit, restart them
        for platform in platforms:
            if not platform.is_spawned():
                platform.spawn()

        # Spawn all at the same time
        with sample_timing(daily_samples, sleep_interval, total_time_seconds=60*60*24) as should_run:
            if should_run:
                for platform in platforms:
                    secho(f"Trigger launch: `{platform.platform_type}`")
                    platform.set_should_launch()
