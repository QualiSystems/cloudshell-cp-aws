from cloudshell.shell.core.driver_context import ReservationContextDetails


class ReservationModel:
    def __init__(self, reservation_context: ReservationContextDetails):
        self.reservation_id = reservation_context.reservation_id
        self.owner = reservation_context.owner_user
        self.blueprint = reservation_context.environment_name
        self.domain = reservation_context.domain
