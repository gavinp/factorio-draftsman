# blueprintable.py

from draftsman import __factorio_version_info__
from draftsman.classes.exportable import (
    Exportable,
    ValidationResult,
    attempt_and_reissue,
    apply_assignment,
    test_replace_me,
)
from draftsman.constants import ValidationMode
from draftsman.error import DataFormatError, IncorrectBlueprintTypeError
from draftsman.signatures import (
    DraftsmanBaseModel,
    Icon,
    normalize_version,
    uint16,
    uint64,
)
from draftsman.data.signals import signal_dict
from draftsman.utils import (
    decode_version,
    JSON_to_string,
    string_to_JSON,
    reissue_warnings,
    version_tuple_to_string,
)

from abc import ABCMeta, abstractmethod

import json
from pydantic import field_validator, ValidationError
from typing import Any, Literal, Optional, Sequence, Union


class Blueprintable(Exportable, metaclass=ABCMeta):
    """
    An abstract base class representing "blueprint-like" objects, such as
    :py:class:`.Blueprint`, :py:class:`.DeconstructionPlanner`,
    :py:class:`.UpgradePlanner`, and :py:class:`.BlueprintBook`.

    All attributes default to keys in the ``self._root`` object, but can (and
    are) overwritten in select circumstances.
    """

    @reissue_warnings
    def __init__(
        self,
        root_format: DraftsmanBaseModel,
        root_item: str,
        init_data: Union[str, dict, None],
        index: uint16,
        validate: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
        **kwargs
    ):
        """
        Initializes the private ``_root`` data dictionary, as well as setting
        the ``item`` name.
        """
        self._root: self.Format

        # Init exportable
        super().__init__()

        # We don't this to be active when constructing, so we it to NONE now and
        # to whatever it should be later in the child-most subclass
        self.validate_assignment = ValidationMode.NONE

        self._root_item = root_item
        # self._root_format = (root_format,)
        self._root_format = root_format
        # self._root = self.Format.model_construct(**{self._root_item: {"item": item, **kwargs}})
        # self._root[self._root_item] = root_format.model_construct(self._root[self._root_item])
        # Create a Pydantic model instance for quick validation (at the cost of
        # startup time and memory)
        self._root = self.Format.model_validate(
            {self._root_item: {"item": root_item, **kwargs}, "index": index},
            context={"construction": True, "mode": ValidationMode.NONE},
        )
        # print("blueprintable")
        # print(self._root)

        # self._root = {}
        # self._root[self._root_item] = {}
        # self._root[self._root_item]["item"] = root_item

        if init_data is None:
            self.setup()
        elif isinstance(init_data, str):
            self.load_from_string(init_data, validate=validate)
        elif isinstance(init_data, dict):
            self.setup(
                **init_data[self._root_item],
                index=init_data.get("index", None),
                validate=validate,
            )
        else:
            raise DataFormatError(
                "'{}' must be a factorio blueprint string, a dictionary, or None".format(
                    self._root_item
                )
            )

    @reissue_warnings
    def load_from_string(
        self,
        string: str,
        validate: Union[
            ValidationMode, Literal["none", "minimum", "strict", "pedantic"]
        ] = ValidationMode.STRICT,
    ):
        """
        Load the :py:class:`.Blueprintable` with the contents of ``string``.

        Raises :py:class:`.UnknownKeywordWarning` if there are any unrecognized
        keywords in the blueprint string for this particular blueprintable.

        :param string: Factorio-encoded blueprint string.

        :exception MalformedBlueprintStringError: If the input string is not
            decodable to a JSON object.
        :exception IncorrectBlueprintTypeError: If the input string is of a
            different type than the base class, such as trying to load the
            string of an upgrade planner into a ``Blueprint`` object.
        """
        root = string_to_JSON(string)
        # Ensure that the blueprint string actually matches the type of the
        # selected class
        if self._root_item not in root:
            raise IncorrectBlueprintTypeError(
                "Expected root keyword '{}', found '{}'; input strings must "
                "match the type of the blueprintable being constructed, or you "
                "can use "
                "`draftsman.blueprintable.get_blueprintable_from_string()` to "
                "generically accept any kind of blueprintable object".format(
                    self._root_item, next(iter(root))
                )
            )

        self.setup(
            **root[self._root_item],
            index=root.get("index", None),
            validate=validate,
        )

    @abstractmethod
    def setup(self, **kwargs):  # pragma: no coverage
        """
        Setup the Blueprintable's parameters with the input keywords as values.
        Primarily used by the constructor, but can be used at any time to set
        a large number of keys all at once.

        Raises :py:class:`.DraftsmanWarning` if any of the input keywords are
        unrecognized.

        :param kwargs: The dict of all keywords to set in the blueprint.

        .. NOTE::

            Calling ``setup`` only sets the specified keys to their values, and
            everything else to either their defaults or ``None``. In other words,
            the effect of calling setup multiple times is not cumulative, but
            rather set to the keys in the last call.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import Blueprint
            >>> blueprint = Blueprint()
            >>> blueprint.setup(label="test")
            >>> assert blueprint.label == "test"
            >>> test_dict = {"description": "testing..."}
            >>> blueprint.setup(**test_dict)
            >>> assert blueprint.description == "testing..."
            >>> assert blueprint.label == None # Gone!
        """
        pass

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def item(self) -> str:
        """
        Always the name of the corresponding Factorio item to this blueprintable
        instance. Read only.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import (
            ...     Blueprint, DeconstructionPlanner, UpgradePlanner, BlueprintBook
            ... )
            >>> Blueprint().item
            'blueprint'
            >>> DeconstructionPlanner().item
            'deconstruction-planner'
            >>> UpgradePlanner().item
            'upgrade-planner'
            >>> BlueprintBook().item
            'blueprint-book'
        """
        return self._root[self._root_item]["item"]

    # =========================================================================

    @property
    def label(self) -> Optional[str]:
        """
        The user given name (title) of the blueprintable.

        :getter: Gets the label, or ``None`` if not set.
        :setter: Sets the label of this object.

        :exception TypeError: When setting ``label`` to something other than
            ``str`` or ``None``.
        """
        return self._root[self._root_item]["label"]

    @label.setter
    def label(self, value: Optional[str]):
        test_replace_me(
            self,
            self._root_format,
            self._root[self._root_item],
            "label",
            value,
            self.validate_assignment,
        )
        # if self.validate_assignment:
        #     result = attempt_and_reissue(
        #         self, self._root_format, self._root[self._root_item], "label", value
        #     )
        #     self._root[self._root_item]["label"] = result
        # else:
        #     self._root[self._root_item]["label"] = value

    # =========================================================================

    @property
    def description(self) -> Optional[str]:
        """
        The description of the blueprintable. Visible when hovering over it when
        inside someone's inventory.

        :getter: Gets the description, or ``None`` if not set.
        :setter: Sets the description of the object. Removes the attribute if
            set to ``None``.

        :exception TypeError: If setting to anything other than a ``str`` or
            ``None``.
        """
        return self._root[self._root_item].get("description", None)

    @description.setter
    def description(self, value: Optional[str]):
        if self.validate_assignment:
            result = attempt_and_reissue(
                self,
                self._root_format,
                self._root[self._root_item],
                "description",
                value,
            )
            self._root[self._root_item]["description"] = result
        else:
            self._root[self._root_item]["description"] = value

    # =========================================================================

    @property
    def icons(self) -> Optional[list[Icon]]:
        """
        The visible icons of the blueprintable, as shown in the icon in
        Factorio's GUI.

        Stored as a list of ``Icon`` objects, which are dicts that contain a
        ``"signal"`` dict and an ``"index"`` key. Icons can be specified in this
        format, or they can be specified more succinctly with a simple list of
        signal names as strings.

        All signal entries must be a valid signal ID. If the input format is a
        list of strings, the index of each item will be it's place in the list
        + 1. A max of 4 icons are permitted.

        :getter: Gets the list if icons, or ``None`` if not set.
        :setter: Sets the icons of the Blueprint. Removes the attribute if set
            to ``None``.

        :exception DataFormatError: If the set value does not match either of
            the specifications above.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import Blueprint
            >>> blueprint = Blueprint()
            >>> blueprint.icons = ["transport-belt"]
            >>> blueprint.icons
            [{'index': 1, 'signal': {'name': 'transport-belt', 'type': 'item'}}]
        """
        return self._root[self._root_item]["icons"]

    @icons.setter
    def icons(self, value: Union[list[str], list[Icon], None]):
        test_replace_me(
            self,
            self._root_format,
            self._root[self._root_item],
            "icons",
            value,
            self.validate_assignment,
        )
        # if self.validate_assignment:
        #     print("validated")
        #     # Question; does the validation of an assignment depend on other components?
        #     # Or, in other words, do we have to rerun the entire validation suite when
        #     # we change just one entry?
        #     # A: perhaps. For example, what if we change the position of an entity
        #     # which should now issue overlapping warnings, or even worse, an entire
        #     # group object?
        #     # In a perfect world it might be possible to "optimize" the amount
        #     # of validation that occurs, but that currently lies firmly outside
        #     # the scope of 2.0
        #     print(self._root[self._root_item])
        #     result = attempt_and_reissue(
        #         self, self._root_format, self._root[self._root_item], "icons", value
        #     )
        #     self._root[self._root_item]["icons"] = result
        # else:
        #     print("non-validated")
        #     result = apply_assignment(
        #         self, self._root_format, self._root[self._root_item], "icons", value
        #     )
        #     self._root[self._root_item]["icons"] = result

    def set_icons(self, *icon_names):
        """
        TODO
        """
        new_icons = [None] * len(icon_names)
        for i, icon in enumerate(icon_names):
            new_icons[i] = {"index": i + 1, "signal": icon}
        self.icons = new_icons

    # =========================================================================

    @property
    def version(self) -> Optional[uint64]:
        """
        The version of Factorio the Blueprint was created in/intended for.

        The Blueprint ``version`` is a 64-bit integer, which is a bitwise-OR
        of four 16-bit numbers. You can interpret this number more clearly by
        decoding it with :py:func:`draftsman.utils.decode_version`, or you can
        use the functions :py:func:`version_tuple` or :py:func:`version_string`
        which will give you a more readable output. This version number defaults
        to the version of Factorio that Draftsman is currently initialized with.

        The version can be set either as said 64-bit int, or a sequence of
        ints, usually a list or tuple, which is then encoded into the combined
        representation. The sequence is defined as:
        ``[major_version, minor_version, patch, development_release]``
        with ``patch`` and ``development_release`` defaulting to 0.

        .. seealso::

            `<https://wiki.factorio.com/Version_string_format>`_

        :getter: Gets the version, or ``None`` if not set.
        :setter: Sets the version of the Blueprint. Removes the attribute if set
            to ``None``.

        :exception TypeError: If set to anything other than an ``int``, sequence
            of ``ints``, or ``None``.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import Blueprint
            >>> blueprint = Blueprint()
            >>> blueprint.version = (1, 0) # version 1.0.0.0
            >>> assert blueprint.version == 281474976710656
            >>> assert blueprint.version_tuple() == (1, 0, 0, 0)
            >>> assert blueprint.version_string() == "1.0.0.0"
        """
        return self._root[self._root_item].get("version", None)

    @version.setter
    def version(self, value: Union[uint64, Sequence[uint16]]):
        value = normalize_version(value)
        if self.validate_assignment:
            result = attempt_and_reissue(
                self, self._root_format, self._root[self._root_item], "version", value
            )
            self._root[self._root_item]["version"] = result
        else:
            self._root[self._root_item]["version"] = value

    # =========================================================================

    @property
    def index(self) -> Optional[uint16]:
        """
        The 0-indexed location of the blueprintable in a parent
        :py:class:`BlueprintBook`. This member is automatically generated if
        omitted, but can be manually set with this attribute. ``index`` has no
        meaning when the blueprintable is not located inside another BlueprintBook.

        :getter: Gets the index of this blueprintable, or ``None`` if not set.
            A blueprintable's index is only generated when exporting with
            :py:meth:`.Blueprintable.to_dict`, so ``index`` will still be ``None``
            until specified otherwise.
        :setter: Sets the index of the :py:class:`.Blueprintable`, or removes it
            if set to ``None``.
        """
        return self._root.get("index", None)

    @index.setter
    def index(self, value: Optional[uint16]):
        if self.validate_assignment:
            result = attempt_and_reissue(self, self.Format, self._root, "index", value)
            self._root["index"] = result
        else:
            self._root["index"] = value

    # =========================================================================
    # Utility functions
    # =========================================================================

    # TODO
    # def formatted_label(self) -> str:
    #     """
    #     Returns a formatted string for the console that can be displayed with
    #     the python module ``rich``.
    #     """
    #     if not self.label:
    #         return self.label

    #     formatted_result = self.label
    #     formatted_result = formatted_result.replace("[font=default-bold]", "[bold]")
    #     formatted_result = formatted_result.replace("[/font]", "[/bold]")

    #     formatted_result = re.sub(
    #         r"\[color=(^\]+)\](.*?)\[\/color\]", r"[\1]\2[/\1]", formatted_result
    #     )
    #     # formatted_result = re.sub(r"\[color=(\d+,\d+,\d+)\](.*?)\[\/color\]", r"\[/\]", formatted_result)
    #     # re.sub("\\[[^\\]]+=([^\\]]+)\\]", "\\\\[\\1\\]", formatted_result)

    #     return formatted_result

    def version_tuple(self) -> tuple[uint16, uint16, uint16, uint16]:
        """
        Returns the version of the :py:class:`.Blueprintable` as a 4-length
        tuple.

        :returns: A 4 length tuple in the format ``(major, minor, patch, dev_ver)``.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import Blueprint
            >>> blueprint = Blueprint({"version": 281474976710656})
            >>> blueprint.version_tuple()
            (1, 0, 0, 0)
        """
        return decode_version(self._root[self._root_item]["version"])

    def version_string(self) -> str:
        """
        Returns the version of the :py:class:`.Blueprintable` in human-readable
        string.

        :returns: a ``str`` of 4 version numbers joined by a '.' character.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import Blueprint
            >>> blueprint = Blueprint({"version": (1, 2, 3)})
            >>> blueprint.version_string()
            '1.2.3.0'
        """
        return version_tuple_to_string(self.version_tuple())

    # =========================================================================

    def validate(
        self, mode: ValidationMode = ValidationMode.STRICT, force: bool = False
    ) -> ValidationResult:
        mode = ValidationMode(mode)

        output = ValidationResult([], [])

        if mode is ValidationMode.NONE and not force:  # (self.is_valid and not force):
            return output

        context = {
            "mode": mode,
            "object": self,
            "warning_list": [],
            "assignment": False,
            "environment_version": __factorio_version_info__,
        }

        try:
            self.Format.model_validate(self._root, strict=True, context=context)
        except ValidationError as e:
            output.error_list.append(DataFormatError(e))

        output.warning_list += context["warning_list"]

        # if len(output.error_list) == 0:
        #     # Set the `is_valid` attribute
        #     # This means that if mode="pedantic", an entity that issues only
        #     # warnings will still not be considered valid
        #     super().validate()

        return output

    # def to_dict(self) -> dict:
    #     out_dict = self.__class__.Format.model_construct(  # Performs no validation(!)
    #         **{self._root_item: self._root}
    #     ).model_dump(
    #         by_alias=True,  # Some attributes are reserved words (type, from,
    #         # etc.); this resolves that issue
    #         exclude_none=True,  # Trim if values are None
    #         exclude_defaults=True,  # Trim if values are defaults
    #         warnings=False  # Ignore warnings because `model_construct` cannot
    #         # be made recursive for some asinine reason
    #     )

    #     return out_dict

    def to_string(self) -> str:  # pragma: no coverage
        """
        Returns this object as an encoded Factorio blueprint string.

        :returns: The zlib-compressed, base-64 encoded string.

        :example:

        .. doctest::

            >>> from draftsman.blueprintable import (
            ...     Blueprint, DeconstructionPlanner, UpgradePlanner, BlueprintBook
            ... )
            >>> Blueprint({"version": (1, 0)}).to_string()
            '0eNqrVkrKKU0tKMrMK1GyqlbKLEnNVbJCEtNRKkstKs7Mz1OyMrIwNDE3sTQ3Mzc0MDM1q60FAHmVE1M='
            >>> DeconstructionPlanner({"version": (1, 0)}).to_string()
            '0eNpdy0EKgCAQAMC/7Nkgw7T8TIQtIdga7tol/HtdunQdmBs2DJlYSg0SMy1nWomwgL+BUSTSzuCppqQgCh7gf6H7goILC78Cfpi0cWZ21unejra1B7C2I9M='
            >>> UpgradePlanner({"version": (1, 0)}).to_string()
            '0eNo1yksKgCAUBdC93LFBhmm5mRB6iGAv8dNE3Hsjz/h0tOSzu+lK0TFThu0oVGtgX2C5xSgQKj2wcy5zCnyUS3gZdjukMuo02shV73qMH4ZxHbs='
            >>> BlueprintBook({"version": (1, 0)}).to_string()
            '0eNqrVkrKKU0tKMrMK4lPys/PVrKqVsosSc1VskJI6IIldJQSk0syy1LjM/NSUiuUrAx0lMpSi4oz8/OUrIwsDE3MTSzNzcwNDcxMzWprAVWGHQI='
        """
        # TODO: add options to compress/canonicalize blueprints before export
        # (though should that happen on a per-blueprintable basis? And what about non-Blueprint strings, like upgrade planners?)
        return JSON_to_string(self.to_dict())

    def __str__(self) -> str:  # pragma: no coverage
        return "<{}>{}".format(
            type(self).__name__,
            json.dumps(self.to_dict()[self._root_item], indent=2),
        )

    def __repr__(self) -> str:  # pragma: no coverage
        return "<{}>{}".format(
            type(self).__name__, repr(self.to_dict()[self._root_item])
        )
