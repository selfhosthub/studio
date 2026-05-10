# api/app/infrastructure/auth/password_service.py

"""Bcrypt-based implementation of the application password-service interface."""

from app.application.interfaces.password_service import PasswordServiceInterface
from app.infrastructure.auth.password import hash_password, verify_password


class PasswordService(PasswordServiceInterface):
    def hash_password(self, password: str) -> str:
        return hash_password(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return verify_password(plain_password, hashed_password)
