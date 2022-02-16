from collections import defaultdict

from starlette.responses import Response as StarletteResponse
from starlette.middleware.base import BaseHTTPMiddleware

from connexion.decorators.validation import ParameterValidator
from connexion.exceptions import BadRequestProblem
from connexion.lifecycle import ConnexionRequest
from connexion.spec import Specification


class ConnexionMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, specification):
        self.app = app
        self.specification = Specification.load(specification)
        self.validator_map = self.build_validator_map()
        super(ConnexionMiddleware, self).__init__(app)

    def build_validator_map(self):
        validator_map = defaultdict(dict)
        paths = self.specification.get('paths', dict())

        for path, methods in paths.items():
            for method, operation in methods.items():
                parameters = operation.get('parameters', [])
                validator = ParameterValidator(parameters, None)
                validator_map[path][method] = validator

        return validator_map

    def validate_request(self, request):
        path = request.url.path
        method = request.method
        validator = self.validator_map[path][method.lower()]
        validator.validate(request)

    def validate_response(self, response):
        pass

    async def dispatch(self, request, call_next):
        try:
            connexion_request = starlette_to_connexion_request(request)
            self.validate_request(connexion_request)
        except BadRequestProblem as e:
            message = f'{e.title}: {e.detail}'
            return StarletteResponse(message, e.status, media_type='text/plain')

        response = await call_next(request)
        self.validate_response(response)
        return response


def starlette_to_connexion_request(request):
    return ConnexionRequest(
        url=request.url,
        method=request.method,
        query=request.query_params
    )
