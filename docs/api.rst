.. _pyramid_resourceful_api:

API
===

Configuration
-------------

.. autofunction:: pyramid_resourceful.config.add_json_adapter

.. autofunction:: pyramid_resourceful.config.add_json_adapters

.. autofunction:: pyramid_resourceful.config.add_resource

.. autofunction:: pyramid_resourceful.config.add_resources

.. autofunction:: pyramid_resourceful.config.enable_cors

.. autofunction:: pyramid_resourceful.config.enable_post_tunneling

Settings
--------

.. autodata:: pyramid_resourceful.settings.DEFAULT_SETTINGS

.. autofunction:: pyramid_resourceful.settings.get_setting

.. autofunction:: pyramid_resourceful.settings.set_setting

Views
-----

.. autoclass:: pyramid_resourceful.view.ResourceView
   :members:

Resources
---------

.. autofunction:: pyramid_resourceful.resource.resource_config

.. autoclass:: pyramid_resourceful.resource.Resource
   :members:

Utilities
---------

.. autofunction:: pyramid_resourceful.util.extract_data

.. autofunction:: pyramid_resourceful.util.get_param

SQLAlchemy Resource Types
-------------------------

.. autoclass:: pyramid_resourceful.sqlalchemy.SQLAlchemyResource
   :members:

.. autoclass:: pyramid_resourceful.sqlalchemy.SQLAlchemyContainerResource
   :members:

.. autoclass:: pyramid_resourceful.sqlalchemy.SQLAlchemyItemResource
   :members:
