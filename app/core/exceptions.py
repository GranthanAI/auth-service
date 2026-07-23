class AuthServiceException(Exception):
    """Base class for all business logic exceptions in the Auth Service."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class UserAlreadyExistsException(AuthServiceException):
    def __init__(self, email: str):
        super().__init__(f"A user with the email '{email}' already exists.")
        self.email = email

class UserNotFoundException(AuthServiceException):
    def __init__(self, identifier: str):
        super().__init__(f"User '{identifier}' not found.")
        self.identifier = identifier

class IncorrectPasswordException(AuthServiceException):
    def __init__(self):
        super().__init__("The specified current password is incorrect.")

class SamePasswordException(AuthServiceException):
    def __init__(self):
        super().__init__("The new password cannot be the same as the old password.")
