from datetime import timedelta
from itsdangerous import (BadData, BadSignature, SignatureExpired,
                          TimedJSONWebSignatureSerializer)
from ..core import tokens


_DEFAULT_EXPIRY = timedelta(hours=1)


class FlaskBBTokenSerializer(tokens.TokenSerializer):
    

    def __init__(self, secret_key, expiry=_DEFAULT_EXPIRY):
        self._serializer = TimedJSONWebSignatureSerializer(
            secret_key, int(expiry.total_seconds())
        )
    def dumps(self, token):
        return self._serializer.dumps(
            {
                'id': token.user_id,
                'op': token.operation,
            }
        )
    def loads(self, raw_token):
        try:
            parsed = self._serializer.loads(raw_token)
        except SignatureExpired:
            raise tokens.TokenError.expired()
        except BadSignature:  
            raise tokens.TokenError.invalid()
        
        
        
        
        except BadData:  
            raise tokens.TokenError.bad()
        else:
            return tokens.Token(user_id=parsed['id'], operation=parsed['op'])
