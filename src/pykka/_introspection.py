from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from pykka import ActorProxy
    from pykka._types import AttrPath

logger = logging.getLogger("pykka")


class AttrInfo(NamedTuple):
    callable: bool
    traversable: bool


def introspect_attrs(
    *,
    root: Any,
    proxy: ActorProxy[Any],
) -> dict[AttrPath, AttrInfo]:
    """Introspects the actor's attributes."""
    result: dict[AttrPath, AttrInfo] = {}
    object_attrs = dict(object.__dict__)
    attr_infos = (
        AttrInfo(callable=False, traversable=False),
        AttrInfo(callable=True, traversable=False),
    )
    attr_groups_to_visit: list[tuple[AttrPath, list[str]]] = [((), dir(root))]

    while attr_groups_to_visit:
        next_attr_groups: list[tuple[AttrPath, list[str]]] = []
        for parent_path, attr_names in attr_groups_to_visit:
            for attr_name in attr_names:
                if attr_name.startswith("_"):
                    # Attribute names starting with _ are considered private and are
                    # not exposed via ActorProxy.
                    continue

                attr_path = (*parent_path, attr_name)
                parent = get_attr_directly(root, parent_path) if parent_path else root
                parent_attrs: dict[str, Any] = {}
                for cls in reversed(parent.__class__.mro()):
                    parent_attrs |= object_attrs if cls is object else cls.__dict__
                if hasattr(parent, "__dict__"):
                    parent_attrs |= parent.__dict__
                try:
                    attr = parent_attrs[attr_name]
                except KeyError:
                    msg = (
                        f"type object {parent.__class__.__name__!r} "
                        f"has no attribute {attr_name!r}"
                    )
                    raise AttributeError(msg) from None

                # Keep `proxy` first to use its `__eq__` method instead of `attr`'s
                # unknown implementation.
                if proxy == attr:
                    logger.warning(
                        f"{root} attribute {'.'.join(attr_path)!r} "
                        f"is a proxy to itself. "
                        f"Consider making it private "
                        f"by renaming it to {'_' + attr_path[-1]!r}."
                    )
                    continue

                is_callable = callable(attr)
                traversable = (
                    getattr(attr, "_pykka_traversable", False) is True
                    or getattr(attr, "pykka_traversable", False) is True
                )
                attr_info = (
                    AttrInfo(callable=is_callable, traversable=True)
                    if traversable
                    else attr_infos[is_callable]
                )
                result[attr_path] = attr_info

                if attr_info.traversable:
                    next_attr_groups.append((attr_path, dir(attr)))
        attr_groups_to_visit = next_attr_groups

    return result


def get_attr_from_parent(
    root: Any,
    attr_path: AttrPath,
) -> Any:
    """Get attribute information from `__dict__` on the parent."""
    parent = get_attr_directly(root, attr_path[:-1])
    parent_attrs = get_obj_dict(parent)
    attr_name = attr_path[-1]

    try:
        return parent_attrs[attr_name]
    except KeyError:
        msg = (
            f"type object {parent.__class__.__name__!r} has no attribute {attr_name!r}"
        )
        raise AttributeError(msg) from None


def get_attr_directly(
    root: Any,
    attr_path: AttrPath,
) -> Any:
    """Traverses the path and returns the attribute at the end of the path."""
    attr = root
    for attr_name in attr_path:
        attr = getattr(attr, attr_name)
    return attr


def get_obj_dict(obj: Any) -> dict[str, Any]:
    """Combine `__dict__` from `obj` and all its superclasses."""
    result: dict[str, Any] = {}
    for cls in reversed(obj.__class__.mro()):
        result.update(cls.__dict__)
    if hasattr(obj, "__dict__"):
        result.update(obj.__dict__)
    return result
