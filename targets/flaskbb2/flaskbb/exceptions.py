from werkzeug.exceptions import HTTPException, Forbidden
from .core.exceptions import BaseFlaskBBError
class FlaskBBHTTPError(BaseFlaskBBError, HTTPException):
    description = "An internal error has occured"
FlaskBBError = FlaskBBHTTPError


class AuthorizationRequired(FlaskBBError, Forbidden):
    description = "Authorization is required to access this area."


class AuthenticationError(FlaskBBError):
    description = "Invalid username and password combination."
