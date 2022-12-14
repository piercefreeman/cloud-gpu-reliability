from abc import ABC, abstractmethod
from threading import Thread
from time import sleep
from uuid import uuid4, UUID
from gpu_reliability.models import PlatformType, LaunchRequest
from gpu_reliability.stats_logger import StatsLogger, Stat
from dataclasses import dataclass, field
from typing import Optional


INSTANCE_TAG = "gpu-reliability-test"
INSTANCE_TAG_VALUE = "true"


class PlatformBase(ABC):
    def __init__(self, storage: StatsLogger, cleanup_interval=60):
        """
        :param cleanup_interval: How often to clean up resources (in seconds) even if we haven't
            actively launched an instance. Used for garbage collection in the case of unrecoverable
            crashes.

        """
        self.thread = None
        self.storage = storage
        self.cleanup_interval = cleanup_interval

        self.should_launch: Optional[LaunchRequest] = None
        self.should_quit = False

    def set_should_launch(self, should_launch: LaunchRequest):
        """
        When called, the worker thread will create a GPU instance on the next
        possible occasion in its runloop
        """
        self.should_launch = should_launch

    def quit(self):
        self.should_quit = True

    def do_work(self):
        until_cleanup = self.cleanup_interval

        while True:
            if self.should_launch:
                try:
                    self.launch_instance(self.should_launch)
                except Exception as e:
                    self.storage.write(
                        Stat(
                            platform=self.platform_type,
                            request=self.should_launch,
                            create_success=False,
                            error=str(e)
                        )
                    )
                    raise
                finally:
                    self.set_should_launch(None)
                    self.cleanup_resources()

            if self.should_quit:
                return

            # This event loop effectively runs every second
            # This is convenient because it allows us to quickly respond to quit signals
            # while still ensuring that we have a timer counting for the cleanup
            sleep(1)

            until_cleanup -= 1
            if until_cleanup <= 0:
                until_cleanup = self.cleanup_interval
                self.cleanup_resources()

    @abstractmethod
    def launch_instance(self):
        """
        Launch a new instance of the GPU into the cloud environment. Calling `self.cleanup_resources`
        is not necessary here so long as this is called from within `self.do_work`.

        """
        pass

    @property
    @abstractmethod
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

    @property
    def is_spawned(self):
        return self.thread is not None and self.thread.is_alive()

    def spawn(self):
        # Spawn the worker logic in a separate thread
        if self.is_spawned:
            raise Exception("Already running")

        self.thread = Thread(target=self.do_work)
        self.thread.start()

    def join(self):
        if self.thread is not None:
            self.thread.join()
