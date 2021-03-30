import functools
import posixpath
import re
from typing import Any, Dict, List, Sequence, Union

from pyramid.interfaces import ICSRFStoragePolicy, IDefaultCSRFOptions

from .response import exception_response

NOT_SET = type("NOT_SET", (), {"__bool__": (lambda self: False)})()
"""Represents the complete absence of a value."""


def as_bool(string: str) -> bool:
    """Convert string to bool.

    Only the values "1", "true", "0", and "false" are accepted.

    """
    string = string.lower()
    if string in ("1", "true"):
        return True
    if string in ("0", "false"):
        return False
    raise ValueError('Expected value to be one of "1", "true", "0", or "false"')


def as_list(string, sep=",", strip=True):
    """Convert string to list, splitting on comma by default."""
    string = string.strip()
    items = string.split(sep)
    if strip:
        items = [item.strip() for item in items]
    return items


def camel_to_underscore(name):
    """Convert camel case name to underscore name."""
    name = re.sub(r"(?<!\b)(?<!_)([A-Z][a-z])", r"_\1", name)
    name = re.sub(r"(?<!\b)(?<!_)([a-z])([A-Z])", r"\1_\2", name)
    name = name.lower()
    return name


def is_sequence(obj):
    """Is the object a non-string sequence?"""
    return isinstance(obj, Sequence) and not isinstance(obj, str)


def merge_dicts(*dicts) -> Dict:
    """Merge all dicts.

    Dicts later in the list take precedence over dicts earlier in the
    list. As special case, any dicts that are ``None`` will be handled
    as empty dicts.

    """
    return functools.reduce(_merge_dicts, dicts, {})


def _merge_dicts(a, b) -> Dict:
    # Merge dict b into dict a
    if a is None:
        a = {} if b is None else b.__class__
    if b is None:
        b = a.__class__()
    if not (isinstance(a, dict) and isinstance(b, dict)):
        raise TypeError(f"Expected two dicts; got {a.__class__} and {b.__class__}")
    for k, v in b.items():
        if k in a and isinstance(a[k], dict):
            v = merge_dicts(a[k], v)
        a[k] = v
    return a


def obj_name_to_route_name(obj, prefix=None, suffix="_resource"):
    """Convert an object name to a route name.

    This is mainly intended to be used with class and function names. The
    name will be converted to underscore case and, by default, the string
    "_resource" will be stripped from the end::

        >>> obj_name_to_route_name("WorkOrdersResource")
        'work_orders'
        >>> obj_name_to_route_name("WorkOrdersResource", prefix="api")
        'api.work_orders'

    Args:
        obj: A string or any object with a ``__name__`` attribute.
        prefix: If specified, this will be prepended to the route name
            with a dot.
        suffix: Suffix that will be stripped from the end of the
            underscore version of the name.

    """
    if isinstance(obj, str):
        name = obj
    elif hasattr(obj, "__name__"):
        name = obj.__name__
    else:
        raise TypeError("A string or an object with a __name__ attribute is required")
    name = camel_to_underscore(name)
    if suffix and name.endswith(suffix):
        name = name[: -len(suffix)]
    if prefix:
        name = f"{prefix}.{name}"
    return name


def route_name_to_path(route_name, prefix=None, add_slash=False):
    """Convert a route name to a URL path."""
    path = route_name.replace(".", "/")
    path = path.replace("_", "-")
    path = path.strip("/")
    path = f"/{path}"
    if prefix:
        path = posixpath.join(prefix, path.lstrip("/"))
    if add_slash:
        path = f"{path}/"
    return path


def extract_data(request):
    """Extract request data from form or JSON data.

    .. note:: Blank *form* data values will be converted to ``None``.
        This applies only to data posted from HTML forms. JSON data is
        left as is.

    """
    content_type = request.content_type

    if content_type == "application/x-www-form-urlencoded":
        # XXX: Blank values are converted to None
        data = {k: v or None for k, v in request.POST.items()}
    elif content_type == "application/json":
        data = request.json_body if request.body else None
    else:
        raise TypeError(f"Cannot extract data for content type: {content_type}")

    # Remove CSRF token from data, if present
    policy = request.registry.queryUtility(ICSRFStoragePolicy)
    if policy:
        options = request.registry.queryUtility(IDefaultCSRFOptions)
        if options:
            token = options.token
            if token in data:
                del data[token]

    return data


def get_param(
    request,
    name,
    converter=None,
    params=None,
    *,
    multi=False,
    strip=False,
    convert_blank_to_none=True,
    default=NOT_SET,
) -> Union[Any, List[Any]]:
    """Get the specified request parameter and, optionally, convert it.

    Args:
        params: Any dict-like object that *also* has ``getone`` and
            ``getall`` methods. Defaults to ``request.GET``.

        multi (bool): If set, all params with ``name`` will be collected
            into a list (even if there's only one such param). If not
            set, only one param with ``name`` may be present in
            ``params``.

        strip (bool): If set, param values will be stripped before being
            converted.

        convert_blank_to_none (bool): If set, blank param values will be
            converted to ``None``. Blank param values look like ``a=``.

        converter (callable): If specified, the value or values will be
            passed to this callable for conversion (unless converted the
            value was already converted to ``None``). If a value can't
            be parsed, a 400 exception response will be raised.

        default (any): A default value to return when the param isn't
            present. If the param isn't present and no default value is
            specified, a ``KeyError`` will be raised.

    Returns:
        any: When ``multi`` is not set
        list[any]: When ``multi`` is set

    Raises:
        KeyError: Param isn't present and no default value is given.
        KeyError: ``multi=False`` but param is present multiple times.
        400 response: Param value can't be converted by ``converter``.

    Special handling of flag parameters:

    If ``converter`` is ``bool`` or :func:`as_bool` *and* the param is
    specified only once *and* the param has *no* value, the param will
    be handled as a flag. Note that in this example, ``c`` is *not*
    considered a flag due to the equal sign (it has a *blank* value)::

        >>> from pyramid.request import Request
        >>> req = Request.blank("/endpoint?a&!b&c=")
        >>> get_param(req, "a", bool) -> True
        >>> get_param(req, "b", bool) -> False

    """
    if params is None:
        params = request.GET

    if converter is bool:
        converter = as_bool
    elif converter is list:
        converter = as_list

    # Special handling of flags.
    if converter is as_bool and not multi:
        maybe_flags = []
        # NOTE: Splitting is based on urllib.parse.parse_qsl()
        for param in request.query_string.split("&"):
            if "=" not in param:
                if param.startswith("!"):
                    if param[1:].strip():
                        maybe_flags.append(param)
                elif param.strip():
                    maybe_flags.append(param)
        if maybe_flags:
            count = maybe_flags.count(name)
            negated_count = maybe_flags.count(f"!{name}")
            if count == 1 and negated_count == 0:
                return True
            if count == 0 and negated_count == 1:
                return False

    if name not in params:
        if default is NOT_SET:
            raise KeyError(f"Param not present: {name!r}")
        return default

    def convert(v):
        if strip:
            v = v.strip()
        if not v and convert_blank_to_none:
            return None
        if converter:
            try:
                v = converter(v)
            except (TypeError, ValueError):
                raise exception_response(
                    400,
                    detail=f"Could not parse parameter {name} with {converter}: {v!r}",
                )
        return v

    if multi:
        values = params.getall(name)
        values = [convert(value) for value in values]
        return values

    value = params.getone(name)
    value = convert(value)
    return value
