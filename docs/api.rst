.. _pyramid_resourceful_api:

API
===

Configuration
-------------

.. autofunction:: pyramid_resourceful.config.add_json_adapters

.. autofunction:: pyramid_resourceful.config.add_resource

.. autofunction:: pyramid_resourceful.config.add_resources

.. autofunction:: pyramid_resourceful.config.enable_cors

.. autofunction:: pyramid_resourceful.config.enable_post_tunneling

Settings
--------

.. autodata:: pyramid_resourceful.settings.DEFAULT_SETTINGS

.. autofunction:: pyramid_resourceful.settings.get_setting

Views
-----

.. autoclass:: pyramid_resourceful.view.ResourceView
   :members:

.. autoclass:: pyramid_resourceful.view.ResourceViewConfig
   :members:

Resources
---------

.. autoclass:: pyramid_resourceful.resource.Resource
   :members:

SQLAlchemy Resource Types
-------------------------

.. autoclass:: pyramid_resourceful.sqlalchemy.SQLAlchemyORMContainerResource
   :members:

.. autoclass:: pyramid_resourceful.sqlalchemy.SQLAlchemyORMItemResource
   :members:
