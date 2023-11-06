from __future__ import annotations

import json
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from cloudshell.cp.aws.domain.handlers.ec2 import TagsHandler
from cloudshell.cp.aws.models.deploy_aws_ec2_ami_instance_resource_model import (
    DeployAWSEc2AMIInstanceResourceModel,
)
from cloudshell.cp.aws.models.reservation_model import ReservationModel

if TYPE_CHECKING:
    from mypy_boto3_iam import IAMClient


def create_profile_for_instance(
    app_blueprint_name: str,
    deploy_app: DeployAWSEc2AMIInstanceResourceModel,
    iam_client: IAMClient,
    reservation: ReservationModel,
    logger,
) -> str:
    role_name = _get_role_name(app_blueprint_name, reservation.reservation_id)
    tags = TagsHandler.create_default_tags(role_name, reservation)
    logger.info(f"Creating role {role_name}")
    iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["sts:AssumeRole"],
                        "Principal": {"Service": ["ec2.amazonaws.com"]},
                    }
                ],
            }
        ),
        Tags=tags.aws_tags,
    )
    for policy_arn in deploy_app.policies_arns_for_new_role:
        logger.info(f"Attaching policy {policy_arn} to role {role_name}")
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)

    logger.info(f"Creating instance profile {role_name}")
    iam_client.create_instance_profile(
        InstanceProfileName=role_name, Tags=tags.aws_tags
    )
    logger.info(f"Adding role {role_name} to instance profile {role_name}")
    iam_client.add_role_to_instance_profile(
        InstanceProfileName=role_name, RoleName=role_name
    )
    return role_name


def delete_profile_for_instance(
    app_blueprint_name: str,
    iam_client: IAMClient,
    reservation: ReservationModel,
    logger,
) -> None:
    role_name = _get_role_name(app_blueprint_name, reservation.reservation_id)
    try:
        # detach policies
        resp = iam_client.list_attached_role_policies(RoleName=role_name)
    except ClientError as e:
        if "NoSuchEntity" not in str(e):
            raise
    else:
        logger.info(f"Deleting role {role_name}")
        for policy in resp["AttachedPolicies"]:
            iam_client.detach_role_policy(
                RoleName=role_name, PolicyArn=policy["PolicyArn"]
            )
        # detach role from profile
        iam_client.remove_role_from_instance_profile(
            InstanceProfileName=role_name, RoleName=role_name
        )
        # delete role
        iam_client.delete_role(RoleName=role_name)
        # delete profile
        iam_client.delete_instance_profile(InstanceProfileName=role_name)


def _get_role_name(app_blueprint_name: str, reservation_id: str) -> str:
    return f"{app_blueprint_name}-{reservation_id}"
