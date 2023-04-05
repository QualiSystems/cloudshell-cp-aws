import json
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from jsonschema import validate

from cloudshell.cp.core.models import (
    CreateTrafficMirroring,
    CreateTrafficMirroringParams,
)

from cloudshell.cp.aws.domain.common.cancellation_service import (
    CommandCancellationService,
)
from cloudshell.cp.aws.domain.conncetivity.operations.traffic_mirroring_operation import (  # noqa
    CREATE_SCHEMA,
    REMOVE_SCHEMA,
    TrafficMirrorOperation,
)
from cloudshell.cp.aws.domain.services.cloudshell.traffic_mirror_pool_services import (
    SessionNumberService,
)
from cloudshell.cp.aws.domain.services.ec2.mirroring import TrafficMirrorService
from cloudshell.cp.aws.models.reservation_model import ReservationModel


class TestCreateTrafficMirroring(TestCase):
    def test_valid_create_returns_success_actions(self):
        session_number_service = SessionNumberService()
        traffic_mirror_service = TrafficMirrorService()
        cancellation_service = CommandCancellationService()
        reservation_context = Mock()
        reservation_context.reservation_id = str(uuid4())
        reservation = ReservationModel(reservation_context)
        reservation.blueprint = "lalala"
        reservation.owner = "admin"
        reservation.domain = "global"
        describe_mirror_targets_result = {
            "TrafficMirrorTargets": [
                {"NetworkInterfaceId": "bbbb", "TrafficMirrorTargetId": "cccc"}
            ]
        }

        create_traffic_mirror_target_result = {
            "TrafficMirrorTarget": {"TrafficMirrorTargetId": "tmt-5050"}
        }

        create_filter_result = {
            "TrafficMirrorFilter": {"TrafficMirrorFilterId": "tmf-5050"}
        }

        create_traffic_mirror_session_result = {
            "TrafficMirrorSession": {"TrafficMirrorSessionId": "tms-5050"}
        }

        ec2_client = Mock()
        ec2_client.describe_traffic_mirror_targets = Mock(
            return_value=describe_mirror_targets_result
        )
        ec2_client.create_traffic_mirror_target = Mock(
            return_value=create_traffic_mirror_target_result
        )
        ec2_client.create_traffic_mirror_filter = Mock(
            return_value=create_filter_result
        )
        ec2_client.create_traffic_mirror_session = Mock(
            return_value=create_traffic_mirror_session_result
        )

        cancellation_context = Mock()
        cancellation_context.is_cancelled = False
        logger = Mock()
        cloudshell = Mock()
        checkout_result = Mock()
        checkout_result.Items = [5]
        cloudshell.CheckoutFromPool = Mock(return_value=checkout_result)

        action = CreateTrafficMirroring()
        action.actionId = str(uuid4())
        action.actionParams = CreateTrafficMirroringParams()
        action.actionParams.sessionNumber = "5"
        action.actionParams.sourceNicId = "a"
        action.actionParams.targetNicId = "b"
        actions = [action]

        op = TrafficMirrorOperation(
            session_number_service,
            traffic_mirror_service,
            cancellation_service,
        )

        results = op.create(
            ec2_client=ec2_client,
            reservation=reservation,
            actions=actions,
            cancellation_context=cancellation_context,
            logger=logger,
            cloudshell=cloudshell,
        )

        self.assertTrue([x for x in results if x.success])

    def test_json_validate(self):
        request = """
        {
            "driverRequest": {
                "actions": [
                    {
                        "actionId": "a156d3db-78fe-4c19-9039-a225d0360119",
                        "type": "RemoveTrafficMirroring",
                        "sessionId": "tms-020e45731259d882d",
                        "targetNicId": ""
                    }
                ]
            }
        }
        """

        result = json.loads(request)
        for a in result["driverRequest"]["actions"]:
            validate(a, REMOVE_SCHEMA)

        create_request = """
        {
            "driverRequest": {
                                "actions": [
                                                {
                                                    "actionId": "a156d3db-78fe-4c19-9039-a225d0360119",
                                                    "type": "CreateTrafficMirroring",
                                                    "actionParams": {"type": "CreateTrafficMirroringParams",
                                                                     "sourceNicId": "eni-0bf9b403bd8d36a79",
                                                                     "targetNicId": "eni-060613fdccd935b67",
                                                                     "sessionNumber": "",
                                                                     "filterRules": [
                                                                        {
                                                                            "type": "TrafficFilterRule",
                                                                            "direction": "ingress",
                                                                            "sourcePortRange": {
                                                                                "type": "PortRange",
                                                                                "fromPort": "123",
                                                                                "toPort": "123"
                                                                            },
                                                                            "protocol": "udp"
                                                                        }
                                                                     ]
                                                                     }
                                                }
                                            ]
                              }
        }
        """  # noqa

        create_actions2 = json.loads(create_request)
        for a in create_actions2["driverRequest"]["actions"]:
            validate(a, CREATE_SCHEMA)
