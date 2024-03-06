from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Literal, Tuple

from dahlia import dprint

from oddsprout.constants import (
    BASE_TYPES,
    BOUNDS_KEYS,
    CATEGORIES,
    CHARSETS,
    DEFAULT_TYPES,
    TYPES_KEYS,
    VALID_TYPES,
)
from oddsprout.exceptions import OddsproutConfigurationError, OddsproutValueError
from oddsprout.utils import matches_type

if TYPE_CHECKING:
    from os import PathLike

if sys.version_info < (3, 11):  # pragma: no cover
    import tomli as toml
else:  # pragma: no cover
    import tomllib as toml


@dataclass(frozen=True)
class Config:
    """An Oddsprout configuration type."""

    types: list[str] = field(default_factory=lambda: sorted(DEFAULT_TYPES))
    base_size: tuple[int, int] = (0, 100)
    string_size: tuple[int, int] = (0, 50)
    collection_size: tuple[int, int] = (0, 100)
    charset: Literal["ascii", "alpha", "alnum", "digits"] = "ascii"
    base: Literal["any", "array", "object"] = "any"

    def __post_init__(self) -> None:
        if not self.types:
            msg = "'types' can't be empty"
            raise OddsproutValueError(msg)


def _check_unexpected_items(items: set[str], err_msg_nouns: tuple[str, str]) -> None:
    if not items:
        return
    singular, plural = err_msg_nouns
    if len(items) == 1:
        msg = f"invalid {singular} {items.pop()!r}"
    else:
        msg = f"invalid {plural} {', '.join(map(repr, sorted(items)))}"
    raise OddsproutConfigurationError(msg)


def _check_bounds_config(config: dict[str, Any]) -> None:
    _check_unexpected_items(config.keys() - BOUNDS_KEYS, ("key", "keys"))
    for key, value in config.items():
        if key.endswith("-max"):
            if not isinstance(value, int):
                msg = f"expected an integer for {key!r}"
                raise OddsproutConfigurationError(msg)
            # NOTE: Disabling coverage for 'continue' since CPython's peephole optimizer
            # never executes it. See: https://github.com/nedbat/coveragepy/issues/198
            continue  # pragma: no cover
        if f"{key}-max" in config:
            msg = f"can't use {key!r} and '{key}-max' at once"
            raise OddsproutConfigurationError(msg)
        if not (
            isinstance(value, list) and matches_type(tuple(value), Tuple[int, int])
        ):
            msg = f"expected a [min, max] array for {key!r}"
            raise OddsproutConfigurationError(msg)
    # TODO(trag1c): check what collection sizes could be too large and drop a warning


def _check_types_config(config: dict[str, Any]) -> None:
    _check_unexpected_items(config.keys() - TYPES_KEYS, ("key", "keys"))

    if not isinstance(charset := config.get("charset", "ascii"), str):
        msg = (
            "expected a string for 'charset' "
            f"(one of {', '.join(map(repr, CHARSETS))})"
        )
        raise OddsproutConfigurationError(msg)
    if charset not in CHARSETS:
        msg = (
            f"invalid charset {charset!r} "
            "(valid options: 'ascii', 'alpha', 'alnum', 'digits')"
        )
        raise OddsproutConfigurationError(msg)

    if (base := config.get("base", "any")) not in BASE_TYPES:
        msg = f"invalid base type {base!r} (valid options: 'any', 'array', 'object')"
        raise OddsproutConfigurationError(msg)

    for key in ("exclude", "include"):
        if (value := config.get(key)) is None:
            continue
        if not matches_type(value, List[str]):
            msg = f"expected an array of type names for {key!r}"
            raise OddsproutConfigurationError(msg)
        for item in set(value):
            if item not in VALID_TYPES:
                msg = f"invalid type {item!r} in {key!r}"
                raise OddsproutConfigurationError(msg)
            if value.count(item) > 1:
                dprint(
                    f"&eWARNING:&r duplicated type {item!r} in {key!r}", file=sys.stderr
                )

    if set(config) >= {"include", "exclude"}:
        msg = "can't use 'include' and 'exclude' at once"
        raise OddsproutConfigurationError(msg)


def _transform_config(config: dict[str, dict[str, Any]]) -> Config:
    transformed = {}
    for key, value in config.get("bounds", {}).items():
        new_key = (key[:-4] if key.endswith("-max") else key) + "_size"
        transformed[new_key] = (0, value) if key.endswith("-max") else tuple(value)
    types_config = config.get("types", {})
    if included_types := types_config.pop("include", []):
        transformed["types"] = sorted(included_types)
    if excluded_types := types_config.pop("exclude", []):
        # assuming "include" is not defined based on prior checks
        transformed["types"] = sorted(set(VALID_TYPES) - set(excluded_types))
    transformed.update(types_config)
    return Config(**transformed)


def load_config(path: PathLike[str] | str) -> Config:
    """Load and validate the configuration file."""
    try:
        config = toml.loads(Path(path).read_text())
    except toml.TOMLDecodeError as e:
        # NOTE: Redirecting this to an oddsprout exception so that the user
        # does not have to deal with picking the correct library to import
        msg = f"TOMLDecodeError: {e}"
        raise OddsproutConfigurationError(msg) from None

    found_categories = set(config)
    _check_unexpected_items(found_categories - CATEGORIES, ("category", "categories"))
    if "bounds" in found_categories:
        _check_bounds_config(config["bounds"])
    if "types" in found_categories:
        _check_types_config(config["types"])
    return _transform_config(config)
