from abc import ABC, abstractmethod
import attr
from ..changesets import empty, is_empty
def _should_assign(current, new):
    return not is_empty(new) and current != new


@attr.s(hash=True, eq=True, order=True, repr=True, frozen=True)
class UserDetailsChange(object):
    

    birthday = attr.ib(default=empty)
    gender = attr.ib(default=empty)
    location = attr.ib(default=empty)
    website = attr.ib(default=empty)
    avatar = attr.ib(default=empty)
    signature = attr.ib(default=empty)
    notes = attr.ib(default=empty)
    def assign_to_user(self, user):
        for (name, value) in attr.asdict(self).items():
            if _should_assign(getattr(user, name), value):
                setattr(user, name, value)


@attr.s(hash=True, eq=True, order=True, repr=False, frozen=True)
class PasswordUpdate(object):
    

    old_password = attr.ib()
    new_password = attr.ib()


@attr.s(hash=True, eq=True, order=True, repr=True, frozen=True)
class EmailUpdate(object):
    

    
    old_email = attr.ib(converter=lambda x: x.lower())
    new_email = attr.ib(converter=lambda x: x.lower())

@attr.s(hash=True, eq=True, order=True, repr=True, frozen=True)
class SettingsUpdate(object):
    

    language = attr.ib()
    theme = attr.ib()
    def assign_to_user(self, user):
        for (name, value) in attr.asdict(self).items():
            if _should_assign(getattr(user, name), value):
                setattr(user, name, value)


class UserSettingsUpdatePostProcessor(ABC):
    

    @abstractmethod
    def post_process_settings_update(self, user, settings_update):
        pass
