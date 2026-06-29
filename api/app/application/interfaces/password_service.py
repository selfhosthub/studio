# api/app/application/interfaces/password_service.py

"""Password hashing interface - implementations must use bcrypt/argon2 or equivalent."""

from abc import ABC, abstractmethod


class PasswordServiceInterface(ABC):
    @abstractmethod
    def hash_password(self, password: str) -> str:
        pass

    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        pass
