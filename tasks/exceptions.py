from rest_framework.exceptions import ErrorDetail
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    if "error" in response.data:
        return response

    details = []
    errors = response.data if isinstance(response.data, dict) else {"request": response.data}
    for field, issues in errors.items():
        if isinstance(issues, (list, tuple)):
            for issue in issues:
                details.append({
                    "field": str(field),
                    "issue": str(issue.detail if hasattr(issue, "detail") else issue),
                })
        else:
            details.append({
                "field": str(field),
                "issue": str(issues.detail if hasattr(issues, "detail") else issues),
            })

    code = "NOT_FOUND" if response.status_code == 404 else "VALIDATION_ERROR"
    message = "Task not found" if response.status_code == 404 else "Validation failed"
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return response
