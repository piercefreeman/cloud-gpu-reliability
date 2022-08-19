# cloud-gpu-reliability

After encountering some reliability issues with on-demand provisioning of GPU resources, I put together this benchmarking harness to test AWS vs. GCP availability.

To maximize the statistical and practical significance of results:
- Each provisioning uses the same GPU configurations (currently a T4). GCP provides more flexibility here since their accelerators can be mounted to any hardware configuration whereas AWS only provisions these more powerful GPUs on designated VM configurations.
- Each deployment runs at the same approximate time, roughly 48 times a day. We handle this spawning via separate threads because async support isn't yet available for the official AWS and GCP Python APIs .
- It performs a [random search](https://en.wikipedia.org/wiki/Random_search) for what times during the day we should perform the trial. This attempts to account for the variability during daily demand of jobs that don't fit a set schedule.

At the risk of stating the obvious: running this locally will create cloud resources that you'll have to pay for while they run. This package takes every care to cleanup resources once it creates them but run at your own risk.

## Getting Started

This repo manages dependencies with [poetry](https://python-poetry.org/). A regular `pip install -e .` should work fine but might not pull in dependency versions that are tested.

```
poetry install
```

You'll also have to configure an `.env` file with your AWS and GCP credentials in order to execute. This should be relatively straightforward given the key names that are specified in Settings.

```
cat ~/personal-gcp-service-key.json | base64
```

## Errors

GCP:

```
Operation type [insert] failed with message "The zone 'projects/{project}/zones/{zone}' does not have enough resources available to fulfill the request. Try a different zone, or try again later."
```

```
Resource exhausted (HTTP 429): ZONE_RESOURCE_POOL_EXHAUSTED
```
