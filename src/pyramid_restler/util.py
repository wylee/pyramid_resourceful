import re

from pyramid.httpexceptions import exception_response


NOT_SET = object()


def camel_to_underscore(name):
    """Convert camel case name to underscore name."""
    name = re.sub(r"(?<!\b)(?<!_)([A-Z][a-z])", r"_\1", name)
    name = re.sub(r"(?<!\b)(?<!_)([a-z])([A-Z])", r"\1_\2", name)
    name = name.lower()
    return name


def extract_data(request):
    """Extract request data."""
    content_type = request.content_type
    if content_type == "application/x-www-form-urlencoded":
        return request.POST
    elif content_type == "application/json":
        return request.json_body if request.body else None
    raise TypeError(f"Cannot extract data for content type: {content_type}")


def get_param(
    params,
    name,
    converter=None,
    *,
    multi=False,
    strip=True,
    convert_empty_to_none=True,
    default=NOT_SET,
):
    """Get the specified request parameter and, optionally, convert it.

    ``params`` can be any dict-like object, but typically it's
    ``request.GET``.

    If ``multi=True``, ``params`` *must* have a ``.getall()`` method for
    extracting multiple parameters of the same ``name``.

    If ``strip=True``, the param value or values will be stripped before
    being converted.

    If ``convert_empty_to_none=True`` and a param value is blank (empty
    string), it will be converted to ``None``.

    If a ``converter`` is specified, the value or values will be passed
    to this callable for conversion (unless converted to ``None``). If a
    value can't be parsed, a 400 response will be returned immediately.

    If the param isn't present and a ``default`` value is specified,
    that default value will be returned. If no default value is
    specified, a ``KeyError`` will be raised.

    """
    if name not in params:
        if default is NOT_SET:
            params[name]
        return default

    def convert(v):
        if strip:
            v = v.strip()
        if not v and convert_empty_to_none:
            return None
        if converter:
            try:
                v = converter(v)
            except (TypeError, ValueError):
                raise exception_response(
                    400, f"Could not parse parameter {name} with {converter}: {v!r}",
                )
        return v

    if multi:
        values = params.getall(name)
        converted_values = []
        for value in values:
            value = convert(value)
            converted_values.append(value)
        return converted_values

    value = params[name]
    value = convert(value)
    return value
