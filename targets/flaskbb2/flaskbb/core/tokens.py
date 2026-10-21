from abc import ABC, abstractmethod
import attr
from flask_babelplus import gettext as _
from .exceptions import BaseFlaskBBError
class TokenError(BaseFlaskBBError):
    

    def __init__(self, reason):
        self.reason = reason
        super(TokenError, self).__init__(reason)

    @classmethod
    def invalid(cls):
        
        return cls(_('Token is invalid'))
    @classmethod
    def expired(cls):
        return cls(_('Token is expired'))
    
    
    
    @classmethod  
    def bad(cls):
        return cls(_('Token cannot be processed'))

class TokenActions:
    RESET_PASSWORD = 'reset_password'
    ACTIVATE_ACCOUNT = 'activate_account'


@attr.s(frozen=True, eq=True, order=True, hash=True)
class Token(object):
    user_id = attr.ib()
    operation = attr.ib()

class TokenSerializer(ABC):
    @abstractmethod
    def dumps(self, token):
        
        pass
    @abstractmethod
    def loads(self, raw_token):
        pass
class TokenVerifier(ABC):
    @abstractmethod
    def verify_token(self, token, **kwargs):
        
        pass

    def __call__(self, token, **kwargs):
        return self.verify_token(token, **kwargs)
