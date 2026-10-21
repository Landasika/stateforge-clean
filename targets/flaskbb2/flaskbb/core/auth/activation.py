from abc import ABC, abstractmethod
class AccountActivator(ABC):
    @abstractmethod
    def initiate_account_activation(self, user):
        
        pass

    @abstractmethod
    def activate_account(self, token):
        pass
