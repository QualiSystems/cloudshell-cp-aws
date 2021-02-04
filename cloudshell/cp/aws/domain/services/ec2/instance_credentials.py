from base64 import b64decode
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from cloudshell.shell.core.driver_context import CancellationContext

from cloudshell.cp.aws.models.ami_credentials import AMICredentials


class InstanceCredentialsService:
    DEFAULT_USER_NAME = "Administrator"

    def __init__(self, password_waiter):
        """# noqa
        :param PasswordWaiter password_waiter:
        :return:
        """
        self.password_waiter = password_waiter

    def get_windows_credentials(
        self,
        instance,
        key_value: str,
        wait_for_password: bool = True,
        cancellation_context: Optional[CancellationContext] = None,
    ) -> Optional[AMICredentials]:
        """Get windows credentials.

        :param instance: Ami amazon instance
        :param key_value: pem lines
        """
        password_data = instance.password_data()["PasswordData"]  # todo returns bytes?
        if not password_data and wait_for_password:
            password_data = self.password_waiter.wait(  # todo bytes?
                instance=instance, cancellation_context=cancellation_context
            )

        if not password_data:
            return None

        return AMICredentials(
            user_name=self.DEFAULT_USER_NAME,
            password=self.decrypt_password(key_value, password_data),
        )

    def decrypt_password(self, key_value: str, encrypted_data: str) -> str:
        private_key = load_pem_private_key(key_value.encode(), None)
        encrypted_data = b64decode(encrypted_data)
        plaintext = private_key.decrypt(encrypted_data, padding.PKCS1v15()).decode()
        return plaintext

    def get_default_linux_credentials(self):
        return AMICredentials("root", "")
