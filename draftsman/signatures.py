# signatures.py

"""
Module of data formats, implemented as pydantic ``BaseModel`` instances. Used 
to validate and normalize data. Each one raises a ``ValidationError`` if the 
passed in data does not  match the data format specified, which is usually 
wrapped with ``DraftsmanError`` of some kind.
"""


from draftsman.classes.association import Association
from draftsman.classes.vector import Vector
from draftsman.constants import ValidationMode
from draftsman.data.signals import (
    signal_dict,
    mapper_dict,
    get_signal_type,
    pure_virtual,
)
from draftsman.data import items, signals
from draftsman.error import InvalidMapperError, InvalidSignalError
from draftsman.warning import (
    BarWarning,
    MalformedSignalWarning,
    PureVirtualDisallowedWarning,
    UnknownKeywordWarning,
    UnknownSignalWarning,
)

from typing_extensions import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    PrivateAttr,
    RootModel,
    ValidationInfo,
    field_validator,
    model_validator,
    model_serializer,
)
from pydantic.functional_validators import AfterValidator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from textwrap import dedent
from thefuzz import process
from typing import Any, ClassVar, Literal, Optional, Sequence
from functools import lru_cache
import sys
import types
import typing

try:
    from typing import get_args, get_origin  # type: ignore
except ImportError:
    from typing_extensions import get_args, get_origin


if sys.version_info >= (3, 10):

    def _is_union(origin):
        return origin is typing.Union or origin is types.UnionType

else:

    def _is_union(origin):
        return origin is typing.Union


def recursive_construct(model_class: BaseModel, **input_data) -> BaseModel:
    def handle_annotation(annotation: type, value: Any):
        # print(annotation, value)
        try:
            if issubclass(annotation, BaseModel):
                # print("yes!")
                return recursive_construct(annotation, **value)
        except Exception as e:
            # print(type(e).__name__, e)
            # print("issue with BaseModel".format(annotation))
            pass
        try:
            if issubclass(annotation, RootModel):
                # print("rootyes!")
                return recursive_construct(annotation, root=value)
        except Exception as e:
            # print(type(e).__name__, e)
            # print("issue with RootModel")
            pass

        origin = get_origin(annotation)
        # print(origin)

        if origin is None:
            return value
        elif _is_union(origin):
            # print("optional")
            args = get_args(annotation)
            for arg in args:
                # print("\t", arg)
                result = handle_annotation(arg, value)
                # print("union result: {}".format(result))
                if result != value:
                    # print("early exit")
                    return result
            # Otherwise
            # print("otherwise")
            return value
        elif origin is typing.Literal:
            # print("literal")
            return value
        elif isinstance(origin, (str, bytes)):
            # print("string")
            return value
        elif issubclass(origin, typing.Tuple):
            # print("tuple")
            args = get_args(annotation)
            if isinstance(args[-1], type(Ellipsis)):
                # format: tuple[T, ...]
                member_type = args[0]
                return tuple(handle_annotation(member_type, v) for v in value)
            else:
                # format: tuple[A, B, C]
                return tuple(
                    handle_annotation(member_type, value[i])
                    for i, member_type in enumerate(args)
                )
        elif issubclass(origin, typing.Sequence):
            # print("list")
            member_type = get_args(annotation)[0]
            # print(member_type)
            # print(value)
            result = [handle_annotation(member_type, v) for v in value]
            # print("result: {}".format(result))
            return result
        else:
            return value

    m = model_class.__new__(model_class)
    fields_values: dict[str, typing.Any] = {}
    defaults: dict[str, typing.Any] = {}
    for name, field in model_class.model_fields.items():
        # print("\t", name, field.annotation)
        if field.alias and field.alias in input_data:
            fields_values[name] = handle_annotation(
                field.annotation, input_data.pop(field.alias)
            )
        elif name in input_data:
            result = handle_annotation(field.annotation, input_data.pop(name))
            # print("outer_result: {}".format(result))
            fields_values[name] = result
        elif not field.is_required():
            # print("\tdefault")
            defaults[name] = field.get_default(call_default_factory=True)
    _fields_set = set(fields_values.keys())
    fields_values.update(defaults)

    # print(fields_values)

    _extra: dict[str, typing.Any] | None = None
    if model_class.model_config.get("extra") == "allow":
        _extra = {}
        for k, v in input_data.items():
            _extra[k] = v
    else:
        fields_values.update(input_data)
    object.__setattr__(m, "__dict__", fields_values)
    object.__setattr__(m, "__pydantic_fields_set__", _fields_set)
    if not model_class.__pydantic_root_model__:
        object.__setattr__(m, "__pydantic_extra__", _extra)

    if model_class.__pydantic_post_init__:
        m.model_post_init(None)
    elif not model_class.__pydantic_root_model__:
        # Note: if there are any private attributes, cls.__pydantic_post_init__ would exist
        # Since it doesn't, that means that `__pydantic_private__` should be set to None
        object.__setattr__(m, "__pydantic_private__", None)

    return m


def get_suggestion(name, choices, n=3, cutoff=60):
    suggestions = [
        suggestion[0]
        for suggestion in process.extract(name, choices, limit=n)
        if suggestion[1] >= cutoff
    ]
    if len(suggestions) == 0:
        return ""
    elif len(suggestions) == 1:
        return "; did you mean '{}'?".format(suggestions[0])
    else:
        return "; did you mean one of {}?".format(suggestions)
        # return "; did you mean one of {}?".format(", ".join(["or " + str(item) if i == len(suggestions) - 1 else str(item) for i, item in enumerate(suggestions)]))


int32 = Annotated[int, Field(..., ge=-(2**31), lt=2**31)]
# TODO: description about floating point issues
int64 = Annotated[int, Field(..., ge=-(2**63), lt=2**63)]

uint8 = Annotated[int, Field(..., ge=0, lt=2**8)]
uint16 = Annotated[int, Field(..., ge=0, lt=2**16)]
uint32 = Annotated[int, Field(..., ge=0, lt=2**32)]
# TODO: description about floating point issues
uint64 = Annotated[int, Field(..., ge=0, lt=2**64)]


def known_item(v: str) -> str:
    if v not in items.raw:
        raise ValueError(v)
    return v
ItemName = Annotated[str, AfterValidator(known_item)]


class DraftsmanBaseModel(BaseModel):
    """
    TODO
    """

    @classmethod
    # @lru_cache(maxsize=None)  # maybe excessive...
    # def get_model_aliases(cls) -> list[str]:
    #     """
    #     Similar to ``cls.model_fields``, but converts everything to their
    #     aliases if present.
    #     """
    #     return [
    #         v.alias if v.alias is not None else k for k, v in cls.model_fields.items()
    #     ]
    def true_model_fields(cls):
        return {
            (v.alias if v.alias is not None else k): k for k, v in cls.model_fields.items()
        }

    @model_validator(mode="after")
    def warn_unused_arguments(self, info: ValidationInfo):
        """
        Populates the warning list when an input BaseModel is given a field it
        does not recognize. Because Factorio (seems to) permit extra keys, doing
        so will issue warnings instead of exceptions.
        """
        if not info.context:
            return self
        if info.context["mode"] is ValidationMode.MINIMUM:
            return self

        # We only want to issue this particular warning if we're setting an
        # assignment of a subfield, or if we're doing a full scale `validate()`
        # function call
        obj = info.context["object"]
        if type(obj).Format is type(self) and info.context["assignment"]:
            return self

        if self.model_extra:
            warning_list: list = info.context["warning_list"]

            issue = UnknownKeywordWarning(
                "'{}' object has no attribute(s) {}; allowed fields are {}".format(
                    self.model_config.get("title", type(self).__name__),
                    list(self.model_extra.keys()),
                    self.true_model_fields(),
                )
            )

            if info.context["mode"] is ValidationMode.PEDANTIC:
                raise ValueError(issue) from None
            else:
                warning_list.append(issue)

        return self

    # Permit accessing via indexing
    def __getitem__(self, key):
        return getattr(self, self.true_model_fields().get(key, key))

    def __setitem__(self, key, value):
        setattr(self, self.true_model_fields().get(key, key), value)

    def __contains__(self, key: str) -> bool:
        return self.true_model_fields().get(key, key) in self.__dict__

    # Add a number of dict-like functions:
    def get(self, key, default):
        return self.__dict__.get(self.true_model_fields().get(key, key), default)

    # Strip indentation and newlines from description strings when generating
    # JSON schemas
    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)

        def normalize_description(input_obj: str) -> str:
            if "description" in input_obj:
                input_obj["description"] = dedent(input_obj["description"]).strip()

        normalize_description(json_schema)
        if "properties" in json_schema:
            for property_spec in json_schema["properties"].values():
                normalize_description(property_spec)
        if "items" in json_schema:
            normalize_description(json_schema["items"])

        return json_schema
    
    # def __repr__(self): # TODO
    #     return "{}{{{}}}".format(__class__.__name__, super().__repr__())

    # Factorio seems to be permissive when it comes to extra keys, so we allow
    # them and issue warnings if desired
    model_config = ConfigDict(
        extra="allow",
        revalidate_instances="always",
        populate_by_name=True,  # Allow to pass either internal or alias to constructor
    )


class DraftsmanRootModel(RootModel):
    """
    TODO
    """

    # Permit accessing via indexing
    def __getitem__(self, key):
        getattr(self.root, key)

    def __setitem__(self, key, value):
        setattr(self.root, key, value)

    model_config = ConfigDict(revalidate_instances="always")


# ACCUMULATOR_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             Optional("output_signal"): SIGNAL_ID,
#         },
#     )
# )

# ARITHMETIC_COMBINATOR_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             Optional("arithmetic_conditions"): {
#                 Optional("first_constant"): int,
#                 Optional("first_signal"): SIGNAL_ID,
#                 Optional("operation"): OPERATION,
#                 Optional("second_constant"): int,
#                 Optional("second_signal"): SIGNAL_ID,
#                 Optional("output_signal"): SIGNAL_ID,
#             },
#         },
#     )
# )

# CONSTANT_COMBINATOR_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {Optional("filters"): SIGNAL_FILTERS, Optional("is_on"): bool},
#     )
# )

# DECIDER_COMBINATOR_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             Optional("decider_conditions"): {
#                 Optional("constant"): int,
#                 Optional("first_constant"): int,
#                 Optional("first_signal"): SIGNAL_ID,
#                 Optional("comparator"): COMPARATOR,
#                 Optional("second_constant"): int,
#                 Optional("second_signal"): SIGNAL_ID,
#                 Optional("output_signal"): SIGNAL_ID,
#                 Optional("copy_count_from_input"): bool,
#             },
#         },
#     )
# )

# FILTER_INSERTER_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#             # Inserter
#             Optional("circuit_read_hand_contents"): bool,
#             Optional("circuit_hand_read_mode"): int,
#             Optional("circuit_mode_of_operation"): int,
#             Optional("circuit_set_stack_size"): bool,
#             Optional("stack_control_input_signal"): SIGNAL_ID,
#         },
#     )
# )

# INSERTER_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#             # Inserter
#             Optional("circuit_read_hand_contents"): bool,
#             Optional("circuit_hand_read_mode"): int,
#             Optional("circuit_mode_of_operation"): int,
#             Optional("circuit_set_stack_size"): bool,
#             Optional("stack_control_input_signal"): SIGNAL_ID,
#         },
#     )
# )

# LAMP_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             Optional("circuit_condition"): CONDITION,
#             Optional("logistic_condition"): CONDITION,
#             Optional("use_colors"): bool,
#         },
#     )
# )

# LOGISTIC_BUFFER_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_mode_of_operation"): LOGISTIC_MODE_OF_OPERATION,
#         },
#     )
# )

# LOGISTIC_REQUESTER_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_mode_of_operation"): LOGISTIC_MODE_OF_OPERATION,
#         },
#     )
# )

# MINING_DRILL_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#             # Mining Drills
#             Optional("circuit_read_resources"): bool,
#         },
#     )
# )

# OFFSHORE_PUMP_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#         },
#     )
# )

# POWER_SWITCH_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#         },
#     )
# )

# PROGRAMMABLE_SPEAKER_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Programmable Speaker
#             Optional("circuit_parameters"): {
#                 Optional("signal_value_is_pitch"): bool,
#                 Optional("instrument_id"): int,
#                 Optional("note_id"): int,
#             },
#         },
#     )
# )

# PUMP_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#         },
#     )
# )

# RAIL_SIGNAL_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_close_signal"): bool,
#             Optional("circuit_read_signal"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Rail Signal
#             Optional("red_output_signal"): SIGNAL_ID,
#             Optional("orange_output_signal"): SIGNAL_ID,
#             Optional("green_output_signal"): SIGNAL_ID,
#         },
#     )
# )

# RAIL_CHAIN_SIGNAL_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             Optional("red_output_signal"): SIGNAL_ID,
#             Optional("orange_output_signal"): SIGNAL_ID,
#             Optional("green_output_signal"): SIGNAL_ID,
#             Optional("blue_output_signal"): SIGNAL_ID,
#         },
#     )
# )

# ROBOPORT_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Roboport
#             Optional("read_logistics"): bool,
#             Optional("read_robot_stats"): bool,
#             Optional("available_logistic_output_signal"): SIGNAL_ID,
#             Optional("total_logistic_output_signal"): SIGNAL_ID,
#             Optional("available_construction_output_signal"): SIGNAL_ID,
#             Optional("total_construction_output_signal"): SIGNAL_ID,
#         },
#     )
# )

# TRAIN_STOP_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#             # Train Stop
#             Optional("read_from_train"): bool,
#             Optional("read_stopped_train"): bool,
#             Optional("train_stopped_signal"): SIGNAL_ID,
#             Optional("set_trains_limit"): bool,
#             Optional("trains_limit_signal"): SIGNAL_ID,
#             Optional("read_trains_count"): bool,
#             Optional("trains_count_signal"): SIGNAL_ID,
#             Optional("send_to_train"): bool,
#         },
#     )
# )

# TRANSPORT_BELT_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Logistic condition
#             Optional("connect_to_logistic_network"): bool,
#             Optional("logistic_condition"): CONDITION,
#             # Transport Belts
#             Optional("circuit_read_hand_contents"): bool,
#             Optional("circuit_contents_read_mode"): int,
#         },
#     )
# )

# WALL_CONTROL_BEHAVIOR = Schema(
#     And(
#         Use(lambda x: {} if x is None else x),  # Convert to empty dict if None
#         {
#             # Circuit condition
#             Optional("circuit_enable_disable"): bool,
#             Optional("circuit_condition"): CONDITION,
#             # Wall
#             Optional("circuit_open_gate"): bool,
#             Optional("circuit_read_sensor"): bool,
#             Optional("output_signal"): SIGNAL_ID,
#         },
#     )
# )

# TODO: move this
# class MapperType(str, Enum):
#     entity = "entity"
#     item = "item"


class MapperID(DraftsmanBaseModel):
    name: str  # TODO: optional?
    type: Literal["entity", "item"] = Field(
        ...,
        description="""
        The type of mapping taking place; can be one of 'entity' for entity
        replacement or 'item' for item (typically module) replacement.
        """,
    )  # TODO: optional?

    @model_validator(mode="before")
    @classmethod
    def init_from_string(cls, value: Any):
        """
        Attempt to convert an input string name into a dict representation.
        Raises a ValueError if unable to determine the type of a signal's name,
        likely if the signal is misspelled or used in a modded configuration
        that differs from Draftsman's current one.
        """
        if isinstance(value, str):
            try:
                return mapper_dict(value)
            except InvalidMapperError as e:
                raise ValueError(
                    "Unknown mapping target {}; either specify the full dictionary, or update your environment".format(
                        e
                    )
                ) from None
        else:
            return value


class Mapper(DraftsmanBaseModel):
    # _alias_map: ClassVar[dict] = PrivateAttr(
    #     {"from": "from_", "to": "to", "index": "index"}
    # )

    from_: Optional[MapperID] = Field(
        None,
        alias="from",
        description="""
        Entity/Item to replace with 'to'. Remains blank in the GUI if omitted.
        """,
    )
    to: Optional[MapperID] = Field(
        None,
        description="""
        Entity/item to replace 'from'. Remains blank in the GUI if omitted.
        """,
    )
    index: uint64 = Field(
        ...,
        description="""
        Numeric index of the mapping in the UpgradePlanner's GUI, 0-based. 
        Value defaults to the index of this mapping in the parent 'mappers' list,
        but this behavior is not strictly enforced.
        """,
    )

    # Add the dict-like `get` function
    # def get(self, key, default):
    #     return super().get(self._alias_map[key], default)

    # def __getitem__(self, key):
    #     return super().__getitem__(self._alias_map[key])

    # def __setitem__(self, key, value):
    #     super().__setitem__(self._alias_map[key], value)


class Mappers(DraftsmanRootModel):
    root: list[Mapper]

    # @model_validator(mode="before")
    # @classmethod
    # def normalize_mappers(cls, value: Any):
    #     if isinstance(value, Sequence):
    #         for i, mapper in enumerate(value):
    #             if isinstance(value, (tuple, list)):
    #                 value[i] = {"index": i}
    #                 if mapper[0]:
    #                     value[i]["from"] = mapper_dict(mapper[0])
    #                 if mapper[1]:
    #                     value[i]["to"] = mapper_dict(mapper[1])

    # @validator("__root__", pre=True)
    # def normalize_mappers(cls, mappers):
    #     if mappers is None:
    #         return mappers
    #     for i, mapper in enumerate(mappers):
    #         if isinstance(mapper, (tuple, list)):
    #             mappers[i] = {"index": i}
    #             if mapper[0]:
    #                 mappers[i]["from"] = mapping_dict(mapper[0])
    #             if mapper[1]:
    #                 mappers[i]["to"] = mapping_dict(mapper[1])
    #     return mappers


class SignalID(DraftsmanBaseModel):
    name: Optional[str] = Field(
        ...,
        description="""
        Name of the signal. If omitted, the signal is treated as no signal and 
        removed on import/export cycle.
        """,
    )
    type: Literal["item", "fluid", "virtual"] = Field(
        ..., description="""Category of the signal."""
    )

    @model_validator(mode="before")
    @classmethod
    def init_from_string(cls, input):
        """
        Attempt to convert an input string name into a dict representation.
        Raises a ValueError if unable to determine the type of a signal's name,
        likely if the signal is misspelled or used in a modded configuration
        that differs from Draftsman's current one.
        """
        if isinstance(input, str):
            try:
                return signal_dict(input)
            except InvalidSignalError as e:
                raise ValueError(
                    "Unknown signal name {}; either specify the full dictionary, or update your environment".format(
                        e
                    )
                ) from None
        else:
            return input

    @field_validator("name")
    @classmethod
    def check_name_recognized(cls, value: str, info: ValidationInfo):
        """
        We might be provided with a signal which has all the information
        necessary to pass validation, but will be otherwise unrecognized by
        Draftsman (in it's current configuration at least). Issue a warning
        for every unknown signal.
        """
        # TODO: check a table to make sure we don't warn about the same unknown
        # signal multiple times
        if not info.context:
            return value
        if info.context["mode"] is ValidationMode.MINIMUM:
            return value

        warning_list: list = info.context["warning_list"]

        if value not in signals.raw:
            issue = UnknownSignalWarning(
                "Unknown signal '{}'{}".format(
                    value, get_suggestion(value, signals.raw.keys(), n=1)
                )
            )

            if info.context["mode"] is ValidationMode.PEDANTIC:
                raise ValueError(issue) from None
            else:
                warning_list.append(issue)

        return value

    @model_validator(mode="after")
    @classmethod
    def check_type_matches_name(cls, value: "SignalID", info: ValidationInfo):
        """
        Idiot-check to make sure that the ``type`` of a known signal actually
        corresponds to it's ``name``; prevents silly mistakes like::

            {"name": "signal-A", "type": "fluid"}
        """
        if not info.context:
            return value
        if info.context["mode"] is ValidationMode.MINIMUM:
            return value

        warning_list: list = info.context["warning_list"]

        if value["name"] in signals.raw:
            expected_type = get_signal_type(value["name"])
            if expected_type != value["type"]:
                issue = MalformedSignalWarning(
                    "Known signal '{}' was given a mismatching type (expected '{}', found '{}')".format(
                        value["name"], expected_type, value["type"]
                    )
                )

                if info.context["mode"] is ValidationMode.PEDANTIC:
                    raise AssertionError(issue) from None
                else:
                    warning_list.append(issue)

        return value

    # @model_serializer
    # def serialize_signal_id(self):
    #     """
    #     Try exporting the object as a dict if it was set as a string. Useful if
    #     someone sets a signal to it's name without running validation at any
    #     point, this method will convert it to it's correct output (provided it
    #     can determine it's type).
    #     """
    #     if isinstance(self, str):
    #         try:
    #             return signal_dict(self)
    #         except InvalidSignalError as e:
    #             raise ValueError(
    #                 "Unknown signal name {}; either specify the full dictionary, or update your environment to include it"
    #                 .format(e)
    #             ) from None
    #     else:
    #         return {"name": self["name"], "type": self["type"]}


class Icon(DraftsmanBaseModel):
    signal: SignalID = Field(..., description="""Which signal's icon to display.""")
    index: uint8 = Field(
        ..., description="""Numerical index of the icon, 1-based."""
    )  # TODO: is it numerical order which determines appearance, or order in parent list?


class Icons(DraftsmanRootModel):
    root: list[Icon] = Field(
        ...,
        max_length=4,
        description="""
        The list of all icons used by this object. Hard-capped to 4 entries 
        total; having more than 4 will raise an error in import.
        """,
    )

    @model_validator(mode="before")
    def normalize_icons(cls, value: Any):
        if isinstance(value, Sequence):
            result = [None] * len(value)
            for i, signal in enumerate(value):
                if isinstance(signal, str):
                    result[i] = {"index": i + 1, "signal": signal}
                else:
                    result[i] = signal
            return result
        else:
            return value


class Color(DraftsmanBaseModel):
    r: float = Field(..., ge=0, le=255)
    g: float = Field(..., ge=0, le=255)
    b: float = Field(..., ge=0, le=255)
    a: Optional[float] = Field(None, ge=0, le=255)

    @model_validator(mode="before")
    @classmethod
    def normalize_from_sequence(cls, value: Any):
        if isinstance(value, (list, tuple)):
            new_color = {}
            new_color["r"] = value[0]
            new_color["g"] = value[1]
            new_color["b"] = value[2]
            try:
                new_color["a"] = value[3]
            except IndexError:
                pass
            return new_color
        else:
            return value

    # @model_serializer
    # def normalize(self):  # FIXME: scuffed
    #     if isinstance(self, (list, tuple)):
    #         new_color = {}
    #         new_color["r"] = self[0]
    #         new_color["g"] = self[1]
    #         new_color["b"] = self[2]
    #         try:
    #             new_color["a"] = self[3]
    #         except IndexError:
    #             pass
    #         return new_color
    #     elif isinstance(self, dict):
    #         return {k: v for k, v in self.items() if v is not None}
    #     else:
    #         return {k: v for k, v in self.__dict__.items() if v is not None}


class FloatPosition(DraftsmanBaseModel):
    x: float
    y: float

    @model_validator(mode="before")
    @classmethod
    def model_validator(cls, data):
        # likely a Vector or Primitive vector
        try:
            data = Vector.from_other(data, float)
            return data.to_dict()
        except TypeError:
            return data


class IntPosition(DraftsmanBaseModel):
    x: int
    y: int

    @model_validator(mode="before")
    @classmethod
    def model_validator(cls, data):
        # likely a Vector or Primitive vector
        try:
            data = Vector.from_other(data, int)
            return data.to_dict()
        except TypeError:
            return data


# factorio_comparator_choices = {">", "<", "=", "≥", "≤", "≠"}
# python_comparator_choices = {"==", "<=", ">=", "!="}
# class Comparator(DraftsmanRootModel):
#     root: Literal[">", "<", "=", "≥", "≤", "≠"]

#     @model_validator(mode="before")
#     @classmethod
#     def normalize(cls, input: str):
#         conversions = {"==": "=", ">=": "≥", "<=": "≤", "!=": "≠"}
#         if input in conversions:
#             return conversions[input]
#         else:
#             return input

# @model_serializer
# def normalize(self):
#     conversions = {
#         "==": "=",
#         ">=": "≥",
#         "<=": "≤",
#         "!=": "≠"
#     }
#     if self.root in conversions:
#         return conversions[self.root]
#     else:
#         return self.root


class Condition(DraftsmanBaseModel):
    first_signal: Optional[SignalID] = Field(
        None,
        description="""
        The first signal to specify for this condition. A null value results
        in an empty slot.
        """,
    )
    comparator: Optional[Literal[">", "<", "=", "≥", "≤", "≠"]] = Field(
        "<",
        description="""
        The comparison operation to perform, where 'first_signal' is on the left
        and 'second_signal' or 'constant' is on the right.
        """,
    )
    constant: Optional[int32] = Field(
        0,
        description="""
        A constant value to compare against. Can only be set in the
        rightmost condition slot. The rightmost slot will be empty if neither
        'constant' nor 'second_signal' are set.
        """,
    )
    second_signal: Optional[SignalID] = Field(
        None,
        description="""
        The second signal of the condition, if applicable. Takes 
        precedence over 'constant', if both are set at the same time.
        """,
    )

    @model_validator(mode="before")
    @classmethod
    def convert_sequence_to_condition(cls, value: Any):
        if isinstance(value, Sequence):
            result = {
                "first_signal": value[0],
                "comparator": value[1],
            }
            if isinstance(value[2], int):
                result["constant"] = value[2]
            else:
                result["second_signal"] = value[2]
            return result
        else:
            return value

    @field_validator("comparator", mode="before")
    @classmethod
    def normalize_comparator_python_equivalents(cls, input: Any):
        conversions = {"==": "=", ">=": "≥", "<=": "≤", "!=": "≠"}
        if input in conversions:
            return conversions[input]
        else:
            return input


class WaitCondition(DraftsmanBaseModel):
    type: str
    compare_type: str
    ticks: Optional[int] = None  # TODO dimension
    condition: Optional[Condition] = None  # TODO: correct annotation


class Stop(DraftsmanBaseModel):
    station: str
    wait_conditions: list[WaitCondition]  # TODO: optional?


class EntityFilter(DraftsmanBaseModel):
    name: str = Field(
        ...,
        description="""
        The name of a valid deconstructable entity.
        """
    )
    index: Optional[uint64] = Field(
        description="""
        Position of the filter in the DeconstructionPlanner, 0-based. Seems to 
        behave more like a sorting key rather than a numeric index; if omitted, 
        entities will be sorted by their Factorio order when imported instead
        of specific slots in the GUI, contrary to what index would seem to imply.
        """
    )


class TileFilter(DraftsmanBaseModel):
    name: str = Field(
        ...,
        description="""
        The name of a valid deconstructable tile.
        """
    )
    index: Optional[uint64] = Field(
        description="""
        Position of the filter in the DeconstructionPlanner, 0-based. Seems to 
        behave more like a sorting key rather than a numeric index; if omitted, 
        entities will be sorted by their Factorio order when imported instead
        of specific slots in the GUI, contrary to what index would seem to imply.
        """
    )


class CircuitConnectionPoint(DraftsmanBaseModel):
    entity_id: uint64
    circuit_id: Optional[Literal[1, 2]] = None


class WireConnectionPoint(DraftsmanBaseModel):
    entity_id: uint64
    wire_id: Optional[Literal[0, 1]] = None


class Connections(DraftsmanBaseModel):
    # _alias_map: ClassVar[dict] = PrivateAttr(
    #     {
    #         "1": "Wr1",
    #         "2": "Wr2",
    #         "Cu0": "Cu0",
    #         "Cu1": "Cu1",
    #     }
    # )

    def export_key_values(self):
        return {k: getattr(self, v) for k, v in self.true_model_fields().items()}

    class CircuitConnections(DraftsmanBaseModel):
        red: Optional[list[CircuitConnectionPoint]] = None
        green: Optional[list[CircuitConnectionPoint]] = None

    Wr1: Optional[CircuitConnections] = Field(CircuitConnections(), alias="1")
    Wr2: Optional[CircuitConnections] = Field(CircuitConnections(), alias="2")
    Cu0: Optional[list[WireConnectionPoint]] = None
    Cu1: Optional[list[WireConnectionPoint]] = None

    # def __getitem__(self, key):
    #     return super().__getitem__(self._alias_map[key])

    # def __setitem__(self, key, value):
    #     super().__setitem__(self._alias_map[key], value)

    # def __contains__(self, item):
    #     return item in self._alias_map and


class Filters(DraftsmanRootModel):
    class FilterEntry(DraftsmanBaseModel):
        index: int64 = Field(
            ..., description="""Numeric index of a filter entry, 1-based."""
        )
        name: str = Field(  # TODO: ItemID
            ..., description="""Name of the item to filter."""
        )

        @field_validator("index")
        @classmethod
        def ensure_within_filter_count(cls, value: int, info: ValidationInfo):
            if not info.context:
                return value

            entity = info.context["object"]
            if entity.filter_count is not None and value >= entity.filter_count:
                raise ValueError(
                    "'{}' exceeds the allowable range for filter slot indices [0, {}) for this entity ('{}')".format(
                        value, entity.filter_count, entity.name
                    )
                )

            return value

    root: list[FilterEntry]

    @model_validator(mode="before")
    @classmethod
    def normalize_validate(cls, value: Any):
        result = []
        if isinstance(value, (list, tuple)):
            for i, entry in enumerate(value):
                if isinstance(entry, str):
                    result.append({"index": i + 1, "name": entry})
                else:
                    result.append(entry)
        return result

    # @model_serializer
    # def normalize_construct(self):
    #     result = []
    #     for i, entry in enumerate(self.root):
    #         if isinstance(entry, str):
    #             result.append({"index": i + 1, "name": entry})
    #         else:
    #             result.append(entry)
    #     return result


def ensure_bar_less_than_inventory_size(
    cls, value: Optional[uint16], info: ValidationInfo
):
    if not info.context or value is None:
        return value
    if info.context["mode"] == ValidationMode.MINIMUM:
        return value

    warning_list: list = info.context["warning_list"]
    entity = info.context["object"]
    if entity.inventory_size and value >= entity.inventory_size:
        issue = BarWarning(
            "Bar index ({}) exceeds the container's inventory size ({})".format(
                value, entity.inventory_size
            ),
        )

        if info.context["mode"] is ValidationMode.PEDANTIC:
            raise issue
        else:
            warning_list.append(issue)

    return value


# class Bar(RootModel):
#     root: uint16

#     @model_validator(mode="after")
#     @classmethod
#     def ensure_less_than_inventory_size(cls, bar: "Bar", info: ValidationInfo):
#         if not info.context or bar is None:
#             return bar
#         if info.context["mode"] == ValidationMode.MINIMUM:
#             return bar

#         warning_list: list = info.context["warning_list"]
#         entity = info.context["entity"]
#         if entity.inventory_size and bar.root >= entity.inventory_size:
#             issue = IndexWarning(  # TODO: change warning type
#                 "Bar index ({}) exceeds the container's inventory size ({})".format(
#                     bar, entity.inventory_size
#                 ),
#             )

#             if info.context["mode"] is ValidationMode.PEDANTIC:
#                 raise issue
#             else:
#                 warning_list.append(issue)

#         return bar


class InventoryFilters(DraftsmanBaseModel):
    filters: Optional[Filters] = Field(
        None,
        description="""
        Any reserved item filter slots in the container's inventory.
        """,
    )
    bar: Optional[uint16] = Field(
        None,
        description="""
        Limiting bar on this container's inventory.
        """,
    )

    @field_validator("bar")
    @classmethod
    def ensure_less_than_inventory_size(
        cls, bar: Optional[uint16], info: ValidationInfo
    ):
        return ensure_bar_less_than_inventory_size(cls, bar, info)


class RequestFilters(DraftsmanRootModel):
    class Request(DraftsmanBaseModel):
        index: int64 = Field(
            ..., description="""Numeric index of the logistics request, 1-based."""
        )
        name: str = Field(  # TODO: ItemName
            ..., description="""The name of the item to request from logistics."""
        )
        count: Optional[int64] = Field(
            1,
            description="""
            The amount of the item to request. Optional on import to Factorio, 
            but always included on export from Factorio. If omitted, will 
            default to a count of 1.
            """,
        )

    root: list[Request]

    @model_validator(mode="before")
    @classmethod
    def normalize_validate(cls, value: Any):
        if value is None:
            return value

        result = []
        if isinstance(value, list):
            for i, entry in enumerate(value):
                if isinstance(entry, (tuple, list)):
                    result.append({"index": i + 1, "name": entry[0], "count": entry[1]})
                else:
                    result.append(entry)
            return result
        else:
            return value

    # @model_serializer
    # def normalize_construct(self):
    #     result = []
    #     for i, entry in enumerate(self.root):
    #         if isinstance(entry, (tuple, list)):
    #             result.append({"index": i + 1, "name": entry[0], "count": entry[1]})
    #         else:
    #             result.append(entry)
    #     return result


class SignalFilter(DraftsmanBaseModel):
    index: int64 = Field(
        ...,
        description="""
        Numeric index of the signal in the combinator, 1-based. Typically the 
        index of the signal in the parent 'filters' key, but this is not 
        strictly enforced. Will result in an import error if this value exceeds 
        the maximum number of slots that this constant combinator can contain.
        """,
    )
    signal: Optional[SignalID] = Field(
        None,
        description="""
        Signal to broadcast. If this value is omitted the occupied slot will
        behave as if no signal exists within it. Cannot be a pure virtual
        (logic) signal like "signal-each", "signal-any", or 
        "signal-everything"; if such signals are set they will be removed
        on import.
        """,
    )
    count: int32 = Field(
        ...,
        description="""
        Value of the signal to emit.
        """,
    )

    @field_validator("index")
    @classmethod
    def ensure_index_within_range(cls, value: int64, info: ValidationInfo):
        """
        Factorio does not permit signal values outside the range of it's item
        slot count; this method raises an error IF item slot count is known.
        """
        if not info.context:
            return value

        entity = info.context["object"]

        # If Draftsman doesn't recognize entity, early exit
        if entity.item_slot_count is None:
            return value

        if not 0 <= value < entity.item_slot_count:
            raise ValueError(
                "Signal 'index' ({}) must be in the range [0, {})".format(
                    value, entity.item_slot_count
                )
            )

        return value

    @field_validator("signal")
    @classmethod
    def ensure_not_pure_virtual(cls, value: Optional[SignalID], info: ValidationInfo):
        """
        Warn if pure virtual signals (like "signal-each", "signal-any", and
        "signal-everything") are entered inside of a constant combinator.
        """
        if not info.context or value is None:
            return value
        if info.context["mode"] is ValidationMode.MINIMUM:
            return value

        warning_list: list = info.context["warning_list"]

        if value.name in pure_virtual:
            issue = PureVirtualDisallowedWarning(
                "Cannot set pure virtual signal '{}' in a constant combinator".format(
                    value.name
                )
            )

            if info.context["mode"] is ValidationMode.PEDANTIC:
                raise ValueError(issue) from None
            else:
                warning_list.append(issue)

        return value
