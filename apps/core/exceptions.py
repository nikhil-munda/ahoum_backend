from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """
    Normalize every DRF error response to:
        {"detail": "<human-readable message>", "code": "<error_code>"}

    DRF response.data arrives in three possible shapes:
        1. {"detail": ErrorDetail(...)}        — most APIException subclasses
        2. {"field": [ErrorDetail, ...], ...}  — serializer field-level errors
        3. [ErrorDetail, ...]                  — non-field validation errors
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        return None

    detail, code = _normalize(response.data)
    response.data = {"detail": detail, "code": code}
    return response


def _normalize(data):
    """Return (detail_str, code_str) from any DRF response.data shape."""

    # Shape 1 — {"detail": ErrorDetail(...)}
    if isinstance(data, dict) and "detail" in data:
        err = data["detail"]
        return str(err), getattr(err, "code", "error")

    # Shape 2 — {"field": [ErrorDetail, ...], ...}  (serializer field errors)
    if isinstance(data, dict):
        for errors in data.values():
            if isinstance(errors, list) and errors:
                err = errors[0]
                return str(err), getattr(err, "code", "validation_error")
            return str(errors), getattr(errors, "code", "validation_error")

    # Shape 3 — [ErrorDetail, ...]  (non-field validation errors)
    if isinstance(data, list) and data:
        err = data[0]
        return str(err), getattr(err, "code", "validation_error")

    return "An error occurred.", "error"
