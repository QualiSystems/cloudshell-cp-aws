from typing import List

from retrying import retry


class TagNames:
    CreatedBy = "CreatedBy"
    Owner = "Owner"
    Blueprint = "Blueprint"
    ReservationId = "ReservationId"
    Domain = "Domain"
    Name = "Name"
    Isolation = "Isolation"
    IsPublic = "IsPublic"
    Type = "Type"


class IsolationTagValues:
    Exclusive = "Exclusive"
    Shared = "Shared"


class TypeTagValues:
    Default = "Default"
    Isolated = "Isolated"
    InboundPorts = "InboundPorts"
    Interface = "Interface"


class TagService:
    CREATED_BY_QUALI = "Cloudshell"

    def get_security_group_tags(self, name, isolation, reservation, type=None):  # noqa
        """# noqa
        returns the default tags with the isolation tag
        :param name: the name of the resource
        :type name: str
        :param isolation: the isolation level of the resource
        :type isolation: str
        :param reservation: reservation model
        :type reservation: cloudshell.cp.aws.models.reservation_model.ReservationModel
        :param type: the type of security group
        :type type: str
        :return: list[dict]
        """
        tags = self.get_default_tags(name, reservation)
        tags.append(self._get_kvp(TagNames.Isolation, isolation))
        if type:
            tags.append(self._get_kvp(TagNames.Type, type))
        return tags

    def get_sandbox_default_security_group_tags(self, name, reservation):
        return self.get_security_group_tags(
            name, IsolationTagValues.Shared, reservation, TypeTagValues.Default
        )

    def get_sandbox_isolated_security_group_tags(self, name, reservation):
        return self.get_security_group_tags(
            name, IsolationTagValues.Shared, reservation, TypeTagValues.Isolated
        )

    def get_custom_security_group_tags(self):
        """# noqa
        Returns the tags for custom security group
        :return:
        """
        tags = [
            self._get_kvp(TagNames.Isolation, IsolationTagValues.Exclusive),
            self._get_kvp(TagNames.Type, TypeTagValues.Interface),
        ]
        return tags

    def find_isolation_tag_value(self, tags):
        for tag in tags:
            if tag["Key"] == TagNames.Isolation:
                return tag["Value"]
        return None

    def find_type_tag_value(self, tags):
        for tag in tags:
            if tag["Key"] == TagNames.Type:
                return tag["Value"]
        return None

    def get_default_tags(self, name, reservation):
        """# noqa
        returns the default tags of a resource. Name,reservationId,createdBy
        :param str name: the name of the resource
        :type name: str
        :param reservation: reservation model
        :type reservation: cloudshell.cp.aws.models.reservation_model.ReservationModel
        :return: list[dict]
        """
        return [
            self.get_name_tag(name),
            self.get_created_by_kvp(),
            self._get_kvp(TagNames.Blueprint, reservation.blueprint),
            self._get_kvp(TagNames.Owner, reservation.owner),
            self._get_kvp(TagNames.Domain, reservation.domain),
            self.get_reservation_tag(reservation.reservation_id),
        ]

    def get_custom_tags(self, custom_tags: dict) -> List[dict]:
        """Returns the default tags of a resource. Name,reservationId,createdBy."""
        if custom_tags:
            return [self._get_kvp(k, v) for k, v in custom_tags.items()]
        return []

    def get_name_tag(self, name):
        return self._get_kvp(TagNames.Name, name)

    def get_reservation_tag(self, reservation_id):
        return self._get_kvp(TagNames.ReservationId, reservation_id)

    def get_is_public_tag(self, value):
        return self._get_kvp(TagNames.IsPublic, str(value))

    @retry(stop_max_attempt_number=30, wait_fixed=1000)
    def set_ec2_resource_tags(self, resource, tags):
        """Will set tags on a EC2 resource.

        :param resource: EC2 resource
        :param tags: Array of key pair tags
        :type tags: list[dict]
        """
        resource.create_tags(Tags=tags)

    def get_created_by_kvp(self):
        return self._get_kvp(TagNames.CreatedBy, TagService.CREATED_BY_QUALI)

    @staticmethod
    def _get_kvp(key, value):
        return {"Key": key, "Value": value}
