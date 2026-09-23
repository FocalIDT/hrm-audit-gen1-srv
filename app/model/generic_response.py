from typing import Any, Optional


class GenericResponse:
    def __init__(self, is_error: bool, message: str, results: Optional[Any], status_code: int):
        self.is_error = is_error
        self.message = message
        self.results = results
        self.status_code = status_code

    @classmethod
    def success(cls, message: str, results: Optional[Any], status_code: int = 200):
        return cls(is_error=False, message=message, results=results, status_code=status_code)

    @classmethod
    def failed(cls, message: str, results: Optional[Any], status_code: int = 400):
        return cls(is_error=True, message=message, results=results, status_code=status_code)

    def to_dict(self):
        return {
            "is_error": self.is_error,
            "message": self.message,
            "status_code": self.status_code,
            "results": self.results,
        }
