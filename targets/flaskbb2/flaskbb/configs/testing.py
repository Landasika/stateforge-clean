from flaskbb.configs.default import DefaultConfig
class TestingConfig(DefaultConfig):
    DEBUG = False
    TESTING = True

    SQLALCHEMY_DATABASE_URI = (
        'sqlite://'
    )

    SERVER_NAME = "localhost:5000"

    
    SQLALCHEMY_ECHO = False

    
    WHOOSHEE_MEMORY_STORAGE = True

    CELERY_CONFIG = {
        "always_eager": True,
        "eager_propagates_exceptions": True,
        "result_backend": "cache",
        "cache_backend": "memory",
    }

    LOG_DEFAULT_CONF = {
        'version': 1,
        'disable_existing_loggers': False,

        'formatters': {
            'standard': {
                'format': '%(asctime)s %(levelname)-7s %(name)-25s %(message)s'
            },
        },

        'handlers': {
            'console': {
                'level': 'NOTSET',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
            },
        },

        
        'loggers': {
            'flask.app': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False
            },
            'flaskbb': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            },
        }
    }
