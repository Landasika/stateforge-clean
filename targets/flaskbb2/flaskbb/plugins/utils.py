from flask import current_app, flash, redirect, url_for
from flask_babelplus import gettext as _
from markupsafe import Markup
from flaskbb.extensions import db
from flaskbb.plugins.models import PluginRegistry
from flaskbb.utils.datastructures import TemplateEventResult
def template_hook(name, silent=True, is_markup=True, **kwargs):
    
    try:
        hook = getattr(current_app.pluggy.hook, name)
        result = TemplateEventResult(hook(**kwargs))
    except AttributeError:  
        if silent:
            return ""
        raise

    if is_markup:
        return Markup(result)
    return result
def validate_plugin(name):
    plugin_module = current_app.pluggy.get_plugin(name)
    if plugin_module is None:
        flash(_("Plugin %(plugin)s not found.", plugin=name), "error")
        return redirect(url_for("management.plugins"))
    return plugin_module

def remove_zombie_plugins_from_db():
    
    d_fs_plugins = [p[0] for p in current_app.pluggy.list_disabled_plugins()]
    d_db_plugins = [
        p.name for p in PluginRegistry.query.filter_by(enabled=False).all()
    ]  

    plugin_names = [p.name for p in PluginRegistry.query.all()]

    remove_me = []
    for p in plugin_names:
        if p in d_db_plugins and p not in d_fs_plugins:
            remove_me.append(p)

    if len(remove_me) > 0:
        PluginRegistry.query.filter(PluginRegistry.name.in_(remove_me)).delete(
            synchronize_session="fetch"
        )
        db.session.commit()
    return remove_me
