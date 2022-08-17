from time import time, sleep
from gpu_reliability.platforms.base import PlatformType, PlatformBase, INSTANCE_TAG, INSTANCE_TAG_VALUE
from click import secho
from boto3 import Session
from gpu_reliability.stats_logger import StatsLogger, Stat
from enum import Enum


class AWSInstanceCodes(Enum):
    PENDING = 0
    RUNNING = 16 
    SHUTTING_DOWN = 32 
    TERMINATED = 48
    STOPPING = 64
    STOPPED = 80


class AWSPlatform(PlatformBase):
    def __init__(
        self,
        #access_key: str,
        #secret_key: str,
        region: str,
        machine_type: str,
        spot: bool,
        logger: StatsLogger,
        create_timeout: int = 200,
        delete_timeout: int = 300,
    ):
        """
        :param service_account_path: Path to the service account JSON file
        :param machine_type: For custom types, format as: `custom-CPUS-MEMORY` populating CPU and MEMORY counts
        :param accelerator_type: To view the accelerators available in the given zone:
            `gcloud compute accelerator-types list --filter="zone:( us-central1-b us-east-a )"`

        """
        super().__init__(logger=logger)
        self.region = region
        self.machine_type = machine_type
        self.spot = spot

        self.create_timeout = create_timeout
        self.delete_timeout = delete_timeout

        session = Session(
            #aws_access_key_id=access_key,
            #aws_secret_access_key=secret_key,
        )

        self.client = session.client("ec2", region_name=region)
        self.resource = session.resource("ec2", region_name=region)

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.AWS

    def launch_instance(self):
        instance_name = f"gpu-test-{int(time())}"

        # Custom options that can be configured by init parameters
        additional_options = {}

        if self.spot:
            additional_options["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {
                    # By not specifying `MaxPrice` we pay the current spot price
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                }
            }

        secho(f"Creating instance `{instance_name}`...", fg="yellow")

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.run_instances
        created_instance = self.client.run_instances(
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
        )

        secho(f"Finished creating instance `{instance_name}`", fg="green")

        error = None
        if state_type != AWSInstanceCodes.RUNNING:
            final_state_code = instance.state_reason["Code"]
            final_state_text = instance.state_reason["Message"]
            error = f"[Code: {final_state_code}]: {final_state_text}"

        # Check status
        self.logger.write(
            Stat(
                platform=self.platform_type,
                launch_identifier=self.launch_identifier,
                create_success=state_type == AWSInstanceCodes.RUNNING,
                error=error,
            )
        )

    def cleanup_resources(self):
        instances = self.resource.instances.filter(
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
            instances.terminate()

            secho(f"Deleting `{instance_id}`...", fg="yellow")

            self.wait_for_status(
                instance_id,
                lambda x: x == AWSInstanceCodes.TERMINATED,
                self.delete_timeout
            )

            secho(f"Finished deleting `{instance_id}`", fg="green")

    def wait_for_status(
        self,
        instance_id: str,
        break_condition,
        max_wait: int,
        check_interval: int = 10
    ):
        while max_wait > 0:
            instance = self.resource.Instance(instance_id)
            instance_name = [tag for tag in instance.tags if tag["Key"] == "Name"][0]
            state_type = AWSInstanceCodes(instance.state["Code"])
            secho(f"{instance_name} - {state_type}")

            # Once we resolve the status of the resource, we don"t have to wait any longer
            if break_condition(state_type):
                return instance, state_type

            sleep(check_interval)
            max_wait -= check_interval

        raise TimeoutError(f"Instance `{instance_id}` did not reach break condition`")
