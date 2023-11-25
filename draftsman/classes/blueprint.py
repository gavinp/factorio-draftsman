# blueprint.py
# -*- encoding: utf-8 -*-

"""
.. code-block:: python

    {
        "blueprint": {
            "item": "blueprint", # The associated item with this structure
            "label": str, # A user given name for this blueprint
            "label_color": { # The overall color of the label
                "r": float[0.0, 1.0] or int[0, 255], # red
                "g": float[0.0, 1.0] or int[0, 255], # green
                "b": float[0.0, 1.0] or int[0, 255], # blue
                "a": float[0.0, 1.0] or int[0, 255]  # alpha (optional)
            },
            "icons": [ # A set of signals to act as visual identification
                {
                    "signal": {"name": str, "type": str}, # Name and type of signal
                    "index": int, # In range [1, 4], starting top-left and moving across
                },
                ... # Up to 4 icons total
            ],
            "description": str, # A user given description for this blueprint
            "version": int, # The encoded version of Factorio this planner was created 
                            # with/designed for (64 bits)
            "snap-to-grid": { # The size of the grid to snap this blueprint to
                "x": int, # X dimension in units
                "y": int, # Y dimension in units
            }
            "absolute-snapping": bool, # Whether or not to use absolute placement 
                                       # (defaults to True)
            "position-relative-to-grid": { # The offset of the grid if using absolute
                                           # placement
                "x": int, # X offset in units
                "y": int, # Y offset in units
            }
            "entities": [ # A list of entities in this blueprint
                {
                    "name": str, # Name of the entity,
                    "entity_number": int, # Unique number associated with this entity 
                    "position": {"x": float, "y": float}, # Position of the entity
                    ... # Any associated Entity key/value
                },
                ...
            ]
            "tiles": [ # A list of tiles in this blueprint
                {
                    "name": str, # Name of the tile
                    "position": {"x": int, "y": int}, # Position of the tile
                },
                ...
            ],
            "schedules": [ # A list of the train schedules in this blueprint
                {
                    "schedule": [ # A list of schedule records
                        {
                            "station": str, # Name of the stop associated with these
                                            # conditions
                            "wait_conditions": [
                                {
                                    "type": str, # Name of the type of condition
                                    "compare_type": "and" or "or",
                                    "ticks": int, # If using "time" or "inactivity"
                                    "condition": CONDITION, # If a circuit condition is 
                                                            # needed
                                }
                            ],
                        },
                        ...
                    ]
                    "locomotives": [int, ...] # A list of ints, corresponding to
                                              # "entity_number" in "entities"
                },
                ...
            ]
            
        }
    }
"""

from draftsman._factorio_version import __factorio_version_info__
from draftsman.classes.association import Association
from draftsman.classes.blueprintable import Blueprintable
from draftsman.classes.entity_like import EntityLike
from draftsman.classes.entity_list import EntityList
from draftsman.classes.exportable import ValidationResult, attempt_and_reissue
from draftsman.classes.tile_list import TileList
from draftsman.classes.transformable import Transformable
from draftsman.classes.collection import EntityCollection, TileCollection
from draftsman.classes.schedule_list import ScheduleList
from draftsman.classes.spatial_data_structure import SpatialDataStructure
from draftsman.classes.spatial_hashmap import SpatialHashMap
from draftsman.classes.vector import Vector, PrimitiveVector
from draftsman.constants import ValidationMode
from draftsman.error import (
    DraftsmanError,
    UnreasonablySizedBlueprintError,
    DataFormatError,
    InvalidAssociationError,
    IncorrectBlueprintTypeError,
    MalformedBlueprintStringError,
)
from draftsman.signatures import (
    Color,
    Connections,
    DraftsmanBaseModel,
    Icon,
    IntPosition,
    uint16,
    uint64,
)
from draftsman.entity import Entity
from draftsman.tile import Tile
from draftsman.classes.schedule import Schedule
from draftsman.utils import (
    AABB,
    aabb_to_dimensions,
    encode_version,
    extend_aabb,
    flatten_entities,
    reissue_warnings,
)

from builtins import int
import copy
from typing import Any, Literal, Optional, Sequence, Union
from pydantic import (
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    field_serializer,
)


def _normalize_internal_structure(input_root, entities_in, tiles_in, schedules_in):
    """ """
    # TODO make this a member of blueprint?
    def _throw_invalid_association(entity):
        raise InvalidAssociationError(
            "'{}' at {} is connected to an entity that no longer exists".format(
                entity["name"], entity["position"]
            )
        )

    # Entities
    flattened_entities = flatten_entities(entities_in)
    entities_out = []
    for i, entity in enumerate(flattened_entities):
        # Get a copy of the dict representation of the Entity
        # (At this point, Associations are not copied and still point to original)
        # result = entity.to_dict() # copy.deepcopy?
        # result = copy.deepcopy(entity.to_dict())
        result = entity.to_dict()
        if not isinstance(result, dict):
            raise DraftsmanError(
                "{}.to_dict() must return a dict".format(type(entity).__name__)
            )
        # Add this to the output's entities and set it's entity_number
        entities_out.append(result)
        entities_out[i]["entity_number"] = i + 1

    for entity in entities_out:
        if "connections" in entity:  # Wire connections
            connections = entity["connections"]
            for side in connections:
                if side in {"1", "2"}:
                    for color in connections[side]:
                        connection_points = connections[side][color]
                        for point in connection_points:
                            old = point["entity_id"]
                            # if isinstance(old, int):
                            #     continue
                            if old() is None:  # pragma: no coverage
                                _throw_invalid_association(entity)
                            else:  # Association
                                point["entity_id"] = flattened_entities.index(old()) + 1

                elif side in {"Cu0", "Cu1"}:  # pragma: no branch
                    connection_points = connections[side]
                    for point in connection_points:
                        old = point["entity_id"]
                        # if isinstance(old, int):
                        #     continue
                        if old() is None:  # pragma: no coverage
                            _throw_invalid_association(entity)
                        else:  # Association
                            point["entity_id"] = flattened_entities.index(old()) + 1

        if "neighbours" in entity:  # Power pole connections
            neighbours = entity["neighbours"]
            for i, neighbour in enumerate(neighbours):
                if neighbour() is None:  # pragma: no coverage
                    _throw_invalid_association(entity)
                else:  # Association
                    neighbours[i] = flattened_entities.index(neighbour()) + 1

    input_root["entities"] = entities_out

    # Tiles (TODO: should also be flattened)

    tiles_out = []
    for tile in tiles_in:
        tiles_out.append(tile.to_dict())

    input_root["tiles"] = tiles_out

    # Schedules (TODO: should also be flattened)

    # We also need to process any schedules that any subgroup might have, so
    # we recursively traverse the nested entitylike tree and append each
    # schedule to the output list
    # TODO: re-add the following
    # def recurse_schedules(entitylike_list):
    #     for entitylike in entitylike_list:
    #         if hasattr(entitylike, "schedules"):  # if a group
    #             # Add the schedules of this group
    #             out_dict["schedules"] += copy.deepcopy(entitylike.schedules)
    #             # Check through this groups entities to see if they have
    #             # schedules:
    #             recurse_schedules(entitylike.entities)

    schedules_out = []
    for schedule in schedules_in:
        schedules_out.append(schedule.to_dict())

    # Change all locomotive associations to use number
    for schedule in schedules_out:
        for i, locomotive in enumerate(schedule["locomotives"]):
            if locomotive() is None:  # pragma: no coverage
                _throw_invalid_association(locomotive)
            else:  # Association
                schedule["locomotives"][i] = flattened_entities.index(locomotive()) + 1

    input_root["schedules"] = schedules_out


class Blueprint(Transformable, TileCollection, EntityCollection, Blueprintable):
    """
    Factorio Blueprint class. Contains and maintains a list of ``EntityLikes``
    and ``Tiles`` and a selection of other metadata. Inherits all the functions
    and attributes you would expect, as well as some extra functionality.
    """

    # =========================================================================
    # Format
    # =========================================================================

    class Format(DraftsmanBaseModel):
        # Private Internals (Not exported)
        _entities: EntityList = PrivateAttr()
        _tiles: TileList = PrivateAttr()
        _schedules: ScheduleList = PrivateAttr()

        class BlueprintObject(DraftsmanBaseModel):
            # Private Internals (Not exported)
            _snap_to_grid: Vector = PrivateAttr(Vector(0, 0))
            _snapping_grid_position: Vector = PrivateAttr(Vector(0, 0))
            _position_relative_to_grid: Vector = PrivateAttr(Vector(0, 0))

            item: Literal["blueprint"] = Field(
                ...,
                description="""
                The item that this BlueprintItem object is associated with. 
                Always equivalent to 'blueprint'.
                """,
            )
            label: Optional[str] = Field(
                None,
                description="""
                A string title for this Blueprint.
                """,
            )
            label_color: Optional[Color] = Field(
                None,
                description="""
                The color to draw the label of this blueprint with, if 'label'
                is present. Defaults to white if omitted.
                """,
            )
            description: Optional[str] = Field(
                None,
                description="""
                A string description given to this Blueprint.
                """,
            )
            icons: Optional[list[Icon]] = Field(
                None,
                description="""
                A set of signal pictures to associate with this Blueprint.
                """,
            )
            version: Optional[uint64] = Field(
                None,
                description="""
                What version of Factorio this UpgradePlanner was made 
                in/intended for. Specified as 4 unsigned 16-bit numbers combined, 
                representing the major version, the minor version, the patch 
                number, and the internal development version respectively. The 
                most significant digits correspond to the major version, and the 
                least to the development number. 
                """,
            )

            snap_to_grid: Optional[IntPosition] = Field(
                IntPosition(x=1, y=1),
                alias="snap-to-grid",
                description="""
                The dimension of a square grid to snap this blueprint to, if
                present.
                """,
            )
            absolute_snapping: Optional[bool] = Field(
                True,
                alias="absolute-snapping",
                description="""
                Whether or not 'snap-to-grid' is relative to the global map
                coordinates, or to the position of the first blueprint built.
                """,
            )
            # snapping_grid_position: Optional[IntPosition] = Field(None, exclude=True) # TODO: remove
            position_relative_to_grid: Optional[IntPosition] = Field(
                IntPosition(x=0, y=0),
                alias="position-relative-to-grid",
                description="""
                Any positional offset that the snapping grid has if 
                'absolute-snapping' is true.
                """,
            )

            entities: Optional[list[dict]] = Field(  # TODO
                [],
                description="""
                The list of all entities contained in the blueprint.
                """,
            )
            tiles: Optional[list[dict]] = Field(  # TODO
                [],
                description="""
                The list of all tiles contained in the blueprint.
                """,
            )
            schedules: Optional[list[dict]] = Field(  # TODO
                [],
                description="""
                The list of all schedules contained in the blueprint.
                """,
            )

            @field_validator("version", mode="before")
            @classmethod
            def normalize_to_int(cls, value: Any):
                if isinstance(value, Sequence) and not isinstance(value, str):
                    return encode_version(*value)
                return value

            @field_serializer("snap_to_grid", when_used="unless-none")
            def serialize_snapping_grid(self, _):
                return self._snap_to_grid.to_dict()

            @field_serializer("position_relative_to_grid", when_used="unless-none")
            def serialize_position_relative(self, _):
                return self._position_relative_to_grid.to_dict()

            # @model_validator(mode="before")
            # @classmethod
            # def normalize_internal_lists(cls, data):
            #     _normalize_internal_structure(data)
            #     return data

            # @model_validator(mode="after")
            # def adjust_grid_positions(self) -> "Blueprint.Format.BlueprintObject":
            #     if self.snapping_grid_position is not None:
            #         # Offset Entities
            #         for entity in self.entities:
            #             entity["position"]["x"] -= self.snapping_grid_position.x
            #             entity["position"]["y"] -= self.snapping_grid_position.y

            #         # Offset Tiles
            #         for tile in self.tiles:
            #             tile["position"]["x"] -= self.snapping_grid_position.x
            #             tile["position"]["y"] -= self.snapping_grid_position.y

            #     return self

            # TODO: maybe model serializer would work now?
            # @model_serializer
            # def serialize_blueprint(self, value):
            #     pass

        blueprint: BlueprintObject
        index: Optional[uint16] = Field(
            None,
            description="""
            The index of the blueprint inside a parent BlueprintBook's blueprint
            list. Only meaningful when this object is inside a BlueprintBook.
            """,
        )

        model_config = ConfigDict(title="Blueprint")

    # =========================================================================
    # Constructors
    # =========================================================================

    @reissue_warnings
    def __init__(
        self,
        blueprint: Union[str, dict] = None,
        index: uint16 = None,
        validate: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
        validate_assignment: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
    ):
        """
        Creates a ``Blueprint`` class. Will load the data from ``blueprint`` if
        provided, and otherwise initializes itself with defaults. ``blueprint``
        can be either an encoded blueprint string or a dict object containing
        the desired key-value pairs.

        :param blueprint_string: Either a Factorio-format blueprint string or a
            ``dict`` object with the desired keys in the correct format.
        """
        self._root: __class__.Format

        super().__init__(
            root_item="blueprint",
            root_format=Blueprint.Format.BlueprintObject,
            item="blueprint",
            init_data=blueprint,
            index=index,
            entities=[],
            tiles=[],
            schedules=[],
        )

        self.validate_assignment = validate_assignment

        self.validate(mode=validate).reissue_all(stacklevel=3)

    @reissue_warnings
    def setup(
        self,
        label: Optional[str] = None,
        label_color: Optional[Color] = None,
        description: Optional[str] = None,
        icons: Optional[list[Icon]] = None,
        version: Optional[uint64] = __factorio_version_info__,
        snapping_grid_size: Union[Vector, PrimitiveVector, None] = None,
        snapping_grid_position: Union[Vector, PrimitiveVector, None] = None,
        absolute_snapping: Optional[bool] = True,
        position_relative_to_grid: Union[Vector, PrimitiveVector, None] = None,
        entities: Union[EntityList, list[EntityLike]] = [],
        tiles: Union[TileList, list[Tile]] = [],
        schedules: Union[ScheduleList, list[Schedule]] = [],
        index: Optional[uint16] = None,
        if_unknown: str = "error",
        **kwargs,
    ):  # TODO: keyword arguments

        self._root.blueprint = Blueprint.Format.BlueprintObject(item="blueprint")

        # Item (type identifier)
        kwargs.pop("item", None)

        ### METADATA ###
        self.label = label
        self.label_color = label_color
        self.description = description
        self.icons = icons

        self.version = version

        # Snapping grid parameters
        # Handle their true keys, as well as the Draftsman attribute label
        if "snap-to-grid" in kwargs:
            self.snapping_grid_size = kwargs.pop("snap-to-grid")
        else:
            self.snapping_grid_size = snapping_grid_size

        self.snapping_grid_position = snapping_grid_position

        if "absolute-snapping" in kwargs:
            self.absolute_snapping = kwargs.pop("absolute-snapping")
        else:
            self.absolute_snapping = absolute_snapping

        if "position-relative-to-grid" in kwargs:
            self.position_relative_to_grid = kwargs.pop("position-relative-to-grid")
        else:
            self.position_relative_to_grid = position_relative_to_grid

        ### INTERNAL ###
        self._area = None
        self._tile_width = 0
        self._tile_height = 0

        ### DATA ###
        # Create spatial hashing objects to make spatial queries much quicker
        self._tile_map = SpatialHashMap()
        self._entity_map = SpatialHashMap()

        # Data lists
        # self._root[self._root_item]["entities"] = EntityList(
        #     self, kwargs.pop("entities", None)
        # )
        self._root._entities = EntityList(self, entities)

        # if "tiles" in kwargs:
        # self._root[self._root_item]["tiles"] = TileList(
        #     self, kwargs.pop("tiles", None)
        # )
        self._root._tiles = TileList(self, tiles)

        # self._root[self._root_item]["schedules"] = ScheduleList(
        #     kwargs.pop("schedules", None)
        # )
        self._root._schedules = ScheduleList(schedules)

        self.index = index

        # A bit scuffed, but
        for kwarg, value in kwargs.items():
            self._root[kwarg] = value

        # Convert circuit and power connections to Associations
        for entity in self.entities:
            if hasattr(entity, "connections"):  # Wire connections
                connections: Connections = entity.connections
                for side in connections.true_model_fields():
                    if connections[side] is None:
                        continue

                    if side in {"1", "2"}:
                        for color, _ in connections[side]:  # TODO fix
                            connection_points = connections[side][color]
                            if connection_points is None:
                                continue
                            for point in connection_points:
                                old = point["entity_id"] - 1
                                point["entity_id"] = Association(self.entities[old])

                    elif side in {"Cu0", "Cu1"}:  # pragma: no branch
                        connection_points = connections[side]
                        if connection_points is None:
                            continue  # pragma: no coverage
                        for point in connection_points:
                            old = point["entity_id"] - 1
                            point["entity_id"] = Association(self.entities[old])

            if hasattr(entity, "neighbours"):  # Power pole connections
                neighbours = entity.neighbours
                for i, neighbour in enumerate(neighbours):
                    neighbours[i] = Association(self.entities[neighbour - 1])

        # Change all locomotive numbers to use Associations
        for schedule in self.schedules:
            for i, locomotive in enumerate(schedule.locomotives):
                schedule.locomotives[i] = Association(self.entities[locomotive - 1])

    # =========================================================================
    # Blueprint properties
    # =========================================================================

    @property
    def label_color(self) -> Optional[Color]:
        """
        The color of the Blueprint's label.

        The ``label_color`` parameter exists in a dict format with the "r", "g",
        "b", and an optional "a" keys. The color can be specified like that, or
        it can be specified more succinctly as a sequence of 3-4 numbers,
        representing the colors in that order.

        The value of each of the numbers (according to Factorio spec) can be
        either in the range of [0.0, 1.0] or [0, 255]; if all the numbers are
        <= 1.0, the former range is used, and the latter otherwise. If "a" is
        omitted, it defaults to 1.0 or 255 when imported, depending on the
        range of the other numbers.

        :getter: Gets the color of the label, or ``None`` if not set.
        :setter: Sets the label color of the ``Blueprint``.
        :type: ``dict{"r": number, "g": number, "b": number, Optional("a"): number}``

        :exception DataFormatError: If the input ``label_color`` does not match
            the above specification.

        :example:

        .. code-block:: python

            blueprint.label_color = (127, 127, 127)
            print(blueprint.label_color)
            # {'r': 127.0, 'g': 127.0, 'b': 127.0}
        """
        return self._root[self._root_item].get("label_color", None)

    @label_color.setter
    def label_color(self, value: Optional[Color]):
        if self.validate_assignment:
            result = attempt_and_reissue(
                self,
                self.Format.BlueprintObject,
                self._root.blueprint,
                "label_color",
                value,
            )
            self._root[self._root_item]["label_color"] = result
        else:
            self._root[self._root_item]["label_color"] = value

    def set_label_color(self, r, g, b, a=None):
        """
        TODO
        """
        try:
            self._root[self._root_item]["label_color"] = Color(r=r, g=g, b=b, a=a)
        except ValidationError as exc:
            raise DataFormatError from exc

    # =========================================================================

    @property
    def snapping_grid_size(self) -> Optional[Vector]:
        """
        Sets the size of the snapping grid to use. The presence of this entry
        determines whether or not the Blueprint will have a snapping grid or
        not.

        The value can be set either as a ``dict`` with ``"x"`` and ``"y"`` keys,
        or as a sequence of ints.

        :getter: Gets the size of the snapping grid, or ``None`` if not set.
        :setter: Sets the size of the snapping grid. Removes the attribute if
            set to ``None``
        :type: ``dict{"x": int, "y": int}``
        """
        # return self._root[self._root_item].get("snap-to-grid", None)
        return self._root.blueprint._snap_to_grid

    @snapping_grid_size.setter
    def snapping_grid_size(self, value: Union[Vector, PrimitiveVector, None]):
        # if self.validate_assignment:
        #     result = attempt_and_reissue(
        #         self,
        #         self.Format.BlueprintObject,
        #         self._root.blueprint,
        #         "snapping_grid_size",
        #         value
        #     )
        #     self._root[self._root_item]["snapping_grid_size"] = result
        # else:
        #     self._root[self._root_item]["snapping_grid_size"] = value
        if value is None:
            self._root.blueprint._snap_to_grid.update_from_other((0, 0), int)
        else:
            self._root.blueprint._snap_to_grid.update_from_other(value, int)

    # =========================================================================

    @property
    def snapping_grid_position(self) -> Vector:
        """
        Sets the position of the snapping grid. Offsets all of the
        positions of the entities by this amount, effectively acting as a
        translation in relation to the snapping grid.

        .. NOTE::

            This function does not offset each entities position until export!

        :getter: Gets the offset amount of the snapping grid, or ``None`` if not
            set.
        :setter: Sets the offset amount of the snapping grid. Removes the
            attribute if set to ``None``.
        :type: ``dict{"x": int, "y": int}``
        """
        # return self._root[self._root_item].get("snapping_grid_position", None)
        return self._root.blueprint._snapping_grid_position

    @snapping_grid_position.setter
    def snapping_grid_position(self, value: Union[Vector, PrimitiveVector, None]):
        # if self.validate_assignment:
        #     result = attempt_and_reissue(
        #         self,
        #         self.Format.BlueprintObject,
        #         self._root.blueprint,
        #         "snapping_grid_position",
        #         value
        #     )
        #     self._root[self._root_item]["snapping_grid_position"] = result
        # else:
        #     self._root[self._root_item]["snapping_grid_position"] = value
        if value is None:
            self._root.blueprint._snapping_grid_position.update_from_other((0, 0), int)
        else:
            self._root.blueprint._snapping_grid_position.update_from_other(value, int)

    # =========================================================================

    @property
    def absolute_snapping(self) -> Optional[bool]:
        """
        Whether or not the blueprint uses absolute positioning or relative
        positioning for the snapping grid. On import, a value of ``None`` is
        interpreted as a default ``True``.

        :getter: Gets whether or not this blueprint uses absolute positioning,
            or ``None`` if not set.
        :setter: Sets whether or not to use absolute-snapping. Removes the
            attribute if set to ``None``.
        :type: ``bool``

        :exception TypeError: If set to anything other than a ``bool`` or
            ``None``.
        """
        return self._root[self._root_item].get("absolute-snapping", None)

    @absolute_snapping.setter
    def absolute_snapping(self, value: Optional[bool]):
        if self.validate_assignment:
            result = attempt_and_reissue(
                self,
                self.Format.BlueprintObject,
                self._root.blueprint,
                "absolute_snapping",
                value,
            )
            self._root[self._root_item]["absolute_snapping"] = result
        else:
            self._root[self._root_item]["absolute_snapping"] = value

    # =========================================================================

    @property
    def position_relative_to_grid(self) -> Optional[Vector]:
        """
        The absolute position of the snapping grid in the world. Only used if
        ``absolute_snapping`` is set to ``True`` or ``None``.

        :getter: Gets the absolute grid-position offset, or ``None`` if not set.
        :setter: Sets the a
        :type: ``dict{"x": int, "y": int}``
        """
        return self._root.blueprint._position_relative_to_grid

    @position_relative_to_grid.setter
    def position_relative_to_grid(self, value: Union[Vector, PrimitiveVector, None]):
        # if self.validate_assignment:
        #     result = attempt_and_reissue(
        #         self,
        #         self.Format.BlueprintObject,
        #         self._root.blueprint,
        #         "position_relative_to_grid",
        #         value
        #     )
        #     self._root[self._root_item]["position_relative_to_grid"] = result
        # else:
        #     self._root[self._root_item]["position_relative_to_grid"] = value
        if value is None:
            self._root.blueprint._position_relative_to_grid.update_from_other(
                (0, 0), int
            )
        else:
            self._root.blueprint._position_relative_to_grid.update_from_other(
                value, int
            )

    # =========================================================================

    @property
    def entities(self) -> EntityList:
        """
        The list of the Blueprint's entities. Internally the list is a custom
        class named :py:class:`.EntityList`, which has all the normal properties
        of a regular list, as well as some extra features. For more information
        on ``EntityList``, check out this writeup
        :ref:`here <handbook.blueprints.blueprint_differences>`.

        :getter: TODO
        :setter: TODO
        """
        # return self._root[self._root_item]["entities"]
        return self._root._entities

    @entities.setter
    def entities(self, value: Union[EntityList, list[EntityLike]]):
        self._entity_map.clear()

        if value is None:
            # self._root[self._root_item]["entities"].clear()
            self._root._entities.clear()
        elif isinstance(value, list):
            # self._root[self._root_item]["entities"] = EntityList(self, value)
            self._root._entities = EntityList(self, value)
        elif isinstance(value, EntityList):
            # Just don't ask
            # self._root["entities"] = copy.deepcopy(value, memo={"new_parent": self})
            # self._root[self._root_item]["entities"] = EntityList(self, value.data)
            self._root._entities = EntityList(self, value.data)
        else:
            raise TypeError("'entities' must be an EntityList, list, or None")

        self.recalculate_area()

    def on_entity_insert(
        self, entitylike: EntityLike, merge: bool
    ) -> Optional[EntityLike]:
        """
        Callback function for when an :py:class:`.EntityLike` is added to this
        Blueprint's :py:attr:`entities` list. Handles the addition of the entity
        into :py:attr:`entity_map`, and recalculates it's dimensions.

        :raises UnreasonablySizedBlueprintError: If inserting the new entity
            causes the blueprint to exceed 10,000 x 10,000 tiles in dimension.
        """
        # Here we issue warnings for overlapping entities, modify existing
        # entities if merging is enabled and delete excess entities in entitylike
        entitylike = self.entity_map.handle_overlapping(entitylike, merge)

        if entitylike is None:  # the entity has been entirely merged
            return entitylike  # early exit

        # Issue entity-specific warnings/errors if any exist for this entitylike
        entitylike.on_insert(self)

        # If no errors, add this to hashmap (as well as any of it's children)
        self.entity_map.recursive_add(entitylike)

        # Update dimensions of Blueprint
        self._area = extend_aabb(self._area, entitylike.get_world_bounding_box())
        (
            self._tile_width,
            self._tile_height,
        ) = aabb_to_dimensions(self._area)
        # Check the blueprint for unreasonable size
        # TODO: change this for warning
        if self._tile_width > 10000 or self._tile_height > 10000:
            raise UnreasonablySizedBlueprintError(
                "Current blueprint dimensions ({}, {}) exceeds the maximum size"
                " (10,000 x 10,000)".format(self._tile_width, self._tile_height)
            )

        return entitylike

    def on_entity_set(self, old_entitylike: EntityLike, new_entitylike: EntityLike):
        """
        Callback function for when an :py:class:`.EntityLike` is overwritten in
        a Blueprint's :py:attr:`entities` list. Handles the removal of the old
        ``EntityLike`` from :py:attr:`entity_map` and adds the new one in it's
        stead.
        """
        # Remove the entity and its children
        self.entity_map.recursive_remove(old_entitylike)

        # Perform any remove checks on per entity basis
        old_entitylike.on_remove(self)

        # Check for overlapping entities
        self.entity_map.handle_overlapping(new_entitylike, False)

        # Issue entity-specific warnings/errors if any exist for this entitylike
        new_entitylike.on_insert(self)

        # Add the new entity and its children
        self.entity_map.recursive_add(new_entitylike)

        # Disdain
        # self.recalculate_area()

    def on_entity_remove(self, entitylike: EntityLike):
        """
        Callback function for when an :py:class:`.EntityLike` is removed from a
        Blueprint's :py:attr:`entities` list. Handles the removal of the
        ``EntityLike`` from :py:attr:`entity_map`.
        """
        # Handle entity specific
        entitylike.on_remove(self)

        # Remove the entity and its children
        self.entity_map.recursive_remove(entitylike)

        # Perform any remove checks on per entity basis
        entitylike.on_remove(self)

        # This sucks lmao
        # self.recalculate_area()

    # =========================================================================

    @property
    def entity_map(self) -> SpatialDataStructure:
        """
        An implementation of :py:class:`.SpatialDataStructure` for ``entities``.
        Not exported; read only.
        """
        return self._entity_map

    # =========================================================================

    @property
    def tiles(self) -> TileList:
        """
        The list of the Blueprint's tiles. Internally the list is a custom
        class named :py:class:`~.TileList`, which has all the normal properties
        of a regular list, as well as some extra features.

        :example:

        .. code-block:: python

            blueprint.tiles.append("landfill")
            assert isinstance(blueprint.tiles[-1], Tile)
            assert blueprint.tiles[-1].name == "landfill"

            blueprint.tiles.insert(0, "refined-hazard-concrete", position=(1, 0))
            assert blueprint.tiles[0].position == {"x": 1.5, "y": 1.5}

            blueprint.tiles = None
            assert len(blueprint.tiles) == 0
        """
        # return self._root[self._root_item]["tiles"]
        return self._root._tiles

    @tiles.setter
    def tiles(self, value: Union[TileList, list[Tile]]):
        self.tile_map.clear()

        if value is None:
            self._root._tiles = TileList(self)  # TODO: implement clear
        elif isinstance(value, TileList):
            self._root._tiles = TileList(self, value.data)
        elif isinstance(value, list):
            self._root._tiles = TileList(self, value)
        else:
            raise TypeError("'tiles' must be a TileList, list, or None")

        self.recalculate_area()

    def on_tile_insert(self, tile: Tile, merge: bool) -> Optional[Tile]:
        """
        Callback function for when a :py:class:`.Tile` is added to this
        Blueprint's :py:attr:`tiles` list. Handles the addition of the tile
        into :py:attr:`tile_map`, and recalculates it's dimensions.

        :raises UnreasonablySizedBlueprintError: If inserting the new tile
            causes the blueprint to exceed 10,000 x 10,000 tiles in dimension.
        """
        # Handle overlapping and merging
        tile = self.tile_map.handle_overlapping(tile, merge)

        if tile is None:  # Tile was merged
            return tile  # early exit

        # Add to tile map
        self.tile_map.add(tile)

        # Update dimensions
        self._area = extend_aabb(self._area, tile.get_world_bounding_box())
        (
            self._tile_width,
            self._tile_height,
        ) = aabb_to_dimensions(self.area)

        # Check the blueprint for unreasonable size
        # TODO: remove and move elsewhere
        if self._tile_width > 10000 or self._tile_height > 10000:
            raise UnreasonablySizedBlueprintError(
                "Current blueprint dimensions ({}, {}) exceeds the maximum size"
                " (10,000 x 10,000)".format(self._tile_width, self._tile_height)
            )

        return tile

    def on_tile_set(self, old_tile: Tile, new_tile: Tile):
        """
        Callback function for when a :py:class:`.Tile` is overwritten in a
        Blueprint's :py:attr:`tiles` list. Handles the removal of the old ``Tile``
        from :py:attr:`tile_map` and adds the new one in it's stead.
        """
        self.tile_map.remove(old_tile)
        self.tile_map.handle_overlapping(new_tile, False)
        self.tile_map.add(new_tile)

        # Unfortunately, this can't be here because we need to recalculate after
        # modifying the base list, which happens *after* this function finishes
        # self.recalculate_area() # TODO

    def on_tile_remove(self, tile: Tile):
        """
        Callback function for when a :py:class:`.Tile` is removed from a
        Blueprint's :py:attr:`tiles` list. Handles the removal of the ``Tile``
        from the :py:attr:`tile_map`.
        """
        self.tile_map.remove(tile)

        # Disdain...
        # self.recalculate_area() # TODO

    # =========================================================================

    @property
    def tile_map(self) -> SpatialDataStructure:
        """
        An implementation of :py:class:`.SpatialDataStructure` for ``tiles``.
        Not exported; read only.
        """
        return self._tile_map

    # =========================================================================

    @property
    def schedules(self) -> ScheduleList:
        """
        A list of the Blueprint's train schedules.

        .. seealso::

            `<https://wiki.factorio.com/Blueprint_string_format#Schedule_object>`_

        :getter: Gets the schedules of the Blueprint.
        :setter: Sets the schedules of the Blueprint. Defaults to an empty
            :py:class:`.ScheduleList` if set to ``None``.
        :type: ``list[Schedule]``

        :exception ValueError: If set to anything other than a ``list`` of
            :py:class:`.Schedule` or .
        """
        # return self._root[self._root_item]["schedules"]
        return self._root._schedules

    @schedules.setter
    def schedules(self, value: Union[ScheduleList, list[Schedule]]):
        # TODO: this needs to be more complex. What about associations already
        # set to one blueprint being copied over to another? Should probably
        # wipe the locomotives of each schedule when doing so
        if value is None:
            # self._root[self._root_item]["schedules"] = ScheduleList()
            self._root._schedules = ScheduleList()  # TODO: clear
        elif isinstance(value, ScheduleList):
            # self._root[self._root_item]["schedules"] = value
            self._root._schedules = value
        else:
            # self._root[self._root_item]["schedules"] = ScheduleList(value)
            self._root._schedules = ScheduleList(value)

    # =========================================================================

    @property
    def area(self) -> Optional[AABB]:
        """
        The Axis-aligned Bounding Box of the Blueprint's dimensions. Not
        exported; for user aid. Read only.

        Stored internally as a list of two lists, where the first one represents
        the top-left corner (minimum) and the second the bottom-right corner
        (maximum). This attribute is updated every time an Entity or Tile is
        changed inside the Blueprint.

        :type: ``list[list[float, float], list[float, float]]``
        """
        return self._area

    # =========================================================================

    @property
    def tile_width(self) -> int:
        """
        The width of the Blueprint's ``area``, rounded up to the nearest tile.
        Read only.

        :type: ``int``
        """
        return self._tile_width

    # =========================================================================

    @property
    def tile_height(self) -> int:
        """
        The width of the Blueprint's ``area``, rounded up to the nearest tile.
        Read only.

        :type: ``int``
        """
        return self._tile_height

    # =========================================================================

    @property
    def double_grid_aligned(self) -> bool:
        """
        Whether or not the blueprint is aligned with the double grid, which is
        the grid that rail entities use, like rails and train-stops. If the
        blueprint has any entities that are double-grid-aligned, the Blueprint
        is considered double-grid-aligned. Read only.

        :type: ``bool``
        """
        for entity in self.entities:
            if entity.double_grid_aligned:
                return True

        return False

    # =========================================================================

    # @property
    # def index(self) -> Optional[uint16]:
    #     """
    #     The index of the blueprint in a parent :py:class:`BlueprintBook`. Index
    #     is automatically generated if omitted, but can be manually set with this
    #     attribute. ``index`` has no meaning when the Blueprint is not located in
    #     a BlueprintBook.

    #     :getter: Gets the index of the blueprint, or ``None`` if not set.
    #     :setter: Sets the index of the blueprint, or removes it if set to ``None``.
    #     :type: ``int``
    #     """
    #     return self._root.index

    # @index.setter
    # def index(self, value: Optional[uint16]):
    #     if self.validate_assignment:
    #         result = attempt_and_reissue(self, self.Format, self._root, "index", value)
    #         self._root.index = result
    #     else:
    #         self._root.index = value

    # =========================================================================
    # Utility functions
    # =========================================================================

    def recalculate_area(self):
        """
        Recalculates the ``area``, ``tile_width``, and ``tile_height``. Called
        automatically when an EntityLike or Tile object is altered or removed.
        Can be called by the end user, though it shouldn't be neccessary.
        """
        self._area = None
        for entity in self.entities:
            self._area = extend_aabb(self._area, entity.get_world_bounding_box())

        for tile in self.tiles:
            self._area = extend_aabb(self._area, tile.get_world_bounding_box())

        self._tile_width, self._tile_height = aabb_to_dimensions(self._area)

        # Check the blueprint for unreasonable size
        if self.tile_width > 10000 or self.tile_height > 10000:
            raise UnreasonablySizedBlueprintError(
                "Current blueprint dimensions ({}, {}) exceeds the maximum size"
                " (10,000 x 10,000)".format(self.tile_width, self.tile_height)
            )

    def validate(
        self, mode: ValidationMode = ValidationMode.STRICT, force: bool = False
    ) -> ValidationResult:
        mode = ValidationMode(mode)

        output = ValidationResult([], [])

        if mode is ValidationMode.NONE or (self.is_valid and not force):
            return output

        context: dict[str, Any] = {
            "mode": mode,
            "object": self,
            "warning_list": [],
            "assignment": False,
        }

        try:
            # print(self._root)
            result = self.Format.model_validate(
                self._root,
                strict=False,  # TODO: ideally this should be strict
                context=context,
            )
            # print(result)
            # Reassign private attributes
            result._entities = self._root._entities
            result._tiles = self._root._tiles
            result._schedules = self._root._schedules
            result.blueprint._snap_to_grid = self._root.blueprint._snap_to_grid
            result.blueprint._snapping_grid_position = (
                self._root.blueprint._snapping_grid_position
            )
            result.blueprint._position_relative_to_grid = (
                self._root.blueprint._position_relative_to_grid
            )
            # Acquire the newly converted data
            self._root = result
        except ValidationError as e:
            output.error_list.append(DataFormatError(e))

        output.warning_list += context["warning_list"]

        # if len(output.error_list) == 0:
        #     # Set the `is_valid` attribute
        #     # This means that if mode="pedantic", an entity that issues only
        #     # warnings will still not be considered valid
        #     super().validate()

        return output

    def to_dict(self, exclude_none: bool = True, exclude_defaults: bool = True) -> dict:
        # Create a copy of root, since we don't want to clobber the original
        # data when creating a dict representation
        # We skip copying the special lists because we have to handle their
        # conversion specifically and carefully
        # root_copy = {
        #     self._root_item: {
        #         k: v
        #         for k, v in self._root[self._root_item].items()
        #         if k not in {"entities", "tiles", "schedules"}
        #     },
        # }
        # if self.index is not None:
        #     root_copy["index"] = self.index

        result = super().to_dict(
            exclude_none=exclude_none, exclude_defaults=exclude_defaults
        )

        # We then convert all the entities, tiles, and schedules to
        # 1-dimensional lists, flattening any Groups that this blueprint
        # contains, and swapping their Associations into integer indexes
        _normalize_internal_structure(
            result[self._root_item], self.entities, self.tiles, self.schedules
        )

        # # Construct a model with the flattened data, not running any validation
        # # We do a number of submodels manually since model_construct is not
        # # recursive (woe be upon me)
        # out_model = Blueprint.Format.model_construct(**root_copy)
        # out_model.blueprint = Blueprint.Format.BlueprintObject.model_construct(
        #     **out_model.blueprint
        # )
        # if out_model.blueprint.icons is not None:
        #     out_model.blueprint.icons = Icons.model_construct(out_model.blueprint.icons)
        # if out_model.blueprint.snap_to_grid is not None:
        #     out_model.blueprint.snap_to_grid = (
        #         out_model.blueprint.snap_to_grid.to_dict()
        #     )
        # if out_model.blueprint.position_relative_to_grid is not None:
        #     out_model.blueprint.position_relative_to_grid = (
        #         out_model.blueprint.position_relative_to_grid.to_dict()
        #     )

        # Make sure that snapping_grid_position is respected
        # if self.snapping_grid_position is not None:
        # Offset Entities
        for entity in result["blueprint"]["entities"]:
            entity["position"]["x"] -= self.snapping_grid_position.x
            entity["position"]["y"] -= self.snapping_grid_position.y

        # Offset Tiles
        for tile in result["blueprint"]["tiles"]:
            tile["position"]["x"] -= self.snapping_grid_position.x
            tile["position"]["y"] -= self.snapping_grid_position.y

        # # We then create an output dict
        # out_dict = out_model.model_dump(
        #     by_alias=True,
        #     exclude_none=True,
        #     exclude_defaults=True,
        #     warnings=False,  # until `model_construct` is properly recursive
        # )

        # print(result)
        # print(self.snapping_grid_size)
        # print(self.position_relative_to_grid)

        if "snap-to-grid" in result["blueprint"] and result["blueprint"][
            "snap-to-grid"
        ] == {"x": 0, "y": 0}:
            del result["blueprint"]["snap-to-grid"]
        if "position-relative-to-grid" in result["blueprint"] and result["blueprint"][
            "position-relative-to-grid"
        ] == {"x": 0, "y": 0}:
            del result["blueprint"]["position-relative-to-grid"]

        if len(result["blueprint"]["entities"]) == 0:
            del result["blueprint"]["entities"]
        if len(result["blueprint"]["tiles"]) == 0:
            del result["blueprint"]["tiles"]
        if len(result["blueprint"]["schedules"]) == 0:
            del result["blueprint"]["schedules"]

        return result

    # =========================================================================

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Blueprint):
            return NotImplemented

        return (
            self.label == other.label
            and self.label_color == other.label_color
            and self.description == other.description
            and self.icons == other.icons
            and self.version == other.version
            and self.snapping_grid_size == other.snapping_grid_size
            and self.snapping_grid_position == other.snapping_grid_position
            and self.absolute_snapping == other.absolute_snapping
            and self.position_relative_to_grid == other.position_relative_to_grid
            and self.entities == other.entities
            and self.tiles == other.tiles
            and self.schedules == other.schedules
        )

    def __deepcopy__(self, memo: dict) -> "Blueprint":
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        # Make sure we copy "_entity_hashmap" first so we don't get
        # OverlappingEntitiesWarnings
        v = getattr(self, "_entity_map")
        setattr(result, "_entity_map", copy.deepcopy(v, memo))
        result.entity_map.clear()

        # We copy everything else, save for the 'root' dictionary, because
        # deepcopying those depend on some of the other attributes, so we load
        # those first
        for k, v in self.__dict__.items():
            if k == "_entity_map" or k == "_root":
                continue
            else:
                setattr(result, k, copy.deepcopy(v, memo))

        # Finally we can copy the root (most notably EntityList)
        # root = getattr(self, "_root")
        # copied_dict = {}
        # copied_dict["blueprint"] = {}
        # for rk, rv in root["blueprint"].model_fields.items():
        #     if rk == "entities":
        #         # Create a copy of EntityList with copied self as new
        #         # parent so that `result.entities[0].parent` will be
        #         # `result`
        #         memo["new_parent"] = result  # This is hacky, but fugg it
        #         copied_dict["blueprint"][rk] = copy.deepcopy(rv, memo)
        #     else:
        #         copied_dict["blueprint"][rk] = copy.deepcopy(rv, memo)
        # # Dont forget index (if present)
        # if "index" in root:
        #     copied_dict["index"] = copy.deepcopy(root["index"], memo)

        # setattr(result, "_root", copied_dict)

        root = getattr(self, "_root")

        memo["new_parent"] = result
        root_copy = copy.deepcopy(root, memo)

        setattr(result, "_root", root_copy)

        return result
