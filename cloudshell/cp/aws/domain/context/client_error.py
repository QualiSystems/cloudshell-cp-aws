import sys
from contextlib import contextmanager

from botocore.exceptions import ClientError


class ClientErrorWrapper:
    @contextmanager
    def wrap(self):
        try:
            yield
        except ClientError as e:
            err_class = type(e)
            raise err_class(
                f"AWS API Error. Please consider retrying the operation. {e}",
                sys.exc_info()[2],
            )
