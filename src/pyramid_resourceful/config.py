import logging
import posixpath
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Sequence

from pyramid.config import Configurator, ConfigurationError
from pyramid.events import NewRequest, NewResponse
from pyramid.interfaces import IRendererFactory

from .cors import add_cors_headers
from .response import exception_response
from .settings import get_setting
from .util import NOT_SET, merge_dicts, obj_name_to_route_name, route_name_to_path
from .view import ResourceView


__all__ = [
    "add_json_adapter",
    "add_json_adapters",
    "add_resource",
    "add_resources",
    "enable_cors",
    "enable_post_tunneling",
]


log = logging.getLogger(__name__)


RENDERER_EXT_MAP = {
    "jinja2": "html",
    "mako": "html",
}


RENDERER_ACCEPT_MAP = {
    "csv": "text/csv",
    "json": "application/json",
    "html": "text/html",
}


@dataclass
class AddResourceInfo:
    name: str
    renderers: List[str]
    path: str
    resource_class: type
    resource_args: dict
    allowed_methods: Sequence[str]
    view: type


def add_json_adapter(self: Configurator, adapter):
    """Add a JSON adapter."""
    type_, adapter = adapter
    renderer = self.registry.getUtility(IRendererFactory, "json")
    renderer.add_adapter(type_, adapter)


def add_json_adapters(self: Configurator, *adapters):
    """Add default and additional JSON adapters.

    Adds default JSON adapters for date, datetime, and decimal objects:

    - date -> ISO date string
    - datetime -> ISO datetime string
    - decimal -> string

    Also adds additional adapters if specified.

    .. note:: If you don't want the defaults, use
        :func:`add_json_adapter` instead.

    """
    renderer = self.registry.getUtility(IRendererFactory, "json")
    adapters = (
        (date, lambda obj, req: obj.isoformat()),
        (datetime, lambda obj, req: obj.isoformat()),
        (Decimal, lambda obj, req: str(obj)),
    ) + adapters
    for type_, adapter in adapters:
        renderer.add_adapter(type_, adapter)


def add_resource(
    self: Configurator,
    resource_class,
    resource_args=None,
    resource_factory=None,
    name=None,
    renderers=["json"],
    # Resource args
    allowed_methods=None,
    acl=NOT_SET,
    # Route args
    path=None,
    segments=(),
    route_args=None,
    # View args
    view=ResourceView,
    permission=None,
    view_args=None,
    # Not generally intended for use by end users
    name_prefix=None,
    path_prefix=None,
) -> AddResourceInfo:
    """Add routes and views for a resource.

    Given a resource (class), generates a set of routes and associated
    views.

    Args:
        resource_class: The class that implements the resource. This
            must accept the current request as its first arg. It may
            also accept other args...

        resource_args: Args that will be passed to the resource factory
            to construct a configured instance of the resource.

        resource_factory: The factory that will be used to create an
            instance of ``resource_class`` for the current request. If
            this isn't specified, the ``resource_class`` itself will be
            used as the factory.

        name: The base route name. If not specified, this will be
            generated from the resource class's module path and class
            name as follows:

            - If the class name ends with "Resource", that's stripped
              off
            - The class name is then converted to camel case
            - The module name containing the class is joined to the
              converted class name with a dot

            So, for a resource class named ``ContainerResource`` in a
            module named ``api``, the computed name will be
            "api.container".

        renderers: A list of renderers to generate routes and views for.
            This can include entries like "json" and/or "template.mako".

            For each renderer, a route with an extension (like ".json"
            and/or ".html") is generated with a view for each
            corresponding resource method. In this case, the response is
            rendered according to the extension.

            In addition, a route with *no* extension is generated with
            a view for each corresponding resource method. In this case,
            the response is rendered according to the Accept header in
            the request.

        allowed_methods: The HTTP methods that are allowed on the
            resource being configured. This is usually derived from the
            methods defined on the ``resource_class``. An
            ``allowed_methods`` attribute will be added resource
            instances that don't already have one.

        acl: An ACL list that will be attached to resource instances as
            the``__acl__`` attribute. If this isn't specified and the
            resource class doesn't have an ``__acl__`` attribute
            already, the default ACL will be attached instead (assuming
            a default ACL is configured).

        path: The base route path. If not specified, this will be
            computed from ``name`` by replacing dots with slashes
            and underscores with dashes. For the example above, the
            computed path would be "/api/container".

        path_prefix: If specified, this will be prepended to all
            generated route paths.

        segments (str|list): Additional path segments to join to
            the base route path. Examples (assuming ``path="/path"``):

            - segments="{id}" -> "/path/{id}"
            - segments=("{a}", "{b}") -> "/path/{a}/{b}"
            - segments="{a}/{b}" -> "/path/{a}/{b}"
            - segments="{c:.+} -> "/path/{c:.+}"

            This is useful when an explicit ``path`` isn't passed (and
            is therefore computed from the resource name). As shown in
            the last example, a regular expression can be included as
            well.

            .. note:: All of the segments *must* be relative paths--they
                should *not* start with slashes.

        route_args: Common route args that will be passed to *every*
            call to ``config.add_view()``.

        view: The view class that will call methods on the resource
            class. This is optional because in many cases the included/
            default view class will suffice.

        permission: Permission that will be set on all generated views.
            This is a special case for convenience.

        view_args: Common view args that will be passed to *every* call
            to ``config.add_view()``.

        name_prefix: If specified, this will be prepended to all
            generated route names (separated by a dot).

            .. note:: This is generally not used directly.

        path_prefix: If specified, this will be prepended to all
            generated route paths (separated by a forward slash).

            .. note:: This is generally not used directly.

    Settings can be set under the "pyramid_resourceful" key:

    - default_acl: Default ACL to attach to resource classes that
      don't have an __acl__ attribute (when ``acl`` isn't specified).

    - resource_methods: Methods on resource classes that will be
      considered resource methods (these should be lower case); if not
      specified, the default :data:`RESOURCE_METHODS` will be used.

    """
    resource_class = self.maybe_dotted(resource_class)

    if resource_args is None:
        resource_args = {}

    if resource_factory is None:
        resource_name = resource_class.__name__
        resource_factory = resource_class
    else:
        resource_factory = self.maybe_dotted(resource_factory)
        resource_name = resource_factory.__name__

    view = self.maybe_dotted(view)
    view_name = view.__name__

    if name is None:
        module_name = resource_factory.__module__.rsplit(".", 1)[-1]
        name = obj_name_to_route_name(resource_factory, prefix=module_name)
        log.debug("Computed route name: %s", name)

    if name_prefix is not None:
        log.debug("Prepending name prefix %s to name: %s", name_prefix, name)
        if name:
            name = f"{name_prefix}.{name}"
        else:
            # Name can be ""
            name = name_prefix

    if path is None:
        path = route_name_to_path(name)
        log.debug("Computed route pattern: %s", path)

    if path_prefix is not None:
        log.debug("Prepending path prefix %s to route pattern: %s", path_prefix, path)
        if path:
            path = posixpath.join(path_prefix, path.lstrip("/"))
        else:
            # Path can be "" to indicate root of prefixed routes
            path = path_prefix

    if segments:
        if isinstance(segments, str):
            segments = (segments,)
        log.debug("Appending path segment(s) to route pattern: %s", ", ".join(segments))
        path = posixpath.join(path, *segments)

    if acl is NOT_SET and getattr(resource_class, "__acl__", NOT_SET) is NOT_SET:
        acl = get_setting(self.get_settings(), "default_acl")
        if acl is not NOT_SET:
            log.debug("Using default ACL for resource: %s", resource_name)

    route_args = {} if route_args is None else route_args

    view_args = {} if view_args is None else view_args
    view_args.setdefault("http_cache", 0)
    if permission:
        view_args["permission"] = permission

    method_config = []
    methods_not_allowed = []
    resource_methods = get_setting(self.get_settings(), "resource_methods")
    resource_methods = tuple(m.lower() for m in resource_methods)

    def add_method_config(resource_class_, method):
        attr = method.lower()
        if not hasattr(resource_class, attr):
            return None
        if not hasattr(view, attr):
            raise ConfigurationError(
                f"View has no method {attr!r} corresponding to "
                f"resource method {attr!r}: {view_name}"
            )
        request_method = attr.upper()
        resource_method = getattr(resource_class_, attr)
        resource_config = getattr(resource_method, "resource_config", None)
        config = (attr, request_method, resource_config)
        method_config.append(config)
        return config

    if allowed_methods:
        # Inspect resource class and find the specified allowed methods.
        allowed_methods = tuple(m.upper() for m in allowed_methods)
        for method in allowed_methods:
            config = add_method_config(resource_class, method)
            if config is None:
                raise ConfigurationError(
                    f"The specified allowed method {method!r} does not exist on "
                    f"resource: {resource_name}"
                )
        methods_not_allowed = [
            m.upper() for m in resource_methods if m not in allowed_methods
        ]
    else:
        # Inspect resource class and find methods based on configured
        # resource methods.
        allowed_methods = []
        for method in resource_methods:
            config = add_method_config(resource_class, method)
            if config is None:
                methods_not_allowed.append(method.upper())
            else:
                attr, request_method, _ = config
                allowed_methods.append(request_method)

    if not allowed_methods:
        raise ConfigurationError(
            f"No resource methods found for resource: {resource_name}"
        )

    if methods_not_allowed:
        log.debug(
            "Resource %s does not allow these methods: %s",
            resource_name,
            ", ".join(methods_not_allowed),
        )

    def factory(request):
        resource = resource_factory(request, **resource_args)
        if acl is not NOT_SET:
            resource.__acl__ = acl
        resource.allowed_methods = allowed_methods
        return resource

    def add_route(route_name, pattern, accept: List[str] = None):
        log.debug(
            "Adding route '%s' with pattern '%s' for resource '%s' "
            "responding to %s accepting content type %s",
            route_name,
            pattern,
            resource_name,
            {", ".join(allowed_methods)},
            {", ".join(accept) if accept else "ANY"},
        )
        self.add_route(
            route_name,
            pattern,
            factory=factory,
            request_method=allowed_methods,
            accept=accept,
            **route_args,
        )

    def add_views(route_name, renderer, accept: str = None):
        for attr, request_method, view_config in method_config:
            if view_config:
                args = {**view_config.view_args, **view_args}
            else:
                args = {**view_args}

            log.debug(
                "Adding view '%s.%s' for route '%s' responding to %s "
                "accepting content type %s with renderer %s",
                view_name,
                attr,
                route_name,
                request_method,
                accept or "ANY",
                renderer,
            )

            self.add_view(
                route_name=route_name,
                view=view,
                attr=attr,
                request_method=request_method,
                accept=accept,
                renderer=renderer,
                **args,
            )

        for request_method in methods_not_allowed:
            self.add_view(
                route_name=route_name,
                view=method_not_allowed_view,
                request_method=request_method,
                accept=accept,
            )

    accepts = []

    # Add route with extension for each renderer. In this case, the
    # accepted renderer is specified by the extension in the URL path
    # (and the Accept header is ignored).
    for renderer in renderers:
        ext, accept = get_ext_and_accept_for_renderer(renderer)
        accepts.append(accept)
        route_name = f"{name}.{ext}"
        pattern = f"{path}.{ext}"
        add_route(route_name, pattern)
        add_views(route_name, renderer)

    # Add route without extension for all renderers. In this case, the
    # accepted renderer is specified by the Accept header.
    add_route(name, path, accepts)
    for accept, renderer in zip(accepts, renderers):
        add_views(name, renderer, accept)

    return AddResourceInfo(
        name=name,
        renderers=renderers,
        path=path,
        resource_class=resource_class,
        resource_args=resource_args,
        allowed_methods=allowed_methods,
        view=view,
    )


@contextmanager
def add_resources(
    self: Configurator,
    name_prefix=None,
    path_prefix=None,
    resource_args=None,
    add_method=None,
    **add_kwargs,
):
    """Add multiple resources with the same base configuration.

    This can be used to add a set of resources under a common name
    and/or path prefix. For example, this sets the name prefix to "api",
    which will cause all the route names to be prefixed with "api." and
    all the route paths to be prefixed with "/api"::

        with config.add_resources("api") as add_resource:
            add_resource(".resources.ContainerResource")
            # name -> api.resources.container
            # path -> /api/resources/container

            add_resource(".resources.ItemResource")
            # name -> api.resources.item
            # path -> /api/resources/item

    If the resources have other shared configuration, the common args
    can be passed in too. For example, to specify the same permission
    for a set of resources/views::

        with config.add_resources("api", permission="admin") as api:
            api(".resources.ContainerResource")
            api(".resources.ItemResource")

    """
    if add_method is None:
        add_method = self.add_resource

    def add(*args, resource_args=None, **kwargs):
        resource_args = merge_dicts(parent_resource_args, resource_args)
        kwargs = {**add_kwargs, **kwargs}
        return add_method(
            *args,
            resource_args=resource_args,
            name_prefix=name_prefix,
            path_prefix=path_prefix,
            **kwargs,
        )

    # Allow nested calls to add_resources()
    def nested_add_resources(
        name_prefix=None,
        path_prefix=None,
        resource_args=None,
        **nested_add_kwargs,
    ):
        if name_prefix and parent_name_prefix:
            name_prefix = f"{parent_name_prefix}.{name_prefix}"
        elif parent_name_prefix:
            name_prefix = parent_name_prefix
        if path_prefix and parent_path_prefix:
            path_prefix = f"{parent_path_prefix}.{path_prefix}"
        elif parent_path_prefix:
            path_prefix = parent_path_prefix
        resource_args = merge_dicts(parent_resource_args, resource_args)
        return self.add_resources(
            name_prefix=name_prefix,
            path_prefix=path_prefix,
            resource_args=resource_args,
            **nested_add_kwargs,
        )

    parent_name_prefix = name_prefix
    parent_path_prefix = path_prefix
    parent_resource_args = {} if resource_args is None else resource_args
    add.add_resources = nested_add_resources

    yield add


def enable_cors(self: Configurator):
    """Enable CORS permissively (for use in development).

    This allows CORS requests from *anywhere*, which is probably not
    what you want, other than in development.

    .. warning:: Use with CAUTION. See :func:`add_cors_headers` for
        additional info.

    """
    self.add_subscriber(add_cors_headers, NewResponse)


def enable_post_tunneling(
    self: Configurator,
    allowed_methods=("DELETE", "PATCH", "PUT"),
    param_name="$method",
    header_name="X-HTTP-Method-Override",
):
    """Allow other request methods to be tunneled via POST.

    This allows DELETE, PATCH, and PUT and requests to be tunneled via
    POST requests. The method can be specified using a parameter or a
    header.

    The name of the parameter is "$method"; it can be a query or POST
    parameter. The query parameter will be preferred if both the query
    and POST parameters are present in the request.

    The name of the header is "X-HTTP-Method-Override". If the parameter
    described above is passed, this will be ignored.

    The request method will be overwritten before it reaches application
    code, such that the application will never be aware of the original
    request method. Likewise, the parameter and header will be removed
    from the request, and the application will never see them.

    """
    allowed_methods = sorted(allowed_methods)
    disallowed_message = (
        f"Only these methods may be tunneled over POST: {allowed_methods}."
    )

    def new_request_subscriber(event):
        request = event.request
        if request.method == "POST":
            if param_name in request.GET:
                method = request.GET[param_name]
            elif param_name in request.POST:
                method = request.POST[param_name]
            elif header_name in request.headers:
                method = request.headers[header_name]
            else:
                return  # Not a tunneled request
            if method in allowed_methods:
                request.GET.pop(param_name, None)
                request.POST.pop(param_name, None)
                request.headers.pop(header_name, None)
                request.method = method
            else:
                raise exception_response(405, detail=disallowed_message)

    self.add_subscriber(new_request_subscriber, NewRequest)


def get_ext_and_accept_for_renderer(renderer):
    if "." in renderer:
        ext = renderer.rsplit(".", 1)[1]
    else:
        ext = renderer
    ext = RENDERER_EXT_MAP.get(ext, ext)
    return ext, RENDERER_ACCEPT_MAP.get(ext)


def method_not_allowed_view(request):
    raise exception_response(405)
