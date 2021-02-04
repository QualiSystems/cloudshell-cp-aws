from cloudshell.cp.core.models import TrafficMirroringResult


class TrafficMirrorFulfillment:
    def __init__(self, action, reservation):
        """# noqa
        :param cloudshell.cp.core.models.CreateTrafficMirroring action:
        :return:
        """
        self.reservation = reservation
        self.traffic_mirror_filter_id = None
        self.action_id = action.actionId
        self.target_nic_id = action.actionParams.targetNicId
        self.traffic_mirror_target_id = None
        self.source_nic_id = action.actionParams.sourceNicId
        self.session_number = action.actionParams.sessionNumber
        self.session_name = self._get_mirror_session_name()
        self.mirror_session_id = None
        self.filter_rules = action.actionParams.filterRules

    def _get_mirror_session_name(self):
        return f"{self.session_number}_{self.source_nic_id}_{self.target_nic_id}"


def create_results(success, fulfillments, message):
    return [
        TrafficMirroringResult(
            actionId=f.action_id,
            success=success,
            infoMessage=message,
            errorMessage=message,
            sessionId=f.mirror_session_id or "",
        )
        for f in fulfillments
    ]
