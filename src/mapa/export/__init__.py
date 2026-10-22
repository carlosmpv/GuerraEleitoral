"""Exportação das camadas do mapa para formatos abertos e utilizáveis em OSM.

São três os formatos entregues:

* ``.osm``    — documento OSM XML, importável no JOSM/iD e enviável para uma
  conta do OpenStreetMap;
* ``.geojson`` — formato lido pelo uMap, QGIS, ArcGIS e pela maioria dos
  visualizadores web;
* ``.zip``    — pacote com os dois formatos, o manifesto dos dados e um
  ``leia-me.txt`` explicando o fluxo de publicação.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any

from mapa.generator import (
    gerar_camada_locais_votacao,
    gerar_camada_votos_municipio,
)

from .osm_xml import feature_collection_to_osm_xml

FORMATO_OSM = "osm"
FORMATO_GEOJSON = "geojson"
FORMATO_ZIP = "zip"
FORMATOS = (FORMATO_OSM, FORMATO_GEOJSON, FORMATO_ZIP)

MEDIA_TYPES = {
    FORMATO_OSM: "application/vnd.osm+xml",
    FORMATO_GEOJSON: "application/geo+json",
    FORMATO_ZIP: "application/zip",
}

LEIA_ME = """\
Camada electoral exportada pelo "Mapas da guerra eleitoral"
==========================================================

Conteúdo do pacote
------------------
* {arquivo_osm}: documento OSM XML (objetos com id negativo = objetos novos).
* {arquivo_geojson}: mesma camada em GeoJSON.
* manifesto.json: metadados (ano, estado, município, legenda, quantidade de
  objetos, extensão geográfica e fontes dos dados).
* leia-me.txt: este arquivo.

O que fazer com o arquivo
-------------------------
1. Editar e publicar na sua conta do OpenStreetMap
   Baixe o "{arquivo_osm}", abra no JOSM (menu Arquivo > Abrir), revise os
   dados e use "Enviar dados" (Ctrl+Shift+U) para criar os objetos na sua
   conta. Depois de publicado, compartilhe o link do editor
   (https://www.openstreetmap.org/edit) ou do mapa
   (https://www.openstreetmap.org/#map=...&layers=N).
   Observação: como os ids são negativos, o JOSM trata tudo como criação
   nova; nada do OpenStreetMap existente é alterado ou apagado.

2. Publicar um mapa compartilhável sem alterar o OSM
   Importe o "{arquivo_geojson}" no uMap (https://umap.openstreetmap.fr),
   escolha um basemap do OpenStreetMap e publique. O uMap devolve um link
   público que pode ser compartilhado com qualquer pessoa.

3. Usar em programas de SIG
   O GeoJSON abre diretamente no QGIS, no ArcGIS, no GeoServer e no Felt.

Tags das camadas
----------------
Todos os objetos carregam as tags do projeto no padrão "eleitoral:*":
* eleitoral:camada    – nome da camada exportada
* eleitoral:ano       – ano da eleição
* eleitoral:uf        – unidade federativa
* electives:municipio – município (quando aplicável)
* eleitoral:legenda   – legenda (partido) filtrada na exportação
* eleitoral:votos     – votos da legenda na unidade
* eleitoral:votos_totais – votos somando todas as legendas na unidade
* eleitoral:eleitorado    – eleitorado registrado no local (quando aplicável)

Fontes dos dados
----------------
* Resultados eleitorais: Tribunal Superior Eleitoral (TSE), dados abertos.
* Malhas territoriais: IBGE, malhas municipalities.
* Geometrias convertidas a partir do formato GeoJSON.
"""


def _slug(texto: str) -> str:
    """Normaliza um texto para uso em nome de arquivo."""
    normalizado = (
        unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", normalizado).strip("_").lower()


def _geojson_bytes(colecao: dict) -> bytes:
    return json.dumps(colecao, ensure_ascii=False, indent=1).encode("utf-8")


def _bbox(colecao: dict) -> list[float] | None:
    """Extensão geográfica ``[minlon, minlat, maxlon, maxlat]`` da camada."""
    valores: list[float] = []

    def percorrer(coordenadas: Any) -> None:
        if not isinstance(coordenadas, (list, tuple)) or not coordenadas:
            return
        if isinstance(coordenadas[0], (int, float)):
            valores.append(float(coordenadas[0]))
            valores.append(float(coordenadas[1]))
            return
        for item in coordenadas:
            percorrer(item)

    for feature in colecao.get("features", []):
        geometria = feature.get("geometry") or {}
        percorrer(geometria.get("coordinates"))
    if not valores:
        return None
    longitudes = valores[0::2]
    latitudes = valores[1::2]
    return [
        round(min(longitudes), 6),
        round(min(latitudes), 6),
        round(max(longitudes), 6),
        round(max(latitudes), 6),
    ]


def _tags_municipio(feature: dict) -> dict[str, Any]:
    """Tags OSM dos polígonos de votos por município."""
    propriedades = feature.get("properties") or {}
    return {
        "name": propriedades.get("municipio_nome"),
        "eleitoral:camada": "votos_municipais",
        "eleitoral:ano": propriedades.get("ano"),
        "eleitoral:uf": propriedades.get("uf"),
        "eleitoral:legenda": propriedades.get("legenda"),
        "eleitoral:votos": propriedades.get("votos"),
        "eleitoral:votos_totais": propriedades.get("votos_total"),
        "source": "TSE",
    }


def _tags_local(feature: dict) -> dict[str, Any]:
    """Tags OSM dos pontos de locais de votação."""
    propriedades = feature.get("properties") or {}
    return {
        "name": propriedades.get("nome_local"),
        "eleitoral:camada": "locais_votacao",
        "eleitoral:ano": propriedades.get("ano"),
        "eleitoral:uf": propriedades.get("uf"),
        "eleitoral:municipio": propriedades.get("municipio"),
        "eleitoral:legenda": propriedades.get("legenda"),
        "eleitoral:votos": propriedades.get("votos"),
        "eleitoral:votos_totais": propriedades.get("votos_total"),
        "eleitoral:eleitorado": propriedades.get("eleitorado"),
        "eleitoral:bairro": propriedades.get("bairro"),
        "eleitoral:zona": propriedades.get("zona"),
        "eleitoral:secoes": propriedades.get("secoes"),
        "eleitoral:tipo_local": propriedades.get("tipo_local"),
        "addr:street": propriedades.get("endereco"),
        "addr:postcode": propriedades.get("cep"),
        "addr:city": propriedades.get("municipio"),
        "source": "TSE",
    }


def _metadados(
    *,
    camada: str,
    ano: int,
    estado: str,
    municipio: str | None,
    legenda: str,
    colecao: dict,
    formato: str,
) -> dict:
    return {
        "camada": camada,
        "gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ano": ano,
        "estado": estado,
        "municipio": municipio,
        "legenda": legenda,
        "formato": formato,
        "quantidade_de_objetos": len(colecao.get("features", [])),
        "bbox": _bbox(colecao),
        "identificadores": "negativos (objetos novos no OpenStreetMap)",
        "fontes": [
            "TSE — resultados das votações (dados abertos)",
            "IBGE — malhas territoriais",
        ],
    }


def _empacotar(
    nome: str,
    colecao: dict,
    tags,
    metadados: dict,
    formato: str,
) -> tuple[bytes, str]:
    """Monta o arquivo final e devolve ``(conteúdo, nome do arquivo)``."""
    osm_bytes = feature_collection_to_osm_xml(
        colecao, tags, propriedades_como_tags=True
    )
    if formato == FORMATO_OSM:
        return osm_bytes, f"{nome}.osm"
    if formato == FORMATO_GEOJSON:
        return _geojson_bytes(colecao), f"{nome}.geojson"
    if formato == FORMATO_ZIP:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pacote:
            pacote.writestr(f"{nome}.osm", osm_bytes)
            pacote.writestr(f"{nome}.geojson", _geojson_bytes(colecao))
            pacote.writestr(
                "manifesto.json",
                json.dumps(metadados, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            pacote.writestr(
                "leia-me.txt",
                LEIA_ME.format(
                    arquivo_osm=f"{nome}.osm", arquivo_geojson=f"{nome}.geojson"
                ).encode("utf-8"),
            )
        return buffer.getvalue(), f"{nome}.zip"
    raise ValueError(f"Formato de exportação desconhecido: {formato}")


async def exportar_votos_municipio(
    ano: int,
    estado: str,
    legenda: str,
    formato: str = FORMATO_ZIP,
) -> tuple[bytes, str]:
    """Exporta a camada de votos por município (polígonos do IBGE)."""
    estado = estado.upper()
    colecao = await gerar_camada_votos_municipio(ano, estado, legenda)
    nome = f"votos_municipais_{estado}_{ano}_{_slug(legenda)}"
    metadados = _metadados(
        camada="votos_municipais",
        ano=ano,
        estado=estado,
        municipio=None,
        legenda=legenda,
        colecao=colecao,
        formato=formato,
    )
    return _empacotar(nome, colecao, _tags_municipio, metadados, formato)


async def exportar_locais_votacao(
    ano: int,
    estado: str,
    municipio: str,
    legenda: str,
    formato: str = FORMATO_ZIP,
) -> tuple[bytes, str]:
    """Exporta a camada de locais de votação (pontos)."""
    estado = estado.upper()
    colecao = await gerar_camada_locais_votacao(ano, estado, municipio, legenda)
    nome = f"locais_votacao_{_slug(municipio)}_{estado}_{ano}_{_slug(legenda)}"
    metadados = _metadados(
        camada="locais_votacao",
        ano=ano,
        estado=estado,
        municipio=municipio,
        legenda=legenda,
        colecao=colecao,
        formato=formato,
    )
    return _empacotar(nome, colecao, _tags_local, metadados, formato)
