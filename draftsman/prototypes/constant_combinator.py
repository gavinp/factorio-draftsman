# constant_combinator.py

from draftsman.classes.entity import Entity
from draftsman.classes.exportable import attempt_and_reissue
from draftsman.classes.mixins import (
    ControlBehaviorMixin,
    CircuitConnectableMixin,
    DirectionalMixin,
)
from draftsman.classes.vector import Vector, PrimitiveVector
from draftsman.constants import Direction, ValidationMode
from draftsman.error import DataFormatError
from draftsman.signatures import (
    Connections,
    DraftsmanBaseModel,
    SignalFilter,
    SignalID,
    int32,
    int64,
    uint32,
)
from draftsman.warning import PureVirtualDisallowedWarning

from draftsman.data.entities import constant_combinators
from draftsman.data import entities, signals

from pydantic import ConfigDict, Field, ValidationError, field_validator
from typing import Any, Literal, Optional, Union


class ConstantCombinator(
    ControlBehaviorMixin, CircuitConnectableMixin, DirectionalMixin, Entity
):
    """
    A combinator that holds a number of constant signals that can be output to
    the circuit network.
    """

    class Format(
        ControlBehaviorMixin.Format,
        CircuitConnectableMixin.Format,
        DirectionalMixin.Format,
        Entity.Format,
    ):
        class ControlBehavior(DraftsmanBaseModel):
            filters: Optional[list[SignalFilter]] = Field(
                [],
                description="""
                The set of constant signals that are emitted when this 
                combinator is turned on.
                """,
            )
            is_on: Optional[bool] = Field(
                True,
                description="""
                Whether or not this constant combinator is toggled on or off.
                """,
            )

            @field_validator("filters", mode="before")
            @classmethod
            def normalize_input(cls, value: Any):
                if isinstance(value, list):
                    for i, entry in enumerate(value):
                        if isinstance(entry, tuple):
                            value[i] = {
                                "index": i + 1,
                                "signal": entry[0],
                                "count": entry[1],
                            }

                return value

        control_behavior: Optional[ControlBehavior] = ControlBehavior()

        model_config = ConfigDict(title="ConstantCombinator")

    def __init__(
        self,
        name: str = constant_combinators[0],
        position: Union[Vector, PrimitiveVector] = None,
        tile_position: Union[Vector, PrimitiveVector] = (0, 0),
        direction: Direction = Direction.NORTH,
        connections: Connections = Connections(),
        control_behavior: Format.ControlBehavior = Format.ControlBehavior(),
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

        self._root: __class__.Format
        self.control_behavior: __class__.Format.ControlBehavior

        super().__init__(
            name,
            constant_combinators,
            position=position,
            tile_position=tile_position,
            direction=direction,
            connections=connections,
            control_behavior=control_behavior,
            tags=tags,
            **kwargs
        )

        self.validate_assignment = validate_assignment

        if validate:
            self.validate(mode=validate).reissue_all(stacklevel=3)

    # =========================================================================

    @property
    def item_slot_count(self) -> uint32:
        """
        The total number of signal slots that this ``ConstantCombinator`` can
        hold. Equivalent to ``"item_slot_count"`` from Factorio's ``data.raw``.
        Returns ``None`` if the entity's name is not recognized by Draftsman.
        Not exported; read only.

        :type: ``int``
        """
        return entities.raw.get(self.name, {"item_slot_count": None})["item_slot_count"]

    # =========================================================================

    @property
    def signals(self) -> Optional[list[SignalFilter]]:
        """
        The list of signals that this :py:class:`.ConstantCombinator` currently
        holds. Aliases ``control_behavior["filter"]``. Can be set to one of two
        formats:

        .. code-block:: python

            [{"index": int, "signal": SIGNAL_ID, "count": int}, ...]
            # Or
            [(signal_name, signal_value), (str, int), ...]

        If the data is set to the latter, it is converted to the former.

        Raises :py:class:`.DraftsmanWarning` if a signal is set to one of the
        pure virtual signals ("signal-everything", "signal-anything", or
        "signal-each").

        :getter: Gets the signals of the combinators, or an empty list if not
            set.
        :setter: Sets the signals of the combinators. Removes the key if set to
            ``None``.
        :type: :py:data:`.SIGNAL_FILTERS`

        :exception DataFormatError: If set to anything that does not match the
            format specified above.
        """
        return self.control_behavior.filters

    @signals.setter
    def signals(self, value: Optional[list[SignalFilter]]):
        if self.validate_assignment:
            result = attempt_and_reissue(
                self,
                type(self).Format.ControlBehavior,
                self.control_behavior,
                "filters",
                value,
            )
            self.control_behavior.filters = result
        else:
            self.control_behavior.filters = value

    # =========================================================================

    @property
    def is_on(self) -> Optional[bool]:
        """
        Whether or not this Constant combinator is "on" and currently outputting
        it's contents to connected wires. Default state is enabled.

        :getter: Gets whether or not this combinator is enabled, or ``None`` if
            not set.
        :setter: Sets whether or not this combinator is enabled. Removes the key
            if set to ``None``.
        :type: ``bool``
        """
        return self.control_behavior.is_on

    @is_on.setter
    def is_on(self, value: Optional[bool]):
        if self.validate_assignment:
            result = attempt_and_reissue(
                self,
                type(self).Format.ControlBehavior,
                self.control_behavior,
                "is_on",
                value,
            )
            self.control_behavior.is_on = result
        else:
            self.control_behavior.is_on = value

    # =========================================================================

    def set_signal(
        self, index: int64, signal: Union[str, SignalID, None], count: int32 = 0
    ):
        """
        Set the signal of the ``ConstantCombinator`` at a particular index with
        a particular value.

        :param index: The index of the signal.
        :param signal: The name of the signal.
        :param count: The value of the signal.

        :exception TypeError: If ``index`` is not an ``int``, if ``name`` is not
            a ``str``, or if ``count`` is not an ``int``.
        """

        try:
            new_entry = SignalFilter(index=index + 1, signal=signal, count=count)
        except ValidationError as e:
            raise DataFormatError(e) from None

        if self.control_behavior.filters is None:
            self.control_behavior.filters = []

        # Check to see if filters already contains an entry with the same index
        existing_index = None
        for i, signal_filter in enumerate(self.control_behavior.filters):
            if index + 1 == signal_filter["index"]:  # Index already exists in the list
                if signal is None:  # Delete the entry
                    del self.control_behavior["filters"][i]
                    return
                else:
                    existing_index = i
                    break

        if existing_index is not None:
            self.control_behavior.filters[existing_index] = new_entry
        else:
            self.control_behavior.filters.append(new_entry)

    def get_signal(self, index: int64) -> Optional[SignalFilter]:
        """
        Get the :py:data:`.SIGNAL_FILTER` ``dict`` entry at a particular index,
        if it exists.

        :param index: The index of the signal to analyze.

        :returns: A ``dict`` that conforms to :py:data:`.SIGNAL_FILTER`, or
            ``None`` if nothing was found at that index.
        """
        filters = self.control_behavior.get("filters", None)
        if not filters:
            return None

        return next((item for item in filters if item["index"] == index + 1), None)

    # =========================================================================

    __hash__ = Entity.__hash__
