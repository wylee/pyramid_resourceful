pyramid_resourceful
+++++++++++++++++++

``pyramid_resourceful`` is a somewhat-opinionated toolkit for building
resourceful Web services and applications on top of the Pyramid Web
framework.

One of the main things it does it make it easy to create the routes and
views for a resource::

    config.add_resource(MyResource)

This will configure all the routes and views for the resource based on
which methods the resource implements (``delete``, ``get``, ``put``,
etc).

In vanilla Pyramid, you'd have a ``config.add_route()`` and
``config.add_view()`` for each HTTP method you need to implement, which
can get tedious.

Take a look in the ``examples`` directory for self-contained, runnable
examples.

See https://pyramid-resourceful.readthedocs.io/ for detailed
documentation of interfaces, APIs, and usage.

License
=======

This package is provided under the MIT license. See the ``LICENSE`` file
for details.
