from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from mapa.generator import (
    filtro_partido,
    generate_map,
    generate_map_brasil,
    generate_map_estado,
)

api = FastAPI()

# [-21.179104, -47.884856]


@api.get("/ano/{ano}/estado/{estado}/municipio/{municipio}/legenda/{legenda}")
async def map(
    ano: int,
    estado: str,
    municipio: str,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
):
    content = await generate_map(
        ano,
        filtro_partido(legenda),
        estado=estado,
        municipio=municipio,
        escala=escala,
    )

    return HTMLResponse(content=content)


@api.get("/ano/{ano}/brasil/legenda/{legenda}")
async def map_brasil(
    ano: int,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
) -> HTMLResponse:
    content = await generate_map_brasil(ano, filtro_partido(legenda), escala=escala)
    return HTMLResponse(content=content)


@api.get("/ano/{ano}/estado/{estado}/legenda/{legenda}")
async def map_estado(
    ano: int,
    estado: str,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
) -> HTMLResponse:
    content = await generate_map_estado(
        ano, filtro_partido(legenda), estado=estado, escala=escala
    )
    return HTMLResponse(content=content)


def main() -> None:
    uvicorn.run(api, host="0.0.0.0", port=8000)
