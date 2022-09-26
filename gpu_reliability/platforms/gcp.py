from google.cloud import compute_v1
from time import time
from gpu_reliability.platforms.base import PlatformType, PlatformBase, LaunchRequest, INSTANCE_TAG, INSTANCE_TAG_VALUE
from google.oauth2.service_account import Credentials
from gpu_reliability.stats_logger import StatsLogger, Stat
from google.api_core.exceptions import NotFound
from json import loads
from gpu_reliability.logging import logger
from uuid import uuid1


@logger
class GCPPlatform(PlatformBase):
    def __init__(
        self,
        project_id: str,
        service_account: str,
        machine_type: str,
        accelerator_type: str,
        storage: StatsLogger,
        create_timeout: int = 200,
        delete_timeout: int = 300,
    ):
        """
        :param service_account_path: Path to the service account JSON file
        :param machine_type: For custom types, format as: `custom-CPUS-MEMORY` populating CPU and MEMORY counts
        :param accelerator_type: To view the accelerators available in the given zone:
            `gcloud compute accelerator-types list --filter="zone:( us-central1-b us-east-a )"`

        """
        super().__init__(storage=storage)
        self.project_id = project_id
        self.machine_type = machine_type
        self.accelerator_type = accelerator_type

        self.create_timeout = create_timeout
        self.delete_timeout = delete_timeout

        credentials = Credentials.from_service_account_info(loads(service_account))
        self.image_client = compute_v1.ImagesClient(credentials=credentials)
        self.instance_client = compute_v1.InstancesClient(credentials=credentials)

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.GCP

    def launch_instance(self, request: LaunchRequest):
        uuid = str(uuid1())
        instance_name = f"gpu-test-{uuid}"


        instance = compute_v1.Instance(
            name=instance_name,
            machine_type=f"zones/{request.geography}/machineTypes/{self.machine_type}",
            guest_accelerators=[
                compute_v1.AcceleratorConfig(
                    accelerator_count=1,
                    accelerator_type=f"/zones/{request.geography}/acceleratorTypes/{self.accelerator_type}",
                )
            ],
            labels={
                INSTANCE_TAG: INSTANCE_TAG_VALUE,
            }
        )

        instance.disks = [
            compute_v1.AttachedDisk(
                auto_delete=True,
                boot=True,
                initialize_params=compute_v1.AttachedDiskInitializeParams(
                    source_image=self.get_image().self_link,
                    disk_size_gb=10,
                    disk_type=f"/projects/{self.project_id}/zones/{request.geography}/diskTypes/pd-standard"
                )
            )
        ]

        instance.network_interfaces = [
            compute_v1.NetworkInterface(
            )
        ]

        instance.scheduling = compute_v1.Scheduling(
            on_host_maintenance="TERMINATE",
        )

        if request.spot:
            # Spot VM settings, which replaces preemptible tasks in GCP
            instance.scheduling.provisioning_model = (
                compute_v1.Scheduling.ProvisioningModel.SPOT.name
            )
            # Instances should be so short lived they have a minimal chance of actually getting triggered
            # by spot instance interrupt, but we set the same delete behavior here just in case.
            # https://cloud.google.com/java/docs/reference/google-cloud-compute/1.9.1/com.google.cloud.compute.v1.Scheduling.InstanceTerminationAction
            instance.scheduling.instance_termination_action = "DELETE"

        # Prepare the request to insert an instance.
        create_request = compute_v1.InsertInstanceRequest(
            zone=request.geography,
            project=self.project_id,
            instance_resource=instance,
            request_id=uuid,
        )

        # Wait for the create operation to complete.
        self.logger.info(f"Creating instance `{instance_name}`...")

        operation = self.instance_client.insert(request=create_request)
        start = time()
        operation.result(timeout=self.create_timeout)
        create_time = time() - start

        self.log_operation_status(operation)

        self.logger.info(f"Finished creating instance `{instance_name}`")
        created_instance = self.instance_client.get(project=self.project_id, zone=request.geography, instance=instance_name)

        # Check status
        self.storage.write(
            Stat(
                platform=self.platform_type,
                request=self.should_launch,
                create_success=created_instance.status == "RUNNING",
                create_seconds=create_time,
                error=created_instance.status if created_instance.status != "RUNNING" else None,
            )
        )

    def log_operation_status(self, operation):
        error = None
        warnings = []

        if operation.error_code:
            error = f"[Code: {operation.error_code}]: {operation.error_message}"

        if operation.warnings:
            for warning in operation.warnings:
                warnings.append(
                    f"[Code: {warning.code}]: {warning.message}"
                )

        self.storage.write(
            Stat(
                platform=self.platform_type,
                request=self.should_launch,
                create_success=error is None,
                error=error,
                warnings=warnings,
            )
        )

    def get_image(self) -> compute_v1.Image:
        # List of public operating system (OS) images: https://cloud.google.com/compute/docs/images/os-details
        newest_image = self.image_client.get_from_family(project="debian-cloud", family="debian-11")
        return newest_image

    def cleanup_resources(self):
        # Search through all zones in case we have modified the request.geography paramter
        # and still have remaining instances in other zones.
        active_instances = self.instance_client.aggregated_list(
            request=compute_v1.AggregatedListInstancesRequest(
                filter=f"labels.{INSTANCE_TAG}={INSTANCE_TAG_VALUE}",
                project=self.project_id,
            ),
        )

        for zone_path, results in active_instances:
            zone = zone_path.split("/")[-1]
            if results.warning:
                continue
            for instance in results.instances:
                # Only attempt to shut down running instances, otherwise we might clear away
                # boxes that are still trying to bootstrap and/or have already started terminating.
                if instance.status != "RUNNING":
                    continue
                self.logger.info(f"Deleting `{instance.name}`...")
                operation = self.instance_client.delete(project=self.project_id, zone=zone, instance=instance.name)
                try:
                    operation.result(timeout=self.delete_timeout)
                except NotFound:
                    # Expected error because once instances are deleted the API can't retrieve them
                    pass
                self.logger.info(f"Finished deleting `{instance.name}`")
