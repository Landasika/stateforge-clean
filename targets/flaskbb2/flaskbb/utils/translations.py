import logging
import os
import subprocess
import babel
from flask import current_app
from flask_babelplus import Domain, get_locale
from flask_babelplus.utils import get_state


logger = logging.getLogger(__name__)


class FlaskBBDomain(Domain):
    def __init__(self, app):
        self.app = app
        super(FlaskBBDomain, self).__init__()

        
        with self.app.app_context():
            self.plugin_translations = \
                self.app.pluggy.hook.flaskbb_load_translations()

    def get_translations(self):
        
        state = get_state(silent=True)
        if state is None:
            return babel.support.NullTranslations()

        locale = get_locale()
        cache = self.get_translations_cache()
        translations = cache.get(str(locale))
        if translations is None:
            dirname = self.get_translations_path(state.app)
            translations = babel.support.Translations.load(
                dirname,
                locale,
                domain=self.domain
            )
            
            for plugin in self.plugin_translations:
                logger.debug("Loading plugin translation from: "
                             "{}".format(plugin))
                plugin_translation = babel.support.Translations.load(
                    dirname=plugin,
                    locales=locale,
                    domain="messages"
                )

                if type(plugin_translation) is not babel.support.NullTranslations:
                    translations.add(plugin_translation)
            self.cache[str(locale)] = translations

        return translations


def update_translations(include_plugins=False):
    
    translations_folder = os.path.join(current_app.root_path, "translations")
    source_file = os.path.join(translations_folder, "messages.pot")

    subprocess.call(["pybabel", "extract", "-F", "babel.cfg",
                     "-k", "lazy_gettext", "-o", source_file, "."])
    subprocess.call(["pybabel", "update", "-i", source_file,
                     "-d", translations_folder])

    if include_plugins:
        for plugin in current_app.pluggy.list_name():
            update_plugin_translations(plugin)
def add_translations(translation):
    translations_folder = os.path.join(current_app.root_path, "translations")
    source_file = os.path.join(translations_folder, "messages.pot")

    subprocess.call(["pybabel", "extract", "-F", "babel.cfg",
                     "-k", "lazy_gettext", "-o", source_file, "."])
    subprocess.call(["pybabel", "init", "-i", source_file,
                     "-d", translations_folder, "-l", translation])


def compile_translations(include_plugins=False):
    
    translations_folder = os.path.join(current_app.root_path, "translations")
    subprocess.call(["pybabel", "compile", "-d", translations_folder])

    if include_plugins:
        for plugin in current_app.pluggy.list_name():
            compile_plugin_translations(plugin)
def add_plugin_translations(plugin, translation):
    
    plugin_folder = current_app.pluggy.get_plugin(plugin).__path__[0]
    translations_folder = os.path.join(plugin_folder, "translations")
    source_file = os.path.join(translations_folder, "messages.pot")

    subprocess.call(["pybabel", "extract", "-F", "babel.cfg",
                     "-k", "lazy_gettext", "-o", source_file,
                     plugin_folder])
    subprocess.call(["pybabel", "init", "-i", source_file,
                     "-d", translations_folder, "-l", translation])
def update_plugin_translations(plugin):
    plugin_folder = current_app.pluggy.get_plugin(plugin).__path__[0]
    translations_folder = os.path.join(plugin_folder, "translations")
    source_file = os.path.join(translations_folder, "messages.pot")

    if not os.path.exists(source_file):
        return False

    subprocess.call(["pybabel", "extract", "-F", "babel.cfg",
                     "-k", "lazy_gettext", "-o", source_file,
                     plugin_folder])
    subprocess.call(["pybabel", "update", "-i", source_file,
                     "-d", translations_folder])
def compile_plugin_translations(plugin):
    plugin_folder = current_app.pluggy.get_plugin(plugin).__path__[0]
    translations_folder = os.path.join(plugin_folder, "translations")

    if not os.path.exists(translations_folder):
        return False

    subprocess.call(["pybabel", "compile", "-d", translations_folder])
