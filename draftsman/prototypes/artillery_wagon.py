# artillery_wagon.py

from draftsman.classes.entity import Entity
from draftsman.classes.mixins import RequestItemsMixin, OrientationMixin
from draftsman.classes.vector import Vector, PrimitiveVector
from draftsman.constants import Orientation, ValidationMode
from draftsman.signatures import uint32

from draftsman.data.entities import artillery_wagons

from pydantic import ConfigDict
from typing import Any, Literal, Union


class ArtilleryWagon(RequestItemsMixin, OrientationMixin, Entity):
    """
    An artillery train car.
    """

    class Format(RequestItemsMixin.Format, OrientationMixin.Format, Entity.Format):
        model_config = ConfigDict(title="ArtilleryWagon")

    def __init__(
        self,
        name: str = artillery_wagons[0],
        position: Union[Vector, PrimitiveVector] = None,
        tile_position: Union[Vector, PrimitiveVector] = (0, 0),
        orientation: Orientation = Orientation.NORTH,
        items: dict[str, uint32] = {},  # TODO: ItemID
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
            artillery_wagons,
            position=position,
            tile_position=tile_position,
            orientation=orientation,
            items=items,
            tags=tags,
            **kwargs
        )

        self.validate_assignment = validate_assignment

        if validate:
            self.validate(mode=validate).reissue_all(stacklevel=3)

    # TODO: read the gun prototype for this entity and use that to determine the
    # kinds of ammo it uses
    # Though what about mods?

    # =========================================================================

    __hash__ = Entity.__hash__
