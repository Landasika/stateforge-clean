from flask import current_app
from flask_login import current_user
from .locals import current_forum
def force_login_if_needed():
    

    if current_forum and should_force_login(current_user, current_forum):
        return current_app.login_manager.unauthorized()


def should_force_login(user, forum):
    return not user.is_authenticated and not (
        {g.id for g in forum.groups} & {g.id for g in user.groups}
    )
