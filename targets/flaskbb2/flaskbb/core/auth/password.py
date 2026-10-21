from abc import ABC, abstractmethod
class ResetPasswordService(ABC):
    @abstractmethod
    def initiate_password_reset(self, email):
        
        pass

    @abstractmethod
    def reset_password(self, token, email, new_password):
        pass
