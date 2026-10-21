import typing
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import HeatMap, MarkerCluster

from mapa.resources import download_eleitorado_local_votacao, download_votacao_secao

MIN_RAIO = 150
MAX_RAIO = 1200
# OUTPUT_PATH = Path("./public")

_TypeFiltro = typing.Callable[[pd.DataFrame], pd.Series]


def filtro_partido(prefix: str = "") -> _TypeFiltro:
    return lambda df: df["NR_VOTAVEL"].astype(str).str.startswith(prefix)


async def download_resources(
    ano: int,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
):
    votacao_secao_promisse = download_votacao_secao(
        ano=ano,
        estado=estado,
        municipio=municipio,
    )

    eleitorado_local_votacao_promisse = download_eleitorado_local_votacao(
        ano=ano,
        estado=estado,
        municipio=municipio,
    )

    return (
        await votacao_secao_promisse,
        await eleitorado_local_votacao_promisse,
    )


async def generate_map(
    ano: int,
    filtro: _TypeFiltro,
    /,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    # output: Path | typing.BinaryIO = OUTPUT_PATH / "index.html",
    initial_coords: list[float] | None = None,
    overwrite: bool = False,
):
    # if isinstance(output, Path) and output.exists() and not overwrite:
    #     return

    initial_coords = (
        initial_coords if initial_coords is not None else [-21.179104, -47.884856]
    )

    votacao_secao_path, eleitorado_local_votacao_path = await download_resources(
        ano=ano,
        estado=estado,
        municipio=municipio,
    )
    votacao_secao = pd.read_csv(votacao_secao_path)
    votacao_secao = votacao_secao[filtro(votacao_secao)]
    eleitorado_local_votacao = pd.read_csv(eleitorado_local_votacao_path)

    votacao_com_local = (
        pd.merge(
            eleitorado_local_votacao,
            votacao_secao,
            on="NM_LOCAL_VOTACAO",
            how="left",
        )
        .groupby(["NM_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE"])["QT_VOTOS"]
        .sum()
        .to_frame()
    )

    map = folium.Map(
        location=initial_coords,
        zoom_start=13,
    )
    cluster = MarkerCluster().add_to(map)

    heat_data = []

    for idx, row in votacao_com_local.iterrows():
        nm_local, lat, lon = idx
        lat = lat.replace(",", ".") if isinstance(lat, str) else lat
        lon = lon.replace(",", ".") if isinstance(lon, str) else lon
        (qt_votos,) = row.values

        heat_data.append([lat, lon, qt_votos])

        folium.Marker(
            location=[lat, lon],
            popup=nm_local,
            tooltip=nm_local,
        ).add_to(cluster)

    HeatMap(heat_data, radius=40).add_to(map)
    return map.get_root().render()
