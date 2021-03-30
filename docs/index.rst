pyramid_resourceful
+++++++++++++++++++

Overview
========

`pyramid_resourceful` is a somewhat-opinionated toolkit for building
resourceful Web services and applications on top of the Pyramid
framework.

Resources
=========

Resources focus on the data/logic of your business domain. They are
implemented as classes with methods like ``get``, ``post``, etc
corresponding to HTTP methods. They must also have an ``__init__``
method that accepts the current request as the first argument.

Here's a basic example::

    # A mock "database"
    ITEMS = [
        {"id": 1, "name": "one"},
        {"id": 2, "name": "two"},
    ]

    class ContainerResource:
        def __init__(self, request):
            self.request = request

        def get(self):
            """Get all items."""
            return ITEMS

        def post(self):
            """Add a new item."""
            ITEMS.append({
                "id": max(item["id"] for item in ITEMS) + 1,
                "name": self.request.POST["name"],
            })
            return ITEMS


    class ItemResource:
        def __init__(self, request):
            self.request = request

        def get(self):
            """Get item."""
            return ITEMS[self.request.matchdict["id"]]

        def put(self):
            """Update item."""
            item = ITEMS[self.request.matchdict["id"]]
            item["name"] = self.request.POST["name"]
            return item

Routes
======

A Pyramid configuration directive is provided that generates all the
routes and views for a resource::

    config.add_resource(ContainerResource, name="items")
    config.add_resource(ItemResource, name="item", segments="{id}")

This will configure the following routes and views, which will return
JSON by default:

=========== ========== ========== =========== ========================
HTTP Method Route Name Route Path View Method Resource Method
=========== ========== ========== =========== ========================
GET         items      /items     get()       ContainerResource.get()
POST        items      /items     post()      ContainerResource.post()
GET         item       /item/{id} get()       ItemResource.get()
PUT         item       /item/{id} put()       ItemResource.put()
=========== ========== ========== =========== ========================

Note that only the methods that are present on the resource are routed.

To render HTML or JSON depending on what the request accepts::

    config.add_resource(
        ContainerResource,
        name="items",
        renderers=["items.jinja2", "json"],
    )

The HTML version of the resource can be retrieved using the URLs
``/items`` and ``/items.html``. The JSON version can be retrieved using
the URL ``/items.json`` *or* ``/items`` with the ``Accept`` header set
to ``application/json``.


Views
=====

Views focus on the web aspects of interacting with a resource. They
don't contain any business logic. Like resources, views are implemented
as classes with methods like ``get``, ``post``, etc corresponding to
HTTP methods.

In a typical scenario, you'll only need to define your resource classes
and ``pyramid_resourceful`` will handle the view layer for you in a
standard way (see :class:`pyramid_resourceful.view.ResourceView`).

SQLAlchemy
==========

:class:`pyramid_resourceful.sqlalchemy.SQLAlchemyContainerResource` and
:class:`pyramid_resourceful.sqlalchemy.SQLAlchemyItemResource` are
provided as a starting point for building database-backed resources
using SQLAlchemy ORM classes.

See `examples/sqlalchemy.py`_ for a self-contained, runnable example.

.. _examples/sqlalchemy.py: https://github.com/wylee/pyramid_resourceful/blob/dev/examples/sqlalchemy.py

More Info
=========

.. toctree::
   :maxdepth: 1

   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
