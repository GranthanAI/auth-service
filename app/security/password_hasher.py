from argon2 import PasswordHasher as ArgonPasswordHasher
from argon2.exceptions import VerifyMismatchError

class PasswordHasher:
    _ph = ArgonPasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32
    )

    @classmethod
    def hash(cls, password: str) -> str:
        """Hash a password using Argon2id."""
        return cls._ph.hash(password)

    @classmethod
    def verify(cls, password_hash: str, password: str) -> bool:
        """Verify a password against an Argon2id hash."""
        try:
            return cls._ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False
        except Exception:
            return False