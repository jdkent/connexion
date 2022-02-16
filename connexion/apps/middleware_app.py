"""
"""

import json
import logging
import pathlib
import sys
import typing as t
from contextvars import ContextVar
from functools import partial

import anyio
from starlette.exceptions import ExceptionMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response as StarletteResponse, StreamingResponse
from starlette.routing import Router
from starlette.types import Receive, Scope, Send

from connexion.apis.middleware_api import MiddlewareAPI
from connexion.apps import AbstractApp
from connexion.exceptions import ProblemException
from connexion.resolver import MiddlewareResolver


logger = logging.getLogger('connexion.app')


_call_next_fn: ContextVar[t.Callable] = ContextVar('CALL_NEXT')


async def call_next_callback() -> StarletteResponse:
    return await _call_next_fn.get()()


class MiddlewareApp(AbstractApp):

    def add_api(self, specification, **kwargs):
        api = super().add_api(specification, **kwargs)
        self.app.mount(api.base_path, app=api.sub_app)
        return api

    def create_app(self):
        return Router()

    def get_root_path(self):
        mod = sys.modules.get(self.import_name)
        return pathlib.Path(mod.__file__).resolve().parent

    def route(self, rule, **options):
        raise NotImplementedError('Adding routes not allowed on middleware.')

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        raise NotImplementedError('Adding routes not allowed on middleware.')

    def set_errors_handlers(self):
        pass

    def run(self, port=None, server=None, debug=None, host=None, **options):
        raise NotImplementedError('The middleware is not runnable by itself.')

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return await self.app(scope, receive=receive, send=send)


class ConnexionMiddleware:

    def __init__(self, app, **kwargs):
        self.framework_app = app

        options = {"swagger_ui": False}
        self.connexion_app = MiddlewareApp(
            api_cls=MiddlewareAPI,
            options=options,
            resolver=MiddlewareResolver(call_next_callback),
            **kwargs
        )

        self.exception_middleware = ExceptionMiddleware(self.connexion_app)
        self.exception_middleware.add_exception_handler(ProblemException, problem_handler)

    def add_api(self, specification, **kwargs):
        self.connexion_app.add_api(specification, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Adapted from starlette.middleware.base.BaseHTTPMiddleware
        if scope["type"] != "http":
            await self.framework_app(scope, receive, send)
            return

        async def call_next(request: StarletteRequest, task_group) -> StarletteResponse:
            app_exc: t.Optional[Exception] = None
            send_stream, recv_stream = anyio.create_memory_object_stream()

            async def coro() -> None:
                nonlocal app_exc

                async with send_stream:
                    try:
                        await self.framework_app(scope, request.receive, send_stream.send)
                    except Exception as exc:
                        app_exc = exc

            task_group.start_soon(coro)

            try:
                message = await recv_stream.receive()
            except anyio.EndOfStream:
                if app_exc is not None:
                    raise app_exc
                raise RuntimeError("No response returned.")

            assert message["type"] == "http.response.start"

            async def body_stream() -> t.AsyncGenerator[bytes, None]:
                async with recv_stream:
                    async for message in recv_stream:
                        assert message["type"] == "http.response.body"
                        yield message.get("body", b"")

                if app_exc is not None:
                    raise app_exc

            # response = StreamingResponse(
            #     status_code=message["status"], content=body_stream()
            # )

            # Todo move to API, but needs to be made async
            body = [section async for section in body_stream()]
            body = b''.join(body).decode()

            response = JSONResponse(
                status_code=message["status"], content=json.loads(body)
            )
            response.raw_headers = message["headers"]
            return response

        async with anyio.create_task_group() as task_group:
            request = StarletteRequest(scope, receive=receive)
            call_next = partial(call_next, request, task_group)
            _call_next_fn.set(call_next)

            await self.exception_middleware(scope, receive=receive, send=send)
            await task_group.cancel_scope.cancel()


async def problem_handler(request, exc):
    return JSONResponse({"status": exc.status, "detail": exc.detail}, status_code=exc.status)
