# turret.py

from draftsman.classes.entity import Entity
from draftsman.classes.mixins import RequestItemsMixin, DirectionalMixin
from draftsman.classes.vector import Vector, PrimitiveVector
from draftsman.constants import Direction, ValidationMode
from draftsman.signatures import uint32

from draftsman.data.entities import turrets

from pydantic import ConfigDict
from typing import Any, Literal, Union


class Turret(RequestItemsMixin, DirectionalMixin, Entity):
    """
    An entity that automatically targets and attacks other forces within range.
    Catch-all class for every type of turret in Factorio.
    """

    class Format(RequestItemsMixin.Format, DirectionalMixin.Format, Entity.Format):
        model_config = ConfigDict(title="Turret")

    def __init__(
        self,
        name: str = turrets[0],
        position: Union[Vector, PrimitiveVector] = None,
        tile_position: Union[Vector, PrimitiveVector] = (0, 0),
        direction: Direction = Direction.NORTH,
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
        Construct a new turret.

        TODO
        """

        super().__init__(
            name,
            turrets,
            position=position,
            tile_position=tile_position,
            direction=direction,
            tags=tags,
            **kwargs
        )

        self.validate_assignment = validate_assignment

        if validate:
            self.validate(mode=validate).reissue_all(stacklevel=3)

    # =========================================================================

    __hash__ = Entity.__hash__
