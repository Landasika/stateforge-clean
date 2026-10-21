from abc import ABC, abstractmethod
import attr
@attr.s(hash=True, eq=False, order=False, repr=True, frozen=True)
class UserRegistrationInfo(object):
    username = attr.ib()
    password = attr.ib(repr=False)
    email = attr.ib()
    language = attr.ib()
    group = attr.ib()


class UserValidator(ABC):
    @abstractmethod
    def validate(self, user_info):
        pass  

    def __call__(self, user_info):
        return self.validate(user_info)


class RegistrationFailureHandler(ABC):
    
    @abstractmethod
    def handle_failure(self, user_info, failures):
        pass

    def __call__(self, user_info, failures):
        self.handle_failure(user_info, failures)
class RegistrationPostProcessor(ABC):
    @abstractmethod
    def post_process(self, user):
        
        pass

    def __call__(self, user):
        self.post_process(user)
class UserRegistrationService(ABC):
    

    @abstractmethod
    def register(self, user_info):
        pass
