# api/app/infrastructure/auth/password.py

"""Password hashing and verification using bcrypt."""
import bcrypt

# Prefix marking an admin-set one-time password hash; the user must change it.
ONE_TIME_MARKER = "otp$"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Inputs longer than 72 bytes are silently truncated by bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def hash_password_one_time(password: str) -> str:
    """Hash a password and prefix the one-time marker."""
    return ONE_TIME_MARKER + hash_password(password)


def is_one_time_hash(hashed_password: str | None) -> bool:
    """True if the hash carries the one-time marker."""
    return bool(hashed_password) and hashed_password.startswith(ONE_TIME_MARKER)


def verify_password(plain_password: str | None, hashed_password: str | None) -> bool:
    """Verify a password against a bcrypt hash. Applies the same 72-byte truncation as hashing."""
    if plain_password is None or hashed_password is None:
        return False

    if hashed_password.startswith(ONE_TIME_MARKER):
        hashed_password = hashed_password[len(ONE_TIME_MARKER):]

    try:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]

        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except BaseException:
        # bcrypt can surface a Rust PanicException; treat as verification failure.
        return False
