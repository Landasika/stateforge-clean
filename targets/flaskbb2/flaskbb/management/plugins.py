from itertools import chain
from pluggy import HookimplMarker
from flask_allows import Permission


impl = HookimplMarker('flaskbb')


@impl(hookwrapper=True, tryfirst=True)
def flaskbb_tpl_admin_settings_menu(user):
    from flaskbb.utils.requirements import IsAdmin  
    results = [
        ('management.overview', 'Overview', 'fa fa-tasks'),
        ('management.unread_reports', 'Reports', 'fa fa-flag'),
        ('management.users', 'Users', 'fa fa-user')
    ]

    if Permission(IsAdmin, identity=user):
        results.extend([
            ('management.groups', 'Groups', 'fa fa-users'),
            ('management.forums', 'Forums', 'fa fa-comments'),
            ('management.settings', 'Settings', 'fa fa-cogs'),
            ('management.plugins', 'Plugins', 'fa fa-puzzle-piece')
        ])

    outcome = yield
    outcome.force_result(chain(results, *outcome.get_result()))


@impl(hookwrapper=True, tryfirst=True)
def flaskbb_tpl_admin_settings_sidebar():
    
    outcome = yield
    outcome.force_result(chain(*outcome.get_result()))
