# electric_pole.py
# -*- encoding: utf-8 -*-

from __future__ import unicode_literals

from draftsman.classes.entity import Entity
from draftsman.classes.mixins import CircuitConnectableMixin, PowerConnectableMixin
from draftsman.classes.vector import Vector, PrimitiveVector
from draftsman.constants import ValidationMode
from draftsman.data import entities
from draftsman.signatures import Connections, uint64

from draftsman.data.entities import electric_poles

from pydantic import ConfigDict
from typing import Any, Literal, Union


class ElectricPole(CircuitConnectableMixin, PowerConnectableMixin, Entity):
    """
    An entity used to distribute electrical energy as a network.
    """

    class Format(
        CircuitConnectableMixin.Format, PowerConnectableMixin.Format, Entity.Format
    ):
        model_config = ConfigDict(title="ElectricPole")

    def __init__(
        self,
        name=electric_poles[0],
        position: Union[Vector, PrimitiveVector] = None,
        tile_position: Union[Vector, PrimitiveVector] = (0, 0),
        neighbours: list[uint64] = [],
        connections: Connections = Connections(),
        tags: dict[str, Any] = {},
        validate: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
        validate_assignment: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
        **kwargs
    ):
        """
        TODO
        """

        super().__init__(
            name,
            electric_poles,
            position=position,
            tile_position=tile_position,
            neighbours=neighbours,
            connections=connections,
            tags=tags,
            **kwargs
        )

        self.validate_assignment = validate_assignment

        if validate:
            self.validate(mode=validate).reissue_all(stacklevel=3)

    # =========================================================================

    @property
    def circuit_wire_max_distance(self) -> float:
        # Electric poles use a custom key (for some reason)
        return entities.raw.get(self.name, {"maximum_wire_distance": None}).get(
            "maximum_wire_distance", 0
        )

    # =========================================================================

    __hash__ = Entity.__hash__
