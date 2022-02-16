from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from starlette.routing import Router

from connexion.apis import AbstractAPI
from connexion.lifecycle import ConnexionRequest, ConnexionResponse
from connexion.security import MiddlewareSecurityHandlerFactory


class MiddlewareAPI(AbstractAPI):

    def __init__(self, specification, **kwargs):
        self.sub_app = Router()
        super().__init__(specification, **kwargs)

    def add_openapi_json(self):
        pass

    def add_openapi_yaml(self):
        pass

    def add_swagger_ui(self):
        pass

    def add_auth_on_not_found(self, security, security_definitions):
        pass

    @staticmethod
    def make_security_handler_factory(pass_context_arg_name):
        return MiddlewareSecurityHandlerFactory(pass_context_arg_name)

    def _add_operation_internal(self, method, path, operation):
        self.sub_app.add_route(path, operation.function, methods=[method])

    @classmethod
    async def get_request(cls, request: StarletteRequest) -> ConnexionRequest:
        body = await request.body()
        return ConnexionRequest(
            url=request.url,
            method=request.method,
            path_params=request.path_params,
            query=request.query_params,
            headers=request.headers,
            body=body,
            json_getter=lambda: cls.jsonifier.loads(body),
            files={},
            context=request.scope
        )

    @classmethod
    async def get_response(cls, response, mimetype=None, request=None):
        return cls._get_response(response, mimetype=mimetype, extra_context={"url": request.url})

    @classmethod
    def _is_framework_response(cls, response):
        return isinstance(response, StarletteResponse)

    @classmethod
    def _framework_to_connexion_response(cls, response: StarletteResponse, mimetype):
        body = None
        if hasattr(response, 'body'):
            body = response.body

        return ConnexionResponse(
            status_code=response.status_code,
            mimetype=mimetype,
            content_type=response.media_type,
            headers=response.headers,
            body=body
        )

    @classmethod
    def _connexion_to_framework_response(cls, response, mimetype, extra_context=None):
        return cls._build_response(
            mimetype=response.mimetype or mimetype,
            status_code=response.status_code,
            content_type=response.content_type,
            headers=response.headers,
            data=response.body.encode(),
            extra_context=extra_context,
        )

    @classmethod
    def _build_response(cls, data, mimetype, content_type=None, status_code=None, headers=None,
                        extra_context=None):
        data, status_code, serialized_mimetype = cls._prepare_body_and_status_code(data=data, mimetype=mimetype, status_code=status_code, extra_context=extra_context)

        content_type = content_type or mimetype or serialized_mimetype
        return StarletteResponse(data, status_code=status_code, headers=headers,
                                 media_type=content_type)
