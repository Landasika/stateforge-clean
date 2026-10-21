class BaseFlaskBBError(Exception):
    pass
class ValidationError(BaseFlaskBBError):
    def __init__(self, attribute, reason):
        self.attribute = attribute
        self.reason = reason
        super(ValidationError, self).__init__((attribute, reason))
class StopValidation(BaseFlaskBBError):
    

    def __init__(self, reasons):
        self.reasons = reasons
        super(StopValidation, self).__init__(reasons)
class PersistenceError(BaseFlaskBBError):
    pass
def accumulate_errors(caller, validators, throw=True):
    errors = []

    for validator in validators:
        try:
            caller(validator)
        except ValidationError as e:
            errors.append((e.attribute, e.reason))

    if len(errors) and throw:
        raise StopValidation(errors)
    return errors
