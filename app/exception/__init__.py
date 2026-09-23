class BaseAppException(Exception):
    def __init__(self, message: str, status: int = 500):
        self.message = message
        self.status = status
        super().__init__(self.message)


class UnauthorizedException(BaseAppException):
    def __init__(self, message: str = "Unauthorized", status: int = 401):
        super().__init__(message, status)


class ForbiddenException(BaseAppException):
    def __init__(self, message: str = "Forbidden", status: int = 403):
        super().__init__(message, status)


class NotFoundException(BaseAppException):
    def __init__(self, message: str = "Not found", status: int = 404):
        super().__init__(message, status)


class BadRequestException(BaseAppException):
    def __init__(self, message: str = "Bad request", status: int = 400):
        super().__init__(message, status)
