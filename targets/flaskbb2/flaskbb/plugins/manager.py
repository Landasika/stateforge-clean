import logging
import pluggy
from pkg_resources import (DistributionNotFound, VersionConflict,
                           iter_entry_points)
from flaskbb.utils.helpers import parse_pkg_metadata
logger = logging.getLogger(__name__)


class FlaskBBPluginManager(pluggy.PluginManager):
    

    def __init__(self, project_name):
        super(FlaskBBPluginManager, self).__init__(
            project_name=project_name
        )
        self._plugin_metadata = {}
        self._disabled_plugins = {}
        self._internal_name2plugin = {}

    def register(self, plugin, name=None, internal=False):
        
        
        name = super(FlaskBBPluginManager, self).register(plugin, name)
        if not internal:
            return name

        self._internal_name2plugin[name] = self._name2plugin.pop(name)
        return name

    def unregister(self, plugin=None, name=None):
        plugin = super(FlaskBBPluginManager, self).unregister(
            plugin=plugin, name=name
        )
        name = self.get_name(plugin)
        if self._internal_name2plugin.get(name):
            del self._internal_name2plugin[name]

        return plugin

    def set_blocked(self, name):
        
        super(FlaskBBPluginManager, self).set_blocked(name)
        self._internal_name2plugin[name] = None
    def is_blocked(self, name):
        
        blocked = super(FlaskBBPluginManager, self).is_blocked(name)

        return blocked or name in self._internal_name2plugin and \
            self._internal_name2plugin[name] is None

    def get_plugin(self, name):
        
        plugin = super(FlaskBBPluginManager, self).get_plugin(name)
        return self._internal_name2plugin.get(name, plugin)
    def get_name(self, plugin):
        name = super(FlaskBBPluginManager, self).get_name(plugin)
        if name:
            return name

        for name, val in self._internal_name2plugin.items():
            if plugin == val:
                return name

    def load_setuptools_entrypoints(self, entrypoint_name):
        
        logger.info("Loading plugins under entrypoint {}"
                    .format(entrypoint_name))
        for ep in iter_entry_points(entrypoint_name):
            if self.get_plugin(ep.name):
                continue

            try:
                plugin = ep.load()
            except DistributionNotFound:
                logger.warn("Could not load plugin {}. Passing."
                            .format(ep.name))
                continue
            except VersionConflict as e:
                raise pluggy.PluginValidationError(
                    "Plugin %r could not be loaded: %s!" % (ep.name, e)
                )
            if self.is_blocked(ep.name):
                self._disabled_plugins[plugin] = (ep.name, ep.dist)
                self._plugin_metadata[ep.name] = \
                    parse_pkg_metadata(ep.dist.key)
                continue

            self.register(plugin, name=ep.name)
            self._plugin_distinfo.append((plugin, ep.dist))
            self._plugin_metadata[ep.name] = parse_pkg_metadata(ep.dist.key)
            logger.info("Loaded plugin: {}".format(ep.name))
        logger.info("Loaded {} plugins for entrypoint {}".format(
            len(self._plugin_distinfo),
            entrypoint_name
        ))
        return len(self._plugin_distinfo)

    def get_metadata(self, name):
        
        return self._plugin_metadata.get(name)

    def list_name(self):
        
        return list(self._name2plugin.keys())

    def list_internal_name_plugin(self):
        
        return self._internal_name2plugin.items()

    def list_plugin_metadata(self):
        
        return self._plugin_metadata

    def list_disabled_plugins(self):
        
        return self._disabled_plugins.values()
    def get_disabled_plugins(self):
        
        return self._disabled_plugins.keys()
    def get_internal_plugins(self):
        
        return set(self._internal_name2plugin.values())
    def get_external_plugins(self):
        
        return set(self.get_plugins() - self.get_internal_plugins())
