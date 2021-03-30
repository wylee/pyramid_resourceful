import json
from collections import namedtuple
from math import ceil as ceiling

from pyramid.httpexceptions import HTTPNotFound

from sqlalchemy import inspect
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import and_, or_

from .response import exception_response
from .settings import get_setting
from .util import NOT_SET, extract_data, get_param, is_sequence


from .resource import Resource


class FilterSpec(namedtuple("FilterSpec", "operator value")):
    def clone(self, operator=NOT_SET, value=NOT_SET):
        if operator is NOT_SET:
            operator = self.operator
        if value is NOT_SET:
            value = self.value
        return self.__class__(operator, value)


class SQLAlchemyResource(Resource):

    """Base for SQLAlchemy resource types.

    Args:
        request: The current request.

        model: SQLAlchemy ORM class.

        key: Key used to refer to item or items in returned data.

        base_query: Base SQLAlchemy query. If not specified, this will be
            set to ``request.dbsession.query(model)``.

        joined_load_with: Entities to load in the same query. Note that
            func:`sqlalchemy.orm.joinedload` is used to load these
            entities. For complex query logic, this might not be
            suitable.

        filters_to_skip: Filters that should be skipped by
            :meth:`apply_filters`. The intent behind this is to specify
            filters which will be handled specially rather than by the
            default filtering logic.

        filter_converters (dict): A mapping of filter names to converter
            functions. These are used to convert filter values *before*
            they're used to filter a query. For example, this can be
            used to convert date strings to date objects.

    """

    base_query = None
    joined_load_with = ()
    filters_to_skip = ()
    filter_converters = ()

    def __init__(
        self,
        request,
        model=None,
        key=None,
        base_query=None,
        joined_load_with=None,
        filters_to_skip=None,
        filter_converters=None,
        # NOTE: ALL subclass args needs to be passed up
        **kwargs,
    ):
        super().__init__(request)

        cls = self.__class__
        dbsession = request.dbsession
        settings = request.registry.settings

        if model is None:
            model = cls.model
        if key is None:
            key = cls.key
        if base_query is None:
            base_query = cls.base_query or dbsession.query(model)
        if joined_load_with is None:
            joined_load_with = cls.joined_load_with
        if filters_to_skip is None:
            filters_to_skip = cls.filters_to_skip
        if filter_converters is None:
            filter_converters = cls.filter_converters

        self.model = model
        self.key = key
        self.base_query = base_query
        self.joined_load_with = joined_load_with
        self.filters_to_skip = filters_to_skip
        self.filter_converters = filter_converters

        for name, value in kwargs.items():
            if value is None:
                value = getattr(cls, name)
            setattr(self, name, value)

        model_info = inspect(self.model)

        self.dbsession = dbsession
        self.default_response_fields_getter = get_setting(
            settings, "get_default_response_fields"
        )
        self.item_processor = get_setting(settings, "item_processor")
        self.column_attrs = tuple(attr.key for attr in model_info.column_attrs)
        self.default_response_fields = self.column_attrs

    def get_filters(self, *, params=None, converter=json.loads):
        """Get filters from request."""
        return {}

    def convert_filters(self, filters, converters):
        """Convert filter values."""
        if converters:
            for name in converters:
                if name in filters:
                    converter = converters[name]
                    spec = filters[name]
                    value = spec.value
                    if is_sequence(value):
                        value = value.__class__(converter(v) for v in value)
                    else:
                        value = converter(value)
                    filters[name] = spec.clone(value=value)
        return filters

    def apply_filters(self, q, *, skip_filters=()):
        """Get filters and apply them to the base query.

        See :meth:`get_filters` for how filters are specified. By
        default, filters are ANDed together. This can be overridden by
        specifying `$operator=or` in the request's parameters.

        """
        filters = self.get_filters()

        if not filters:
            return q

        filters = self.convert_filters(filters, self.filter_converters)
        model = self.model
        operations = []
        boolean_operator = filters.pop("$operator", "and").lower()

        for name, spec in filters.items():
            if name in skip_filters or name in self.filters_to_skip:
                continue
            try:
                col = getattr(model, name)
            except AttributeError:
                raise exception_response(
                    400,
                    detail=f"Unknown column on model {model.__name__}: {name}",
                )
            operator = getattr(col, spec.operator)
            operations.append(operator(spec.value))

        if boolean_operator == "and":
            q = q.filter(and_(*operations))
        elif boolean_operator == "or":
            q = q.filter(or_(*operations))
        else:
            raise exception_response(
                400,
                detail=f"Unsupported boolean operator: {boolean_operator}",
            )

        return q

    def apply_options(self, q):
        """Apply options to query."""
        if self.joined_load_with:
            for item in self.joined_load_with:
                q = q.options(joinedload(item))
            q = q.populate_existing()
        return q

    def get_response_fields(self, item):
        """Get fields to include in response.

        By default, all column attributes will be included. To include
        additional fields::

            field=*&field=x&field=y&field=z

        The default fields plus ``x``, ``y``, and ``z`` will be
        included.

        To specify only some fields::

            field=a&field=b&field=c

        Only fields ``a``, ``b``, and ``c`` will be included.

        Fields can be passed via one or more ``field`` request
        parameters *or* via a single ``fields`` request parameter
        formatted as a comma-separated list. These are equivalent::

            field=a&field=b&field=c
            fields=a,b,c

        """
        request = self.request
        specified = get_param(request, "field", multi=True, default=None)
        specified = specified or get_param(request, "fields", list, default=None)
        specified = specified or ["*"]
        fields = set()
        for spec in specified:
            if spec == "*":
                fields.update(self.get_default_response_fields(item))
            else:
                fields.add(spec)
        return fields

    def get_default_response_fields(self, item):
        """Get default fields to include in response."""
        default_response_fields_getter = self.default_response_fields_getter
        if default_response_fields_getter:
            return default_response_fields_getter(self, self.model, item, self.request)
        return self.default_response_fields

    def extract_fields(self, item, fields=None):
        """Extract fields from item.

        The incoming item is typically an ORM instance and the returned
        item is typically a dict.

        """
        request = self.request

        if fields is None:
            fields = self.get_response_fields(item)

        new_item = {}

        for name in fields:
            name, *rest = name.split(".", 1)
            obj = getattr(item, name)
            if callable(obj):
                obj = obj(request)
            if rest:
                if is_sequence(obj):
                    result = [self.extract_fields(sub_obj, rest) for sub_obj in obj]
                    if name in new_item:
                        for i, sub_obj in enumerate(result):
                            new_item[name][i].update(sub_obj)
                    else:
                        new_item[name] = result
                else:
                    result = self.extract_fields(obj, rest)
                    if name in new_item:
                        new_item[name].update(result)
                    else:
                        new_item[name] = result
            else:
                new_item[name] = obj

        return new_item

    def process_item(self, item):
        """Process item after fields have been extracted.

        The incoming item is typically a dict. By default, the item is
        returned as is.

        """
        item_processor = self.item_processor
        if item_processor:
            return item_processor(self, self.model, item, self.request)
        return item


class SQLAlchemyContainerResource(SQLAlchemyResource):

    """SQLAlchemy container resource.

    Provides the following methods:

    - ``get`` -> Get all or a filtered subset of items
    - ``post`` -> Add a new item

    """

    key = "items"
    item_key = "item"

    filtering_enabled = True
    filtering_supported_operators = {
        "=": "__eq__",
        "!=": "__ne__",
        "<": "__lt__",
        "<=": "__le__",
        ">": "__gt__",
        ">=": "__ge__",
        "in": "in_",
        "not in": "notin_",
        "like": "like",
        "not like": "notlike",
        "ilike": "ilike",
        "not ilike": "notilike",
        "is": "is_",
        "is not": "isnot",
    }

    ordering_enabled = True
    ordering_default = ()

    # Pagination is enabled by default to avoid huge queries
    pagination_enabled = True
    pagination_default_page_size = 50
    pagination_max_page_size = 250

    def __init__(
        self,
        request,
        model=None,
        key=None,
        base_query=None,
        joined_load_with=None,
        filters_to_skip=None,
        filter_converters=None,
        # Container-specific args
        item_key=None,
        filtering_enabled=None,
        filtering_supported_operators=None,
        ordering_enabled=None,
        ordering_default=None,
        pagination_enabled=None,
        pagination_default_page_size=None,
        pagination_max_page_size=None,
    ):
        kwargs = dict(
            item_key=item_key,
            filtering_enabled=filtering_enabled,
            filtering_supported_operators=filtering_supported_operators,
            ordering_enabled=ordering_enabled,
            ordering_default=ordering_default,
            pagination_enabled=pagination_enabled,
            pagination_default_page_size=pagination_default_page_size,
            pagination_max_page_size=pagination_max_page_size,
        )
        super().__init__(
            request,
            model,
            key,
            base_query,
            joined_load_with,
            filters_to_skip,
            filter_converters,
            **kwargs,
        )

    def get(self, *, wrapped=True):
        """Get items in container."""
        data = {}
        q = self.base_query
        if self.filtering_enabled:
            q = self.apply_filters(q)
        if self.ordering_enabled:
            q = self.apply_ordering(q)
        if self.pagination_enabled:
            q, pagination_data = self.apply_pagination(q)
            if pagination_data is not None:
                data["pagination_data"] = pagination_data
        q = self.apply_options(q)
        items = q.all()
        if not wrapped:
            return items
        items = [self.extract_fields(item) for item in items]
        items = [self.process_item(item) for item in items]
        data[self.key] = items
        return data

    def post(self):
        """Add item to container."""
        data = extract_data(self.request)
        item = self.model(**data)
        self.dbsession.add(item)
        return {self.item_key: item}

    def get_filters(self, *, params=None, converter=json.loads):
        """Get filters from request.

        The ``filters`` query parameter is a JSON-encoded object
        containing filter specifications using one of the following
        formats::

            1. "column": <value>
            2. "column [operator]": <value>

        In the first case, the operator will be ``=`` if the value is
        a scalar or ``in`` if the value is a list.

        For the second case, see the list of allowed operators defined
        by attr:`filtering_supported_operators`.

        Example::

            ?filters={"a": 1, "b": ["1", "2"], "c <": 4}

        This is converted to::

            a = 1 and b in ('1', '2') and c < 4

        .. note:: Filters are extracted from ``request.GET`` by default.
            Pass a different source via ``params`` if necessary (see
            :func:`get_params` for more details).

        """
        request = self.request
        filters = get_param(
            request,
            "filters",
            converter=converter,
            params=params,
            default={},
        )
        if not filters:
            return filters
        supported_operators = self.filtering_supported_operators
        processed_filters = {}
        for spec, value in filters.items():
            name, *operator = spec.split(" ", 1)
            if operator:
                operator = operator[0].lower()
            elif is_sequence(value):
                operator = "in"
            else:
                operator = "="
            if operator not in supported_operators:
                raise exception_response(
                    400, detail=f"Unsupported SQL operator: {operator}"
                )
            operator = supported_operators[operator]
            processed_filters[name] = FilterSpec(operator, value)
        return processed_filters

    def apply_ordering(self, q):
        request = self.request
        ordering = get_param(request, "ordering", multi=True, default=None)
        ordering = ordering or self.ordering_default

        if not ordering:
            return q

        order_by = []
        for item in ordering:
            if isinstance(item, str):
                if item.startswith("-"):
                    item = item[1:]
                    desc = True
                else:
                    desc = False
                item = getattr(self.model, item)
                if desc:
                    item = item.desc()
            order_by.append(item)
        q = q.order_by(*order_by)

        return q

    def apply_pagination(self, q):
        request = self.request
        page = get_param(request, "page", int, default=1)

        page_size = get_param(request, "page_size", default=None)

        # XXX: Page size "*" disables pagination
        if page_size == "*":
            return q, None

        page_size = get_param(
            request, "page_size", int, default=self.pagination_default_page_size
        )

        if page < 1:
            page = 1

        if self.pagination_max_page_size and page_size > self.pagination_max_page_size:
            page_size = self.pagination_max_page_size

        count = q.count()
        num_pages = ceiling(count / page_size)
        offset = (page - 1) * page_size

        q = q.offset(offset)
        q = q.limit(page_size)

        pagination_data = {
            "pages": num_pages,
            "current_page": page,
            "previous_page": 1 if page == 1 else page - 1,
            "next_page": page + 1,
            "page_size": page_size,
            "count": count,
        }

        return q, pagination_data


class SQLAlchemyItemResource(SQLAlchemyResource):

    """SQLAlchemy item resource.

    Provides the following methods:

    - ``delete`` -> Delete item
    - ``get`` -> Get item
    - ``patch`` -> Update some fields on item
    - ``put`` -> Create or update item

    """

    key = "item"

    def delete(self):
        """Delete item."""
        item = self.get(wrapped=False)
        self.dbsession.delete(item)
        return {self.key: item}

    def get(self, *, wrapped=True):
        """Get item."""
        q = self.base_query
        q = self.apply_filters(q)
        q = self.apply_options(q)
        try:
            item = q.one()
        except NoResultFound:
            filters = self.get_filters()
            detail = f"No item found for filters: {filters!r}"
            raise exception_response(404, detail=detail)
        if not wrapped:
            return item
        item = self.extract_fields(item)
        item = self.process_item(item)
        return {self.key: item}

    def patch(self):
        """Update select fields on item."""
        item = self.get(wrapped=False)
        data = extract_data(self.request)
        for name, value in data.items():
            setattr(item, name, value)
        return {self.key: item}

    def put(self):
        """Create or update item.

        If an item with the specified identifier exists, it will
        updated. Otherwise, a new item will be created.

        """
        try:
            item = self.get(wrapped=False)
        except HTTPNotFound:
            item = None
        data = extract_data(self.request)
        if item is None:
            item = self.model(**data)
            self.dbsession.add(item)
        else:
            # TODO: Validate that ``data`` represents a complete item?
            for name, value in data.items():
                setattr(item, name, value)
        return {self.key: item}

    def get_filters(self, *, params=None):
        request = self.request
        params = params or request.matchdict
        filters = {}
        for name, value in params.items():
            try:
                value = json.loads(value)
            except ValueError:
                pass
            filters[name] = FilterSpec("__eq__", value)
        return filters
