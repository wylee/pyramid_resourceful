from typing import Any, Callable, Dict, List

from pyramid.config import ConfigurationError
from pyramid.path import DottedNameResolver
from pyramid.settings import asbool, aslist

from .util import NOT_SET


__all__ = [
    "DEFAULT_SETTINGS",
    "get_setting",
    "set_setting",
]


KEY = "pyramid_resourceful"


DEFAULT_RESOURCE_METHODS = (
    "delete",
    "get",
    "options",
    "patch",
    "post",
    "put",
)
"""Methods which are considered valid resource/view methods."""


DEFAULT_SETTINGS = {
    "default_acl": NOT_SET,
    "get_default_response_fields": None,
    "item_processor": None,
    "resource_methods": DEFAULT_RESOURCE_METHODS,
}
"""Default settings.

These defaults can be overridden by setting the corresponding keys in
the project's settings under the "pyramid_resourceful" key like so::

    >>> settings = {}
    >>> set_setting(settings, "resource_methods", ["get"])

    .. note:: There's no facility for reading settings from a config
        file at this time.

"""


TYPES: Dict[str, Any] = {
    "default_acl": Any,
    "get_default_response_fields": Callable[..., Any],
    "item_processor": Callable[..., Any],
    "resource_methods": List,
}
"""Types of the :data:`DEFAULT_SETTINGS`.

Used to determine how to convert settings values.

"""


def convert_setting(name, value):
    """Convert setting value according to its defined type."""
    if isinstance(value, str):
        type_ = TYPES[name]
        if type_ is bool:
            converter = asbool
        elif type_ is Callable[..., Any]:
            resolver = DottedNameResolver()
            converter = resolver.maybe_resolve
        elif type_ is List:
            converter = aslist
        elif type_ is Any:
            resolver = DottedNameResolver()
            converter = resolver.maybe_resolve
        else:
            converter = None
        if converter is not None:
            value = converter(value)
    return value


def get_setting(all_settings, name, default=NOT_SET):
    """Get pyramid_resourceful setting from config.

    If the setting wasn't set in the app, the passed ``default`` value
    will be used. If a ``default`` value wasn't passed, the default from
    :data:`DEFAULT_SETTINGS` will be used.

    """
    if name not in DEFAULT_SETTINGS:
        raise KeyError(f"Unknown {KEY} setting: {name}")
    settings = all_settings.get(KEY, {})
    if name in settings:
        value = settings[name]
    elif default is NOT_SET:
        value = DEFAULT_SETTINGS[name]
    else:
        value = default
    return convert_setting(name, value)


def set_setting(all_settings, name, value) -> Any:
    """Set a pyramid_resourceful setting.

    This ensures the top level pyramid_resourceful key exists in the
    settings, checks that ``name`` is a valid setting name, converts the
    setting value according to its defined type, and returns the
    converted value.

    """
    if KEY not in all_settings:
        all_settings[KEY] = {}
    if name not in DEFAULT_SETTINGS:
        raise ConfigurationError(f"Unknown {KEY} setting: {name}")
    value = convert_setting(name, value)
    all_settings[KEY][name] = value
    return value
