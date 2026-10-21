from abc import ABC, abstractmethod
from inspect import isclass
empty = None
class EmptyValue(object):
    

    __slots__ = ()

    def __new__(cls):
        
        global empty
        if empty is None:
            empty = super(EmptyValue, EmptyValue).__new__(cls)
        return empty
    def __eq__(self, other):
        return isinstance(other, EmptyValue) or (
            isclass(other) and issubclass(other, EmptyValue)
        )

    def __bool__(self):
        return False
    __nonzero__ = __bool__


empty = EmptyValue()


def is_empty(value, consider_none=False):
    
    return empty == value or (consider_none and value is None)


class ChangeSetValidator(ABC):
    

    @abstractmethod
    def validate(self, model, changeset):
        
        pass


class ChangeSetHandler(ABC):
    @abstractmethod
    def apply_changeset(self, model, changeset):
        pass

class ChangeSetPostProcessor(ABC):

    @abstractmethod
    def post_process_changeset(self, model, changeset):
        pass
