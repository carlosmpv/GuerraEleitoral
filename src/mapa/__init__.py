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


@api.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTMLResponse(
        content="""<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mapa eleitoral de São Paulo · Unidade Popular</title>
    <style>
        * { box-sizing: border-box; }
        html, body, main, iframe { width: 100%; height: 100%; margin: 0; border: 0; }
        body { overflow: hidden; background: #e8eff1; font: 15px/1.4 system-ui, sans-serif; color: #202b35; }
        #home-loading { position: fixed; inset: 0; z-index: 10; display: grid; place-content: center; justify-items: center; gap: 14px; background: #f4f7f8; transition: opacity 180ms ease, visibility 180ms ease; }
        #home-loading.is-hidden { visibility: hidden; opacity: 0; pointer-events: none; }
        .home-spinner { width: 30px; height: 30px; border: 3px solid #c6d5d9; border-top-color: #087e8b; border-radius: 50%; animation: spin 750ms linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <main>
        <iframe id="mapa-brasil" title="Mapa eleitoral de São Paulo, Unidade Popular" src="/ano/2026/estado/SP/legenda/80?escala=linear"></iframe>
    </main>
    <div id="home-loading" role="status" aria-live="polite">
        <span class="home-spinner" aria-hidden="true"></span>
        <span>Carregando mapa de São Paulo · Unidade Popular</span>
    </div>
    <script>
        document.getElementById('mapa-brasil').addEventListener('load', () => {
            document.getElementById('home-loading').classList.add('is-hidden');
        }, { once: true });
    </script>
</body>
</html>"""
    )


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
