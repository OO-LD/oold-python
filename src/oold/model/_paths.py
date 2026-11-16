"""Resolve the embedded model behind a field, so queries can follow nested paths.

Duck-typed over pydantic v1 and v2 so neither has to be imported here. No imports
from ``oold``: the legacy bindings use this too, and a cycle would break them.
"""

import types
from functools import lru_cache
from typing import Any, Union, get_args, get_origin

_UNION_ORIGINS = {Union, types.UnionType}

_V1_SINGLETON_SHAPE = 1


def model_fields(model: type) -> dict[str, Any] | None:
    """The fields of a pydantic model class, or None if it is not one.

    v2 first: ``__fields__`` is deprecated there and warns when read.
    """
    fields = getattr(model, "__pydantic_fields__", None)
    if fields is None:
        fields = getattr(model, "__fields__", None)
    return fields if isinstance(fields, dict) else None


def _strip_optional(annotation: Any) -> Any:
    if get_origin(annotation) in _UNION_ORIGINS:
        arms = [arm for arm in get_args(annotation) if arm is not type(None)]
        return arms[0] if len(arms) == 1 else None
    return annotation


@lru_cache(maxsize=1024)
def _model_of(annotation: Any) -> type | None:
    """The model an annotation embeds as a single object. Bounded: models can be generated at runtime."""
    candidate = _strip_optional(annotation)
    # a parametrised alias (list[X], Link[X]) is not a class on every supported Python
    if isinstance(candidate, type) and get_origin(candidate) is None and model_fields(candidate) is not None:
        return candidate
    return None


def embedded_model(field: Any) -> type | None:
    """The model a field embeds as a single object, None for scalars, containers and links."""
    if field is None:
        return None
    if hasattr(field, "shape"):  # pydantic v1 ModelField
        candidate = field.type_ if field.shape == _V1_SINGLETON_SHAPE else None
        return candidate if isinstance(candidate, type) and model_fields(candidate) is not None else None
    annotation = getattr(field, "annotation", None)
    try:
        return _model_of(annotation)
    except TypeError:  # an unhashable annotation cannot be cached
        return _model_of.__wrapped__(annotation)


def is_model_container(field: Any) -> bool:
    """Whether a field holds a list, set or tuple of embedded models."""
    if field is None:
        return False
    if hasattr(field, "shape"):  # pydantic v1 ModelField
        item = field.type_
        return field.shape != _V1_SINGLETON_SHAPE and isinstance(item, type) and model_fields(item) is not None
    annotation = _strip_optional(getattr(field, "annotation", None))
    if get_origin(annotation) in (list, set, frozenset, tuple):
        return any(isinstance(arg, type) and model_fields(arg) is not None for arg in get_args(annotation))
    return False


def reject_nested_path(parent: type, name: str, item: str) -> None:
    """Raise if ``Parent.name.item`` is a nested path, which only the descriptor binding builds."""
    model = embedded_model((model_fields(parent) or {}).get(name))
    fields = model_fields(model) if model is not None else None
    if fields and item in fields:
        raise NotImplementedError(
            f"Nested field paths ({name}.{item}) need the descriptor binding, which is the default. "
            "OOLD_DESCRIPTOR_BINDING=0 selects the legacy binding."
        )
