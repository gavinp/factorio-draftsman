# logistic_passive_container.py

from draftsman.prototypes.mixins import (
    CircuitConnectableMixin, InventoryMixin, Entity
)
from draftsman.warning import DraftsmanWarning

from draftsman.data.entities import logistic_passive_containers

import warnings


class LogisticPassiveContainer(CircuitConnectableMixin, InventoryMixin, Entity):
    """
    """
    def __init__(self, name = logistic_passive_containers[0], **kwargs):
        # type: (str, **dict) -> None
        super(LogisticPassiveContainer, self).__init__(
            name, logistic_passive_containers, **kwargs
        )

        for unused_arg in self.unused_args:
            warnings.warn(
                "{} has no attribute '{}'".format(type(self), unused_arg),
                DraftsmanWarning,
                stacklevel = 2
            )