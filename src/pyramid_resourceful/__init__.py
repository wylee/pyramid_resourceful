from . import config as config_module
from .resource import resource_config, Resource
from .view import ResourceView

__all__ = [
    "resource_config",
    "Resource",
    "ResourceView",
]


__version__ = "1.0a2"


def includeme(config):
    for name in config_module.__all__:
        method = getattr(config_module, name)
        config.add_directive(name, method)
