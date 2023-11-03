# warning.py

"""
Draftsman warnings. Used to enforce "Factorio-correctness", or the belief that
operations in Draftsman that are unorthodox or ignored on import to Factorio 
should be mentioned to the user.
"""


class DraftsmanWarning(UserWarning):
    """
    Root warning class for Draftsman. Useful if you want to easily ignore
    all warnings issued from the module without getting rid of warnings entirely;
    simply filter this class. This is a subclass of ``UserWarning``, and all
    other Draftsman warnings are subclasses of this.
    """

    pass


class ValueWarning(DraftsmanWarning):
    """
    Generic warning, similar to ``ValueError``. Raised when a input value is
    incorrect, but wont cause the blueprint to fail import.
    """

    pass


class DirectionWarning(DraftsmanWarning):
    """
    Raised when the direction does not match the rotation type, e.g. setting
    a 4-way rotatable Entity's direction to :py:data:`.Direction.NORTHWEST` (an
    8-way directional value).
    """

    pass


class FlippingWarning(DraftsmanWarning):
    """
    Raised when attempting to flip an entity that may or not be able to be
    flipped. This is only raised when flipping an :py:class:`.EntityCollection`
    with modded entities.
    """

    pass  # TODO: remove


class IndexWarning(DraftsmanWarning):
    """
    Raised when the index of some element is out of expected range, though not
    to the point of failing import into Factorio.
    """

    pass


class ConnectionDistanceWarning(DraftsmanWarning):
    """
    Raised when an attempted wire connection is too distant to be properly
    resolved in-game.
    """

    pass


class ConnectionSideWarning(DraftsmanWarning):
    """
    Raised when an attempted wire connection is made to an invalid side of the
    Entity.
    """

    pass


class TooManyConnectionsWarning(DraftsmanWarning):
    """
    Raised when a power connection is attempted between an power-pole that
    already has 5 or more connections.
    """

    pass


class GridAlignmentWarning(DraftsmanWarning):
    """
    Raised when an Entity is placed on odd coordinates when it's type restricts
    it's placement to the rail grid (even coordinates).
    """

    pass


class ItemLimitationWarning(DraftsmanWarning):
    """
    Raised when an item request does not match the particular entities valid
    item-types, such as incorrect ingredients for an :py:class:`.AssemblingMachine`
    with a recipe, or a :py:class:`.Lab` with non-science pack inputs.
    """

    pass


class ItemCapacityWarning(DraftsmanWarning):
    """
    Raised when the volume of item requests exeeds the number of inventory slots
    of the entity, such as requesting 10,000 iron plate to a ``"wooden-chest"``.
    """

    pass


class ModuleLimitationWarning(DraftsmanWarning):
    """
    Raised when the modules inside of an :py:class:`.Entity` conflict, either
    with the Entity's type or it's recipe.
    """

    pass


class ModuleNotAllowedWarning(DraftsmanWarning):
    """
    Raised when attempting to add a module to an entity that does not support
    the effect it gives, such as requesting productivity modules to a beacon.
    """

    pass


class ModuleCapacityWarning(DraftsmanWarning):
    """
    Raised when the number of modules in an :py:class:`.Entity` with module slots
    exceeds the total module capacity.
    """

    pass


class RecipeLimitationWarning(DraftsmanWarning):
    """
    TODO
    """

    pass


class TemperatureRangeWarning(DraftsmanWarning):
    """
    Raised when the temperature of a heat interface is outside of the range
    ``[0, 1000]``.
    """

    pass


class VolumeRangeWarning(DraftsmanWarning):
    """
    Raised when the volume of a programmable speaker is outside of the range
    ``[0.0, 1.0]``
    """

    pass


class HiddenEntityWarning(DraftsmanWarning):
    """
    Raised when an Entity that is marked as hidden is placed within a blueprint,
    since these entities cannot usually be placed with a blueprint.
    """

    pass


class OverlappingObjectsWarning(DraftsmanWarning):
    """
    Raised when the :py:class:`.CollisionSet` of a :py:class:`.SpatialLike`
    object overlaps the :py:class:`.CollisionSet` of another object, and that
    their :py:attr:`~.Entity.collision_mask` s intersect. In layman's terms, if
    two or more tiles or entities are placed on top of each other such that they
    would not be able to be placed in-game, this warning is raised.
    """

    pass


class NoEffectWarning(DraftsmanWarning):
    """
    Raised when an action is performed who's operation would not have any
    noticable change, making it's execution needless. For example, setting a
    mapping in an upgrade planner to upgrade "transport-belt" to
    "transport-belt" is possible, but is prohibited in Factorio's GUI and is
    functionally useless.
    """

    pass


class UnknownKeywordWarning(DraftsmanWarning):
    """
    Raised when a keyword is passed to an Entity/Tile constructor that is not
    known by Draftsman, likely indicating a mismatched or extra field.
    """

    pass


class UnknownElementWarning(DraftsmanWarning):
    """
    Raised when Draftsman detects a entity/item/signal/tile or any other
    Factorio construct that it cannot resolve under it's current data
    configuration. This is usually either because the identifier was mistyped,
    or because the element in question belongs to a mod that Draftsman has not
    been updated to recognize.

    This warning acts a superclass to a number of more specific versions, so you
    can catch/filter this warning and all child classes will follow suit.
    """

    pass


class UnknownEntityWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UnknownItemWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UnknownInstrumentWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UnknownNoteWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UnknownRecipeWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UnknownSignalWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class MalformedSignalWarning(DraftsmanWarning):
    """
    TODO
    """

    pass


class UnknownTileWarning(UnknownElementWarning):
    """
    TODO
    """

    pass


class UpgradeProhibitedWarning(DraftsmanWarning):
    """
    Raised when a upgrade from one entity to another in a
    :py:class:`~.UpgradePlanner` is prohibited due to the properties of one or
    both of the upgrade targets.
    """

    pass


class SignalConfigurationWarning(DraftsmanWarning):
    """
    Raised when a particular ordering of signals in a combinator lies outside of
    the available configurations permitted in-game, such as setting both the
    first and second signal of an arithmetic combinator to "signal-each".
    """

    pass


class PureVirtualDisallowedWarning(DraftsmanWarning):
    """
    Raised when a signal slot is set to a pure virtual signal in a situation
    where it is disallowed, such as an entry in a constant combinator.
    """

    pass


class BarWarning(DraftsmanWarning):
    """
    Raised when the inventory bar is set on an entity which does not have bar
    control, or when the bar amount exceeds the inventory size of the entity and
    thus would have no effect.
    """

    pass
