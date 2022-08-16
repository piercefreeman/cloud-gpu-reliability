from random import seed
from gpu_reliability.cli import sample_timing
from unittest.mock import patch
import pytest

# Don't actually sleep the runtime
@patch("gpu_reliability.cli.sleep")
@pytest.mark.parametrize(
    "samples,sleep_interval,total_time",
    [
        # 10x a minute example
        (10, 2, 60),
        # 48x a day
        (48, 60, 60*60*24),
    ]
)
def test_sample_timing(mock_sleep, samples, sleep_interval, total_time):
    seed(42)

    coinflips = []

    # This is the amount of times we'll actually run the timing function
    for _ in range(int(total_time / sleep_interval)):
        with sample_timing(samples=samples, sleep_interval_seconds=sleep_interval, total_time_seconds=total_time) as flip:
            coinflips.append(flip)

    assert sum(coinflips) == pytest.approx(samples, abs=3)
