import asyncio
import copy
import html
import logging
import re
import time
import typing
import unicodedata
from functools import lru_cache

import branca.colormap
import folium
import numpy as np
import pandas as pd
import requests
from folium.plugins import HeatMap, MarkerCluster
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

from mapa.resources import (
    cache_dataframe,
    download_eleitorado_local_votacao,
    download_votacao_agregada,
    download_votacao_secao,
    source_fingerprint,
)

_TypeFiltro = typing.Callable[[pd.DataFrame], pd.Series]
_logger = logging.getLogger(__name__)
_UF_CODES = {
    "RO": "11",
    "AC": "12",
    "AM": "13",
    "RR": "14",
    "PA": "15",
    "AP": "16",
    "TO": "17",
    "MA": "21",
    "PI": "22",
    "CE": "23",
    "RN": "24",
    "PB": "25",
    "PE": "26",
    "AL": "27",
    "SE": "28",
    "BA": "29",
    "MG": "31",
    "ES": "32",
    "RJ": "33",
    "SP": "35",
    "PR": "41",
    "SC": "42",
    "RS": "43",
    "MS": "50",
    "MT": "51",
    "GO": "52",
    "DF": "53",
}
_PALETTE = ["#e0f3f8", "#a6cfe0", "#f4a582", "#d6604d", "#b2182b"]


class _FiltroPartido:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def __call__(self, df: pd.DataFrame) -> pd.Series:
        return df["NR_VOTAVEL"].astype(str).str.startswith(self.prefix)


def filtro_partido(prefix: str = "") -> _TypeFiltro:
    return _FiltroPartido(prefix)


async def download_resources(
    ano: int,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
):
    return await asyncio.gather(
        download_votacao_secao(ano=ano, estado=estado, municipio=municipio),
        download_eleitorado_local_votacao(ano=ano, estado=estado, municipio=municipio),
    )


@lru_cache(maxsize=64)
def _fetch_malha_ibge(nivel: str, id_: str) -> dict:
    url = (
        "https://servicodados.ibge.gov.br/api/v3/malhas/"
        f"{nivel}/{id_}?formato=application/vnd.geo+json&intrarregiao=municipio"
    )
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=1)
def _fetch_municipios_ibge() -> list[dict]:
    response = requests.get(
        "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def centroide_mapa(malha: dict, garantir_dentro: bool = True) -> tuple[float, float]:
    geometries = []
    for feature in malha["features"]:
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        if not geometry.is_empty:
            geometries.append(geometry)
    if not geometries:
        raise ValueError("A malha IBGE não contém geometrias válidas")
    geometry = unary_union(geometries)
    point = geometry.representative_point() if garantir_dentro else geometry.centroid
    return point.y, point.x


def _municipality_uf(item: dict) -> str | None:
    microregion = item.get("microrregiao") or {}
    mesoregion = microregion.get("mesorregiao") or {}
    state = mesoregion.get("UF") or {}
    return state.get("sigla")


def resolver_view(uf: str | None, municipio: str | None) -> tuple[list[float], int]:
    if uf and municipio:
        uf_code = _UF_CODES[uf.upper()]
        municipalities = _fetch_municipios_ibge()
        target = _normalizar_nome(municipio)
        municipality_codes = {
            _normalizar_nome(item["nome"]): str(item["id"])
            for item in municipalities
            if _municipality_uf(item) == uf.upper()
        }
        ibge_code = municipality_codes.get(target)
        malha = _fetch_malha_ibge("estados", uf_code)
        if ibge_code:
            feature = next(
                (
                    item
                    for item in malha["features"]
                    if item["properties"]["codarea"] == ibge_code
                ),
                None,
            )
            if feature:
                return list(centroide_mapa({"features": [feature]})), 13
    if uf:
        malha = _fetch_malha_ibge("estados", _UF_CODES[uf.upper()])
        return list(centroide_mapa(malha)), 7
    malha = _fetch_malha_ibge("paises", "BR")
    return list(centroide_mapa(malha)), 4


def _normalizar_nome(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _scale_index(values: list[float], escala: str) -> list[float]:
    minimum = min(values, default=0.0)
    maximum = max(values, default=1.0)
    maximum = maximum if maximum > minimum else minimum + 1.0
    if escala == "quantil":
        index = np.quantile(
            values or [minimum, maximum], np.linspace(0, 1, len(_PALETTE))
        )
    elif escala == "log":
        index = np.expm1(
            np.linspace(np.log1p(max(0, minimum)), np.log1p(maximum), len(_PALETTE))
        )
    else:
        index = np.linspace(minimum, maximum, len(_PALETTE))
    index = np.asarray(index, dtype=float)
    index[0] = minimum
    index[-1] = maximum
    return np.maximum.accumulate(index).tolist()


def normalizar(
    valores: list[float], escala: str = "linear"
) -> tuple[typing.Callable[[float], str], branca.colormap.LinearColormap]:
    if escala not in {"linear", "quantil", "log"}:
        raise ValueError("escala deve ser linear, quantil ou log")
    finite_values = [float(value) for value in valores if np.isfinite(value)]
    index = _scale_index(finite_values, escala)
    colormap = branca.colormap.LinearColormap(
        colors=_PALETTE,
        index=index,
        vmin=index[0],
        vmax=index[-1],
        caption=f"Votos ({escala})",
    )
    return colormap, colormap


def heatmap_params(valores: list[float], escala: str = "linear") -> dict:
    _, colormap = normalizar(valores, escala)
    positive = [float(value) for value in valores if np.isfinite(value) and value > 0]
    max_val = float(np.percentile(positive, 95)) if positive else 1.0
    density = len(positive)
    radius = int(np.clip(18 + np.sqrt(density) * 1.7, 20, 42))
    blur = int(np.clip(radius * 0.65, 12, 28))
    gradient = {}
    for index, value in enumerate(np.linspace(0, max_val, len(colormap.colors))):
        color = colormap(value)
        gradient[index / (len(colormap.colors) - 1)] = color[:7]
    return {
        "radius": radius,
        "blur": blur,
        "max_val": max_val,
        "min_opacity": 0.2,
        "gradient": gradient,
    }


def _municipality_code_map() -> dict[tuple[str, str], tuple[str, str]]:
    return {
        (
            _municipality_uf(item),
            _normalizar_nome(item["nome"]),
        ): (str(item["id"]), item["nome"])
        for item in _fetch_municipios_ibge()
        if _municipality_uf(item)
    }


def _votes_by_municipality_frame(votes: pd.DataFrame) -> pd.DataFrame:
    result = votes.copy()
    names_to_codes = _municipality_code_map()
    codes_to_names = {
        (uf, code): (code, name) for (uf, _name), (code, name) in names_to_codes.items()
    }
    result["_name_key"] = result["NM_MUNICIPIO"].map(_normalizar_nome)
    result["CD_MUNICIPIO"] = (
        result["CD_MUNICIPIO"].astype(str).str.replace(r"\.0$", "", regex=True)
    )

    def resolve_code(row: pd.Series) -> tuple[str | None, str | None]:
        by_code = codes_to_names.get((row["SG_UF"], row["CD_MUNICIPIO"]))
        if by_code:
            return by_code
        return names_to_codes.get((row["SG_UF"], row["_name_key"]), (None, None))

    result[["CD_IBGE", "IBGE_NAME"]] = result.apply(
        lambda row: pd.Series(resolve_code(row)), axis=1
    )
    return (
        result.groupby(["CD_IBGE", "IBGE_NAME"], dropna=False)["QT_VOTOS"]
        .sum()
        .reset_index()
    )


def _votes_by_municipality(votes: pd.DataFrame) -> dict[tuple[str, str], float]:
    grouped = _votes_by_municipality_frame(votes)
    return {
        (row.CD_IBGE, row.IBGE_NAME): row.QT_VOTOS
        for row in grouped.itertuples(index=False)
    }


def _add_geojson_layer(
    mapa: folium.Map,
    malha: dict,
    votes: pd.DataFrame,
    escala: str,
    cache_key: dict | None = None,
) -> None:
    if cache_key is None:
        grouped = _votes_by_municipality(votes)
    else:
        grouped_frame = cache_dataframe(
            "votos_por_municipio",
            cache_key,
            lambda: _votes_by_municipality_frame(votes),
        )
        grouped_frame["CD_IBGE"] = grouped_frame["CD_IBGE"].where(
            grouped_frame["CD_IBGE"].notna(), None
        )
        grouped_frame["CD_IBGE"] = grouped_frame["CD_IBGE"].map(
            lambda code: str(code) if code is not None else None
        )
        grouped = {
            (row.CD_IBGE, row.IBGE_NAME): row.QT_VOTOS
            for row in grouped_frame.itertuples(index=False)
        }
    code_votes = {
        code: float(count) for (code, _name), count in grouped.items() if pd.notna(code)
    }
    names_by_code = {
        code: name for (code, name), _count in grouped.items() if pd.notna(code)
    }
    all_values = list(code_votes.values())
    color_for, colormap = normalizar(all_values, escala)
    geojson = copy.deepcopy(malha)
    for feature in geojson["features"]:
        code = feature["properties"]["codarea"]
        feature["properties"]["municipio_nome"] = names_by_code.get(code, "Sem dados")
        feature["properties"]["votos"] = code_votes.get(code, 0.0)

    def style_function(feature: dict) -> dict:
        count = code_votes.get(feature["properties"]["codarea"], 0.0)
        return {
            "fillColor": color_for(count),
            "color": "#ffffff",
            "weight": 0.5,
            "fillOpacity": 0.8 if count else 0.15,
        }

    folium.GeoJson(
        geojson,
        name="Votos por município",
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["municipio_nome", "votos"],
            aliases=["Município", "Votos"],
            localize=True,
            labels=True,
        ),
    ).add_to(mapa)
    colormap.add_to(mapa)


def _panel_select(
    name: str,
    label: str,
    options: list[tuple[str, str] | tuple[str, str, str]],
    current: str,
    required: bool = True,
) -> str:
    rendered_options = []
    for option in options:
        value, text = option[:2]
        data_uf = (
            f' data-uf="{html.escape(option[2], quote=True)}"'
            if len(option) == 3
            else ""
        )
        selected = " selected" if value == current else ""
        rendered_options.append(
            f'<option value="{html.escape(value, quote=True)}"{data_uf}{selected}>'
            f"{html.escape(text)}</option>"
        )
    rendered = "".join(rendered_options)
    required_attribute = " required" if required else ""
    return (
        f'<label>{html.escape(label)}<select id="{name}" name="{name}"{required_attribute}>'
        f"{rendered}</select></label>"
    )


def render_painel_filtros(
    mapa: folium.Map,
    ano: int,
    estado: str | None,
    municipio: str | None,
    legenda: str,
    escala: str,
    legendas: list[str] | None = None,
) -> None:
    states = [("", "Brasil")] + [(uf, uf) for uf in _UF_CODES]
    years = sorted({int(ano), 2020, 2022, 2024, 2026}, reverse=True)
    year_options = [(str(value), str(value)) for value in years]
    municipality_items = sorted(
        (
            item["nome"],
            _municipality_uf(item),
        )
        for item in _fetch_municipios_ibge()
        if _municipality_uf(item)
    )
    municipality_options = [("", "Todos os municípios")] + [
        (name, name, uf) for name, uf in municipality_items
    ]
    legend_values = sorted(set(legendas or []) | ({legenda} if legenda else set()))
    legend_options = [(value, value) for value in legend_values]
    if not legend_options:
        legend_options = [("", "Sem legenda disponível")]
    html_panel = f"""
<div id="mapa-loading" role="status" aria-live="polite">
    <span class="mapa-spinner" aria-hidden="true"></span>
    <span id="mapa-loading-message">Preparando mapa...</span>
</div>
<section id="mapa-filtros" aria-label="Filtros do mapa">
  <button class="mapa-handle" type="button" aria-label="Arraste para expandir ou recolher"><span></span></button>
  <form id="mapa-filtros-form">
    <h2>Filtros do mapa</h2>
    {_panel_select("ano", "Ano", year_options, str(ano))}
    {_panel_select("estado", "Estado", states, estado or "", required=False)}
    {_panel_select("municipio", "Município", municipality_options, municipio or "", required=False)}
    {_panel_select("legenda", "Legenda", legend_options, legenda)}
    {_panel_select("escala", "Escala", [(v, v.capitalize()) for v in ("linear", "quantil", "log")], escala)}
    <button class="mapa-aplicar" type="submit">Aplicar</button>
  </form>
</section>
<style>
#mapa-filtros {{ position: fixed; z-index: 10000; right: 18px; bottom: 18px; width: 290px; max-height: calc(100vh - 36px); overflow: auto; padding: 18px; background: #fff; color: #202b35; box-shadow: 0 8px 32px #12202c40; font: 14px/1.4 system-ui, sans-serif; }}
#mapa-filtros h2 {{ margin: 0 0 14px; font-size: 17px; }}
#mapa-filtros label {{ display: block; margin: 0 0 11px; font-weight: 600; }}
#mapa-filtros select {{ display: block; box-sizing: border-box; width: 100%; margin-top: 4px; padding: 9px; border: 1px solid #bdc8ce; border-radius: 3px; background: #fff; color: inherit; font: inherit; }}
#mapa-filtros .mapa-aplicar {{ width: 100%; padding: 10px; border: 0; background: #087e8b; color: #fff; font: inherit; font-weight: 700; cursor: pointer; }}
#mapa-filtros .mapa-handle {{ display: none; }}
#mapa-loading {{ position: fixed; inset: 0; z-index: 20000; display: flex; align-items: center; justify-content: center; gap: 14px; background: #f4f7f8ed; color: #202b35; font: 600 15px/1.4 system-ui, sans-serif; transition: opacity 180ms ease, visibility 180ms ease; }}
#mapa-loading.is-hidden {{ visibility: hidden; opacity: 0; pointer-events: none; }}
.mapa-spinner {{ width: 24px; height: 24px; border: 3px solid #c6d5d9; border-top-color: #087e8b; border-radius: 50%; animation: mapa-spin 750ms linear infinite; }}
@keyframes mapa-spin {{ to {{ transform: rotate(360deg); }} }}
@media (max-width: 700px) {{
  #mapa-filtros {{ inset: auto 0 0; width: auto; height: 26dvh; max-height: 92dvh; overflow: hidden; padding: 0 18px 18px; border-radius: 12px 12px 0 0; transition: height 220ms ease; }}
  #mapa-filtros.expanded {{ height: 92dvh; overflow-y: auto; }}
  #mapa-filtros .mapa-handle {{ display: grid; place-items: center; width: 100%; height: 34px; border: 0; background: transparent; touch-action: none; }}
  #mapa-filtros .mapa-handle span {{ width: 42px; height: 4px; border-radius: 4px; background: #aab5ba; }}
}}
</style>
<script>
(() => {{
  const panel = document.getElementById('mapa-filtros');
  const form = document.getElementById('mapa-filtros-form');
    const loading = document.getElementById('mapa-loading');
    const loadingMessage = document.getElementById('mapa-loading-message');
    const hideLoading = () => loading.classList.add('is-hidden');
    window.addEventListener('load', hideLoading, {{ once: true }});
  form.addEventListener('submit', (event) => {{
    event.preventDefault();
        loadingMessage.textContent = 'Carregando novo mapa...';
        loading.classList.remove('is-hidden');
    const data = new FormData(form);
    const ano = encodeURIComponent(data.get('ano'));
    const municipalitySelect = form.elements.namedItem('municipio');
    const selectedMunicipality = municipalitySelect.options[municipalitySelect.selectedIndex];
    const stateValue = data.get('estado') || selectedMunicipality.dataset.uf || '';
    const estado = encodeURIComponent(stateValue);
    const municipio = encodeURIComponent(data.get('municipio'));
    const legenda = encodeURIComponent(data.get('legenda'));
    const escala = encodeURIComponent(data.get('escala'));
    const path = municipio
      ? `/ano/${{ano}}/estado/${{estado}}/municipio/${{municipio}}/legenda/${{legenda}}`
      : estado
        ? `/ano/${{ano}}/estado/${{estado}}/legenda/${{legenda}}`
        : `/ano/${{ano}}/brasil/legenda/${{legenda}}`;
    window.location = `${{path}}?escala=${{escala}}`;
  }});
  const handle = panel.querySelector('.mapa-handle');
    const stateSelect = form.elements.namedItem('estado');
    const municipalitySelect = form.elements.namedItem('municipio');
    const filterMunicipalities = () => {{
        const selectedState = stateSelect.value;
        for (const option of municipalitySelect.options) {{
            option.hidden = Boolean(selectedState && option.dataset.uf && option.dataset.uf !== selectedState);
        }}
        if (municipalitySelect.selectedOptions[0]?.hidden) municipalitySelect.value = '';
    }};
    stateSelect.addEventListener('change', filterMunicipalities);
    filterMunicipalities();
  let startY = null;
  handle.addEventListener('pointerdown', (event) => {{ startY = event.clientY; handle.setPointerCapture(event.pointerId); }});
  handle.addEventListener('pointerup', (event) => {{
    if (startY === null) return;
    const delta = event.clientY - startY;
    if (Math.abs(delta) > 25) panel.classList.toggle('expanded', delta < 0);
    startY = null;
  }});
}})();
</script>"""
    mapa.get_root().html.add_child(folium.Element(html_panel))


async def _load_votes(ano: int, estado: str | None) -> pd.DataFrame:
    started = time.perf_counter()
    _logger.info("Carregando votos agregados: ano=%s estado=%s", ano, estado or "BR")
    path = await asyncio.to_thread(download_votacao_agregada, ano, estado)
    votes = pd.read_csv(path)
    votes.attrs["source_fingerprint"] = (
        await asyncio.to_thread(source_fingerprint, path)
    )[0]
    _logger.info(
        "Votos prontos: ano=%s estado=%s registros=%s duracao_s=%.2f",
        ano,
        estado or "BR",
        len(votes),
        time.perf_counter() - started,
    )
    return votes


async def _generate_polygon_map(
    ano: int,
    filtro: _TypeFiltro,
    escala: str,
    estado: str | None,
) -> str:
    started = time.perf_counter()
    malha_nivel, malha_id = (
        ("estados", _UF_CODES[estado]) if estado else ("paises", "BR")
    )
    _logger.info(
        "Iniciando mapa de malha: ano=%s nivel=%s id=%s legenda=%s escala=%s",
        ano,
        malha_nivel,
        malha_id,
        getattr(filtro, "prefix", ""),
        escala,
    )
    _logger.info("Carregando malha IBGE: nivel=%s id=%s", malha_nivel, malha_id)
    malha = await asyncio.to_thread(_fetch_malha_ibge, malha_nivel, malha_id)
    _logger.info(
        "Malha IBGE pronta: nivel=%s features=%s", malha_nivel, len(malha["features"])
    )
    votes = await _load_votes(ano, estado)
    legendas = sorted(votes["NR_VOTAVEL"].astype(str).str[:2].unique().tolist())
    source_digest = votes.attrs.get("source_fingerprint")
    filter_prefix = getattr(filtro, "prefix", None)
    cache_key = (
        {"source": source_digest, "prefix": filter_prefix}
        if source_digest is not None and filter_prefix is not None
        else None
    )
    if cache_key is None:
        votes = votes[filtro(votes)]
    else:
        votes = cache_dataframe(
            "votos_filtrados",
            cache_key,
            lambda: votes[filtro(votes)].reset_index(drop=True),
        )
    _logger.info(
        "Votos filtrados: legenda=%s registros=%s",
        getattr(filtro, "prefix", ""),
        len(votes),
    )
    location, zoom = await asyncio.to_thread(resolver_view, estado, None)
    mapa = folium.Map(location=location, zoom_start=zoom)
    _add_geojson_layer(mapa, malha, votes, escala, cache_key)
    render_painel_filtros(
        mapa, ano, estado, None, getattr(filtro, "prefix", ""), escala, legendas
    )
    _logger.info("Serializando HTML do mapa de malha")
    content = mapa.get_root().render()
    _logger.info(
        "Mapa pronto: ano=%s nivel=%s id=%s bytes=%s duracao_s=%.2f",
        ano,
        malha_nivel,
        malha_id,
        len(content),
        time.perf_counter() - started,
    )
    return content


async def generate_map_brasil(
    ano: int, filtro: _TypeFiltro, /, escala: str = "linear"
) -> str:
    return await _generate_polygon_map(ano, filtro, escala, None)


async def generate_map_estado(
    ano: int, filtro: _TypeFiltro, /, estado: str, escala: str = "linear"
) -> str:
    return await _generate_polygon_map(ano, filtro, escala, estado)


async def generate_map(
    ano: int,
    filtro: _TypeFiltro,
    /,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    initial_coords: list[float] | None = None,
    overwrite: bool = False,
    escala: str = "linear",
) -> str:
    started = time.perf_counter()
    _logger.info(
        "Iniciando mapa municipal: ano=%s estado=%s municipio=%s legenda=%s escala=%s",
        ano,
        estado,
        municipio,
        getattr(filtro, "prefix", ""),
        escala,
    )
    votacao_secao_path, eleitorado_local_votacao_path = await download_resources(
        ano=ano, estado=estado, municipio=municipio
    )
    _logger.info("CSVs municipais disponíveis; lendo e cruzando dados")
    source_digests = await asyncio.to_thread(
        source_fingerprint, votacao_secao_path, eleitorado_local_votacao_path
    )
    vote_source_digest = source_digests[0]
    legends_frame = cache_dataframe(
        "legendas_municipais",
        {"source": vote_source_digest},
        lambda: (
            pd.read_csv(votacao_secao_path, usecols=["NR_VOTAVEL"])
            .assign(NR_VOTAVEL=lambda frame: frame["NR_VOTAVEL"].astype(str).str[:2])[
                "NR_VOTAVEL"
            ]
            .drop_duplicates()
            .sort_values()
            .reset_index(drop=True)
            .to_frame()
        ),
    )
    legendas = legends_frame["NR_VOTAVEL"].tolist()
    filter_prefix = getattr(filtro, "prefix", None)

    def aggregate_municipal_votes() -> pd.DataFrame:
        votacao_secao = pd.read_csv(votacao_secao_path)
        votacao_secao = votacao_secao[filtro(votacao_secao)]
        eleitorado_local_votacao = pd.read_csv(eleitorado_local_votacao_path)
        return (
            pd.merge(
                eleitorado_local_votacao,
                votacao_secao,
                on=["CD_MUNICIPIO", "NM_LOCAL_VOTACAO"],
                how="left",
            )
            .groupby(
                ["NM_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE"],
                as_index=False,
            )["QT_VOTOS"]
            .sum()
        )

    if filter_prefix is None:
        votacao_com_local = aggregate_municipal_votes()
    else:
        votacao_com_local = cache_dataframe(
            "votos_por_local",
            {"sources": source_digests, "prefix": filter_prefix},
            aggregate_municipal_votes,
        )
    votacao_com_local = votacao_com_local.set_index(
        ["NM_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE"]
    )
    location, zoom = await asyncio.to_thread(resolver_view, estado, municipio)
    mapa = folium.Map(location=initial_coords or location, zoom_start=zoom)
    cluster = MarkerCluster().add_to(mapa)
    heat_data = []
    for (name, lat, lon), row in votacao_com_local.iterrows():
        lat = float(str(lat).replace(",", "."))
        lon = float(str(lon).replace(",", "."))
        votes = float(row["QT_VOTOS"])
        heat_data.append([lat, lon, votes])
        folium.Marker(location=[lat, lon], popup=name, tooltip=name).add_to(cluster)
    values = [point[2] for point in heat_data]
    params = heatmap_params(values, escala)
    HeatMap(
        heat_data,
        radius=params["radius"],
        blur=params["blur"],
        max_val=params["max_val"],
        min_opacity=params["min_opacity"],
        gradient=params["gradient"],
    ).add_to(mapa)
    _, colormap = normalizar(values, escala)
    colormap.add_to(mapa)
    render_painel_filtros(
        mapa,
        ano,
        estado,
        municipio,
        getattr(filtro, "prefix", ""),
        escala,
        legendas,
    )
    _logger.info("Serializando HTML do mapa municipal")
    content = mapa.get_root().render()
    _logger.info(
        "Mapa municipal pronto: ano=%s estado=%s municipio=%s bytes=%s duracao_s=%.2f",
        ano,
        estado,
        municipio,
        len(content),
        time.perf_counter() - started,
    )
    return content
