import time

from cloudshell.cp.aws.common import retry_helper


class SubnetWaiter:
    PENDING = "pending"
    AVAILABLE = "available"
    INSTANCE_STATES = [PENDING, AVAILABLE]

    def __init__(self, delay=10, timeout=10):
        """# noqa
        :param delay: the time in seconds between each pull
        :type delay: int
        :param timeout: timeout in minutes until time out exception will raised
        :type timeout: int
        """
        self.delay = delay
        self.timeout = timeout * 60

    def wait(self, subnet, state, load=False):
        """# noqa
        Will sync wait for the change of state of the subnet
        :param subnet:
        :param state:
        :param load:
        :return:
        """
        if not subnet:
            raise ValueError("Instance cannot be null")
        if state not in self.INSTANCE_STATES:
            raise ValueError("Unsupported instance state")

        retry_helper.do_with_retry(lambda: subnet.reload())

        start_time = time.time()
        while subnet.state != state:
            retry_helper.do_with_retry(lambda: subnet.reload())

            if time.time() - start_time >= self.timeout:
                raise Exception(f"Timeout: Waiting for instance to be {state} from")
            time.sleep(self.delay)

        if load:
            subnet.reload()

        return subnet
