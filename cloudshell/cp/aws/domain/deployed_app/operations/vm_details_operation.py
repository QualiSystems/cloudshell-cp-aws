class VmDetailsOperation:
    def __init__(self, instance_service, vm_details_provider):
        """# noqa
        :type instance_service: InstanceService
        :type vm_details_provider: VmDetailsProvider
        """
        self.instance_service = instance_service
        self.vm_details_provider = vm_details_provider

    def get_vm_details(self, instance_id, ec2_session):
        instance = self.instance_service.get_active_instance_by_id(
            ec2_session, instance_id
        )
        return self.vm_details_provider.create(instance)
