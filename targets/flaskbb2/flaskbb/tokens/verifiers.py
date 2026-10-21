from ..core.tokens import TokenVerifier
from ..core.exceptions import ValidationError
class EmailMatchesUserToken(TokenVerifier):
    def __init__(self, users):
        self.users = users

    def verify_token(self, token, email, **kwargs):
        user = self.users.query.get(token.user_id)
        if user.email.lower() != email.lower():
            raise ValidationError("email", "Wrong email")
