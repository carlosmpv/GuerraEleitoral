import io

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from mapa.generator import filtro_partido, generate_map

api = FastAPI()

# [-21.179104, -47.884856]


@api.get("/ano/{ano}/estado/{estado}/municipio/{municipio}/legenda/{legenda}")
async def map(
    ano: int,
    estado: str,
    municipio: str,
    legenda: str,
    lat: float = Query(-21.179104, ge=-90, le=90),
    lng: float = Query(-47.884856, ge=-180, le=180),
):
    content = await generate_map(
        ano,
        filtro_partido(legenda),
        estado=estado,
        municipio=municipio,
        initial_coords=[lat, lng],
    )

    return HTMLResponse(content=content)


def main() -> None:
    uvicorn.run(api, host="0.0.0.0", port=8000)
