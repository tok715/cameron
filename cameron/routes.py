from starlette.responses import JSONResponse


async def route_index(req):
    return JSONResponse(dict(hello='world'))
