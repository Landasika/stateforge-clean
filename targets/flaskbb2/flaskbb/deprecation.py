from abc import ABC
import inspect
import warnings
from abc import abstractproperty
from functools import wraps
from flask_babelplus import gettext as _

class FlaskBBWarning(Warning):
    

    pass


class FlaskBBDeprecation(DeprecationWarning, FlaskBBWarning, ABC):
    

    version = abstractproperty(lambda self: None)
class RemovedInFlaskBB3(FlaskBBDeprecation):
    

    version = (3, 0, 0)


def deprecated(message="", category=RemovedInFlaskBB3):
    def deprecation_decorator(f):
        if not issubclass(category, FlaskBBDeprecation):
            raise ValueError(
                "Expected subclass of FlaskBBDeprecation for category, got {}".format(  
                    str(category)
                )
            )

        version = ".".join([str(x) for x in category.version])

        warning = _(
            "%(name)s is deprecated and will be removed in version %(version)s.",  
            name=f.__name__,
            version=version,
        )
        if message:
            warning = "{} {}".format(warning, message)

        docstring = f.__doc__
        if docstring:
            docstring = "\n".join([docstring, warning])
        else:
            docstring = warning
        f.__doc__ = docstring
        @wraps(f)
        def wrapper(*a, **k):
            frame = inspect.currentframe().f_back
            warnings.warn_explicit(
                warning,
                category=category,
                filename=inspect.getfile(frame.f_code),
                lineno=frame.f_lineno,
            )
            return f(*a, **k)

        return wrapper
    return deprecation_decorator
