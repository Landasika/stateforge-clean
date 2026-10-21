from celery import Celery
from sqlalchemy import MetaData
from flask_alembic import Alembic
from flask_allows import Allows
from flask_babelplus import Babel
from flask_caching import Cache
from flask_debugtoolbar import DebugToolbarExtension
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_redis import FlaskRedis
from flask_sqlalchemy import SQLAlchemy
from flask_themes2 import Themes
from flask_whooshee import Whooshee
from flask_wtf.csrf import CSRFProtect

from flaskbb.exceptions import AuthorizationRequired



allows = Allows(throws=AuthorizationRequired)


metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
db = SQLAlchemy(metadata=metadata, session_options={"future": True})


whooshee = Whooshee()


login_manager = LoginManager()


mail = Mail()

cache = Cache()

redis_store = FlaskRedis()

debugtoolbar = DebugToolbarExtension()

alembic = Alembic()

themes = Themes()

babel = Babel()

csrf = CSRFProtect()

limiter = Limiter(auto_check=False, key_func=get_remote_address)

celery = Celery("flaskbb")
