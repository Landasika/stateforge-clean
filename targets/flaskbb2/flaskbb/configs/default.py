import os
import sys
import datetime
class DefaultConfig(object):
    
    basedir = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(
                           os.path.dirname(__file__)))))

    
    py_version = '{0.major}{0.minor}'.format(sys.version_info)

    
    DEBUG = False
    TESTING = False
    
    
    
    
    
    PREFERRED_URL_SCHEME = "http"
    
    ALLOWED_HOSTS = None
    
    
    
    
    LOG_CONF_FILE = None
    LOG_PATH = os.path.join(basedir, 'logs')
    LOG_DEFAULT_CONF = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s %(levelname)-7s %(name)-25s %(message)s'
            },
            'advanced': {
                'format': '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            }
        },

        'handlers': {
            'console': {
                'level': 'NOTSET',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
            },
            'flaskbb': {
                'level': 'DEBUG',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(LOG_PATH, 'flaskbb.log'),
                'mode': 'a',
                'maxBytes': 10485760,  
                'backupCount': 5,
            },

            'infolog': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(LOG_PATH, 'info.log'),
                'mode': 'a',
                'maxBytes': 10485760,  
                'backupCount': 5,
            },
            'errorlog': {
                'level': 'ERROR',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(LOG_PATH, 'error.log'),
                'mode': 'a',
                'maxBytes': 10485760,  
                'backupCount': 5,
            }
        },

        'loggers': {
            'flask.app': {
                'handlers': ['infolog', 'errorlog'],
                'level': 'INFO',
                'propagate': True
            },
            'flaskbb': {
                'handlers': ['console', 'flaskbb'],
                'level': 'WARNING',
                'propagate': True
            },
        }
    }

    
    
    
    USE_DEFAULT_LOGGING = True

    
    
    SEND_LOGS = False

    
    
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + basedir + '/' + \
                              'flaskbb.sqlite'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    ALEMBIC = {
        'script_location': os.path.join(basedir, "flaskbb/migrations"),
        'version_locations': '',
        'file_template': '%%(year)d%%(month).2d%%(day).2d%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s'
    }
    ALEMBIC_CONTEXT = {
        'render_as_batch': True
    }

    
    
    
    
    SECRET_KEY = 'secret key'

    
    
    
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = "reallyhardtoguess"
    
    
    WHOOSHEE_DIR = os.path.join(basedir, "whoosh_index", py_version)
    WHOOSHEE_WRITER_TIMEOUT = 2
    
    WHOOSHEE_MIN_STRING_LEN = 3

    LOGIN_VIEW = "auth.login"
    REAUTH_VIEW = "auth.reauth"
    LOGIN_MESSAGE_CATEGORY = "info"
    REFRESH_MESSAGE_CATEGORY = "info"
    
    REMEMBER_COOKIE_NAME = "remember_token"
    REMEMBER_COOKIE_DURATION = datetime.timedelta(days=365)
    
    
    
    REMEMBER_COOKIE_DOMAIN = None
    
    REMEMBER_COOKIE_PATH = "/"
    
    REMEMBER_COOKIE_SECURE = None
    
    REMEMBER_COOKIE_HTTPONLY = False
    
    
    
    
    
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 60

    
    
    
    MAIL_SERVER = "localhost"
    MAIL_PORT = 25
    MAIL_USE_SSL = False
    MAIL_USE_TLS = False
    MAIL_USERNAME = "noreply@example.org"
    MAIL_PASSWORD = ""
    MAIL_DEFAULT_SENDER = ("Default Sender", "noreply@example.org")
    
    ADMINS = ["admin@example.org"]

    
    
    
    
    
    
    REDIS_ENABLED = False
    REDIS_URL = "redis://localhost:6379"  
    REDIS_DATABASE = 0
    CELERY_CONFIG = {
        "broker_url": 'redis://localhost:6379',
        "result_backend": 'redis://localhost:6379',
        "broker_transport_options": {'max_retries': 1},
    }
    
    
    FORUM_URL_PREFIX = ""
    USER_URL_PREFIX = "/user"
    MESSAGE_URL_PREFIX = "/message"
    AUTH_URL_PREFIX = "/auth"
    ADMIN_URL_PREFIX = "/admin"

    
    
    REMOVE_DEAD_PLUGINS = False
