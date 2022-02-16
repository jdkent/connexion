from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from connexion.apps.middleware_app import ConnexionMiddleware


async def homepage(request):
    value = request.query_params['int']

    if value == '1':
        value = int(value)

    return JSONResponse({'int': value})


app = Starlette(debug=True, routes=[
    Route('/', homepage),
])

app = ConnexionMiddleware(app, import_name=__name__)
app.add_api('openapi.yaml', validate_responses=True)
