from enum import Enum, unique
from abc import ABC, abstractmethod, abstractproperty
from threading import Thread
from time import sleep


INSTANCE_TAG = "gpu-reliability-test"
INSTANCE_TAG_VALUE = "true"


@unique
class PlatformType(Enum):
    GCP = "GCP"
    AWS = "AWS"


class PlatformBase(ABC):
    def __init__(self, logger: "StatsLogger"):
        self.thread = None
        self.should_launch = False
        self.logger = logger

    def set_should_launch(self):
        """
        When called, the worker thread will create a GPU instance on the next
        possible occasion in its runloop
        """
        self.should_launch = True

    def do_work(self):
        while True:
            if self.should_launch:
                try:
                    self.launch_instance()
                finally:
                    self.should_launch = False
            sleep(10)
            self.cleanup_resources()

    @abstractmethod
    def launch_instance(self):
        """
        Launch a new instance of the GPU into the cloud environment. Calling `self.cleanup_resources`
        is not necessary here so long as this is called from within `self.do_work`.

        """
        pass

    @abstractproperty
    def platform_type(self) -> PlatformType:
        """
        Uniquely identify this platform, exclusively used in the output logging
        """
        pass

    @abstractmethod
    def cleanup_resources(self):
        """
        Responsible for cleaning up any currently used resources. Called periodically:
        - After an exception
        - After a successful run
        - Randomly throughout lifecycle, to ensure we are not being billed for wasted compute

        """
        pass

    def is_spawned(self):
        return self.thread is not None and self.thread.is_alive()

    def spawn(self):
        # Spawn the worker logic in a separate thread
        if self.is_spawned():
            raise Exception("Already running")

        self.thread = Thread(target=self.do_work)
