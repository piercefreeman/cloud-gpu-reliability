from click import command, option, Path as ClickPath, secho
from gpu_reliability.platforms.gcp import GCPPlatform
from gpu_reliability.platforms.aws import AWSPlatform
from gpu_reliability.stats_logger import StatsLogger
from time import sleep
from random import random
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def sample_timing(samples: int, sleep_interval_seconds: int, total_time_seconds: int) -> bool:
    """
    On expectation, runs `samples` per `total_time_seconds` period given this
    function is called once every `sleep_interval`.

    For a simplified example let's consider a minute instead of a day:

    - samples = 10
    - total_time = 60 seconds
    - sleep_interval = 2 (only 30 trials per minute)
    - every second we want a 1/3 (10/30) likelihood of running

    E[samples / (total_time/sleep_interval)]

    """
    should_run = (samples / (total_time_seconds / sleep_interval_seconds)) > random()
    yield should_run
    sleep(sleep_interval_seconds)


@command()
@option("--aws-service-account", type=ClickPath(exists=True), required=False)
@option("--gcp-project", type=str, required=True)
@option("--gcp-service-account", type=ClickPath(exists=True), required=True)
@option("--output-path", type=ClickPath(exists=False), required=True)
@option("--daily-samples", type=int, default=24 * 2)
def benchmark(
    aws_service_account,
    gcp_project,
    gcp_service_account,
    output_path,
    daily_samples,
    sleep_interval=10,
):
    storage = StatsLogger(Path(output_path).expanduser())

    platforms = [
        # GCPPlatform(
        #     project_id=gcp_project,
        #     zone="us-central1-b",
        #     machine_type="n1-standard-1",
        #     accelerator_type="nvidia-tesla-t4",
        #     spot=False,
        #     service_account_path=gcp_service_account,
        #     logger=storage,
        # ),
        AWSPlatform(
            region="us-east-1",
            machine_type="t3.micro",
            spot=False,
            logger=storage,
        )
    ]

    for platform in platforms:
        # Spawn on startup to provide a baseline
        platform.set_should_launch(True)

    try:
        while True:
            # Healthcheck of threads; if they have quit, restart them
            for platform in platforms:
                if not platform.is_spawned:
                    platform.spawn()

            # Spawn all at the same time
            with sample_timing(daily_samples, sleep_interval, total_time_seconds=60*60*24) as should_run:
                if should_run:
                    for platform in platforms:
                        secho(f"Trigger launch: `{platform.platform_type}`")
                        platform.set_should_launch(True)
    except KeyboardInterrupt:
        secho("Shutdown triggered, cleaning up resources...", fg="red")
        # Close the running threads
        for platform in platforms:
            platform.quit()
            platform.join()
