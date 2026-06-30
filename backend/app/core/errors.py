"""Unified error hierarchy for the entire application."""

from fastapi import HTTPException, status


class NovelManagerError(HTTPException):
    """Base exception for all application errors."""

    def __init__(self, status_code: int, detail: str, error_code: str = ""):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


# ── 4xx Client Errors ─────────────────────────────────────────────

def not_found(resource: str, identifier: str = "") -> NovelManagerError:
    msg = f"{resource} not found" + (f": {identifier}" if identifier else "")
    return NovelManagerError(status.HTTP_404_NOT_FOUND, msg, "NOT_FOUND")


def bad_request(detail: str) -> NovelManagerError:
    return NovelManagerError(status.HTTP_400_BAD_REQUEST, detail, "BAD_REQUEST")


def unauthorized(detail: str = "Invalid credentials") -> NovelManagerError:
    return NovelManagerError(status.HTTP_401_UNAUTHORIZED, detail, "UNAUTHORIZED")


def forbidden(detail: str = "Access denied") -> NovelManagerError:
    return NovelManagerError(status.HTTP_403_FORBIDDEN, detail, "FORBIDDEN")


def conflict(detail: str) -> NovelManagerError:
    return NovelManagerError(status.HTTP_409_CONFLICT, detail, "CONFLICT")


def too_many_requests(retry_after: int = 60) -> NovelManagerError:
    return NovelManagerError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Rate limit exceeded. Retry after {retry_after}s.",
        "RATE_LIMITED",
    )


# ── 5xx Server Errors ─────────────────────────────────────────────

def internal_error(detail: str = "Internal server error") -> NovelManagerError:
    return NovelManagerError(status.HTTP_500_INTERNAL_SERVER_ERROR, detail, "INTERNAL_ERROR")


def service_unavailable(service: str = "") -> NovelManagerError:
    msg = f"Service unavailable" + (f": {service}" if service else "")
    return NovelManagerError(status.HTTP_503_SERVICE_UNAVAILABLE, msg, "UNAVAILABLE")
