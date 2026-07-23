import secrets

class TokenGenerator:
    @staticmethod
    def generate_secure_token(length_bytes: int = 32) -> str:
        """
        Generate a cryptographically secure random token in hexadecimal format.
        """
        return secrets.token_hex(length_bytes)
