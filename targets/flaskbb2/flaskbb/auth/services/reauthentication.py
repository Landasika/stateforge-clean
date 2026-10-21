import logging
from flask_babelplus import gettext as _
from werkzeug.security import check_password_hash
from ...core.auth.authentication import (PostReauthenticateHandler,
                                         ReauthenticateFailureHandler,
                                         ReauthenticateManager,
                                         ReauthenticateProvider,
                                         StopAuthentication)
from ...utils.helpers import time_utcnow

logger = logging.getLogger(__name__)


class DefaultFlaskBBReauthProvider(ReauthenticateProvider):
    

    def reauthenticate(self, user, secret):
        if check_password_hash(user.password, secret):  
            return True


class ClearFailedLoginsOnReauth(PostReauthenticateHandler):
    def handle_post_reauth(self, user):
        user.login_attempts = 0

class MarkFailedReauth(ReauthenticateFailureHandler):
    

    def handle_reauth_failure(self, user):
        user.login_attempts += 1
        user.last_failed_login = time_utcnow()
class PluginReauthenticationManager(ReauthenticateManager):
    

    def __init__(self, plugin_manager, session):
        self.plugin_manager = plugin_manager
        self.session = session
    def reauthenticate(self, user, secret):
        try:
            result = self.plugin_manager.hook.flaskbb_reauth_attempt(
                user=user, secret=secret
            )
            if not result:
                raise StopAuthentication(_("Wrong password."))
            self.plugin_manager.hook.flaskbb_post_reauth(user=user)
        except StopAuthentication:
            self.plugin_manager.hook.flaskbb_reauth_failed(user=user)
            raise
        finally:
            try:
                self.session.commit()
            except Exception:
                logger.exception("Exception while processing login")
                self.session.rollback()
                raise
