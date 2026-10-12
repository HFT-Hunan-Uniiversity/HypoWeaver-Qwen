from pydantic import ValidationError
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


def install(app):
    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        messages = []
        for error in exc.errors():
            location = ".".join(map(str, error["loc"]))
            detail = "未知字段，不允许额外参数" if error["type"] == "extra_forbidden" else error["msg"]
            messages.append(f"{location}: {detail}")
        message = "; ".join(messages)
        return JSONResponse({"error": {"code": "validation", "message": message}}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": str(exc.status_code), "message": str(exc.detail)}}, status_code=exc.status_code
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "处理失败，请查看服务端运行状态后重试"}}, status_code=500
        )
