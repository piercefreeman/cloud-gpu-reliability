from time import time, sleep
from gpu_reliability.platforms.base import PlatformType, PlatformBase, LaunchRequest, INSTANCE_TAG, INSTANCE_TAG_VALUE
from boto3 import Session
from gpu_reliability.stats_logger import StatsLogger, Stat
from enum import Enum
from gpu_reliability.logging import logger
from backoff import on_exception, expo
from botocore.exceptions import ClientError


class AWSInstanceCodes(Enum):
    PENDING = 0
    RUNNING = 16 
    SHUTTING_DOWN = 32 
    TERMINATED = 48
    STOPPING = 64
    STOPPED = 80


@logger
class AWSPlatform(PlatformBase):
    def __init__(
        self,
        access_key_id: str,
        secret_key: str,
        machine_type: str,
        storage: StatsLogger,
        create_timeout: int = 200,
        delete_timeout: int = 300,
    ):
        """
        :param service_account_path: Path to the service account JSON file
        :param machine_type: AWS supported machine type

        """
        super().__init__(storage=storage)
        self.machine_type = machine_type

        self.create_timeout = create_timeout
        self.delete_timeout = delete_timeout

        self.session = Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_key,
        )

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.AWS

    def launch_instance(self, request: LaunchRequest):
        # Init the resources based on the region request since all downstream
        # requests that use these resources will be made in the same region
        client = self.session.client("ec2", region_name=request.geography)
        resource = self.session.resource("ec2", region_name=request.geography)

        instance_name = f"gpu-test-{int(time())}"

        # Custom options that can be configured by init parameters
        additional_options = {}

        if request.spot:
            additional_options["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {
                    # By not specifying `MaxPrice` we pay the current spot price
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                }
            }

        self.logger.info(f"Creating instance `{instance_name}`...")

        start = time()
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.run_instances
        created_instance = client.run_instances(
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {

                        "DeleteOnTermination": True,
                        "VolumeSize": 8,
                        "VolumeType": "gp2"
                    },
                },
            ],
            # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami.html#finding-an-ami-aws-cli
            # aws ec2 describe-images --query 'Images[?CreationDate>=`2022-04-01`][]'
            ImageId="ami-090fa75af13c156b4",
            InstanceType=self.machine_type,
            MaxCount=1,
            MinCount=1,
            Monitoring={
                "Enabled": False
            },
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {
                            "Key": INSTANCE_TAG,
                            "Value": INSTANCE_TAG_VALUE,
                        },
                        {
                            "Key": "Name",
                            "Value": instance_name,
                        },
                    ]
                },
            ],
            **additional_options,
        )

        instance_id = created_instance["Instances"][0]["InstanceId"]

        instance, state_type = self.wait_for_status(
            instance_id,
            lambda x: x != AWSInstanceCodes.PENDING,
            self.create_timeout,
            resource=resource,
        )
        create_time = time() - start

        self.logger.info(f"Finished creating instance `{instance_name}`")

        error = None
        if state_type != AWSInstanceCodes.RUNNING:
            final_state_code = instance.state_reason["Code"]
            final_state_text = instance.state_reason["Message"]
            error = f"[Code: {final_state_code}]: {final_state_text}"

        # Check status
        self.storage.write(
            Stat(
                platform=self.platform_type,
                request=self.should_launch,
                create_seconds=create_time,
                create_success=state_type == AWSInstanceCodes.RUNNING,
                error=error,
            )
        )

    def cleanup_resources(self):
        # Choose a random region since we just need to list this
        simple_client = self.session.client("ec2", "us-east-1")
        regions = [region["RegionName"] for region in simple_client.describe_regions()["Regions"]]

        for region in regions:
            resource = self.session.resource("ec2", region_name=region)
            instances = resource.instances.filter(
                Filters=[
                    {
                        "Name": f"tag:{INSTANCE_TAG}",
                        "Values": [
                            INSTANCE_TAG_VALUE
                        ]
                    },
                    {
                        # Only attempt to terminate instances that are fully running and where shutdown
                        # actions haven't yet been taken
                        "Name": "instance-state-name",
                        "Values": [
                            "running",
                        ],
                    }
                ]
            )

            for instance in instances:
                instance_id = instance.instance_id
                instance_name = self.name_from_instance(instance)

                instances.terminate()

                self.logger.info(f"Deleting `{instance_name}`...")

                self.wait_for_status(
                    instance_id,
                    lambda x: x == AWSInstanceCodes.TERMINATED,
                    self.delete_timeout,
                    resource=resource,
                )

                self.logger.info(f"Finished deleting `{instance_name}`")

    def wait_for_status(
        self,
        instance_id: str,
        break_condition,
        max_wait: int,
        resource: Session.resource,
        check_interval: int = 1,
    ):
        instance = resource.Instance(instance_id)
        instance_name = self.name_from_instance(instance)

        while max_wait > 0:
            instance = resource.Instance(instance_id)
            state_type = AWSInstanceCodes(instance.state["Code"])
            self.logger.info(f"Status `{instance_name}`: {state_type}")

            # Once we resolve the status of the resource, we don"t have to wait any longer
            if break_condition(state_type):
                return instance, state_type

            sleep(check_interval)
            max_wait -= check_interval

        raise TimeoutError(f"Instance `{instance_id}` did not reach break condition`")

    @on_exception(expo, ClientError, max_tries=8)
    def name_from_instance(self, instance):
        # Sometimes AWS returns an error for these instances even if they do in fact exist
        # https://stackoverflow.com/questions/8969677/aws-error-message-invalidinstanceid-notfound
        return [tag for tag in instance.tags if tag["Key"] == "Name"][0]["Value"]
