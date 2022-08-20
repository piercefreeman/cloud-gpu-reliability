from pydantic import BaseSettings
from base64 import b64decode


class Settings(BaseSettings):
    # IAM credentials for an individual who has access to EC2 launching
    # permissions in your account
    aws_access_key_id: str
    aws_access_secret_key: str

    gcp_project: str

    # Base64 encoded json of the service key
    gcp_service_account_base64: str

    @property
    def gcp_service_account(self):
        return b64decode(self.gcp_service_account_base64)

    class Config:
        env_prefix = "BENCHMARK__"
