"""Conversão de camadas GeoJSON para o formato OSM XML (arquivo ``.osm``).

O documento gerado segue o formato oficial do OpenStreetMap: nós, vias e
relações com identificadores negativos (ou seja, objetos novos), prontos para
ser importados no JOSM/iD e enviados para uma conta do OpenStreetMap.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

OSM_VERSION = "0.6"
GENERATOR = "mapa-guerra-eleitoral"

TipoTags = Mapping[str, Any] | Callable[[dict], Mapping[str, Any]] | None


def _timestamp() -> str:
    agora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return agora.isoformat().replace("+00:00", "Z")


def _normalizar_tags(tags: Mapping[str, Any]) -> dict[str, str]:
    """Converte os valores das tags em texto válido para o OSM."""
    resultado: dict[str, str] = {}
    for chave, valor in tags.items():
        if valor is None:
            continue
        if isinstance(valor, bool):
            texto = "yes" if valor else "no"
        elif isinstance(valor, float):
            if valor != valor:  # NaN
                continue
            texto = f"{valor:.6f}".rstrip("0").rstrip(".")
        else:
            texto = str(valor)
        texto = texto.strip()
        chave = str(chave).strip()
        if not chave or not texto:
            continue
        resultado[chave] = texto
    return resultado


class _Construtor:
    """Monta a árvore XML do OSM, distribuindo identificadores negativos."""

    def __init__(self, raiz: ET.Element, timestamp: str):
        self.raiz = raiz
        self.timestamp = timestamp
        self._proximo_id = 0
        self._limites: list[float] | None = None

    @property
    def limites(self) -> list[float] | None:
        """``[minlat, minlon, maxlat, maxlon]`` ou ``None``."""
        return self._limites

    def _novo_id(self) -> int:
        self._proximo_id -= 1
        return self._proximo_id

    def _registrar(self, lat: float, lon: float) -> None:
        if self._limites is None:
            self._limites = [lat, lon, lat, lon]
            return
        self._limites[0] = min(self._limites[0], lat)
        self._limites[1] = min(self._limites[1], lon)
        self._limites[2] = max(self._limites[2], lat)
        self._limites[3] = max(self._limites[3], lon)

    def _adicionar_tags(self, elemento: ET.Element, tags: Mapping[str, str]) -> None:
        for chave, valor in tags.items():
            ET.SubElement(elemento, "tag", {"k": chave, "v": valor})

    def adicionar_node(self, lat: float, lon: float, tags: Mapping[str, str]) -> int:
        self._registrar(lat, lon)
        node_id = self._novo_id()
        node = ET.SubElement(
            self.raiz,
            "node",
            {
                "id": str(node_id),
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "version": "1",
                "timestamp": self.timestamp,
            },
        )
        self._adicionar_tags(node, tags)
        return node_id

    def adicionar_way(self, coordenadas: list[tuple[float, float]], tags: Mapping[str, str]) -> int:
        way_id = self._novo_id()
        way = ET.SubElement(
            self.raiz,
            "way",
            {"id": str(way_id), "version": "1", "timestamp": self.timestamp},
        )
        for lat, lon in coordenadas:
            ref = self.adicionar_node(lat, lon, {})
            ET.SubElement(way, "nd", {"ref": str(ref)})
        self._adicionar_tags(way, tags)
        return way_id

    def adicionar_relation(
        self,
        membros: list[tuple[str, int, str]],
        tags: Mapping[str, str],
    ) -> int:
        relation_id = self._novo_id()
        relation = ET.SubElement(
            self.raiz,
            "relation",
            {"id": str(relation_id), "version": "1", "timestamp": self.timestamp},
        )
        for tipo, ref, papel in membros:
            ET.SubElement(
                relation, "member", {"type": tipo, "ref": str(ref), "role": papel}
            )
        self._adicionar_tags(relation, tags)
        return relation_id


def _adicionar_geometria(
    construtor: _Construtor, geometria: BaseGeometry, tags: dict[str, str]
) -> None:
    tipo = geometria.geom_type
    if tipo == "Point":
        construtor.adicionar_node(geometria.y, geometria.x, tags)
    elif tipo == "MultiPoint":
        for ponto in geometria.geoms:
            construtor.adicionar_node(ponto.y, ponto.x, tags)
    elif tipo in {"LineString", "LinearRing"}:
        construtor.adicionar_way(list(geometria.coords), tags)
    elif tipo == "MultiLineString":
        for linha in geometria.geoms:
            construtor.adicionar_way(list(linha.coords), tags)
    elif tipo in {"Polygon", "MultiPolygon"}:
        _adicionar_poligonos(construtor, geometria, tags)
    elif tipo == "GeometryCollection":
        for parte in geometria.geoms:
            _adicionar_geometria(construtor, parte, tags)


def _adicionar_poligonos(
    construtor: _Construtor, geometria: BaseGeometry, tags: dict[str, str]
) -> None:
    """Polígono simples vira uma via fechada; furos ou múltiplas partes viram relação."""
    poligonos = (
        [geometria] if geometria.geom_type == "Polygon" else list(geometria.geoms)
    )
    if len(poligonos) == 1 and not poligonos[0].interiors:
        construtor.adicionar_way(list(poligonos[0].exterior.coords), tags)
        return

    membros: list[tuple[str, int, str]] = []
    for poligono in poligonos:
        membros.append(
            (
                "way",
                construtor.adicionar_way(list(poligono.exterior.coords), {}),
                "outer",
            )
        )
        for interior in poligono.interiors:
            membros.append(
                ("way", construtor.adicionar_way(list(interior.coords), {}), "inner")
            )
    construtor.adicionar_relation(membros, {"type": "multipolygon", **tags})


def _tags_da_feature(
    feature: dict,
    tags: TipoTags,
    propriedades_como_tags: bool,
) -> dict[str, str]:
    if callable(tags):
        base = tags(feature) or {}
    elif tags:
        base = tags
    else:
        base = {}
    propriedades = feature.get("properties") or {}
    combinadas: dict[str, Any] = {}
    if propriedades_como_tags:
        combinadas.update(propriedades)
    combinadas.update(base)
    return _normalizar_tags(combinadas)


def feature_collection_to_osm_xml(
    colecao: dict,
    tags: TipoTags = None,
    *,
    timestamp: str | None = None,
    propriedades_como_tags: bool = False,
) -> bytes:
    """Converte uma FeatureCollection GeoJSON em um documento OSM XML.

    ``tags`` pode ser um dicionário aplicado a todos os objetos ou uma função
    que recebe a feature e devolve as tags específicas dela.
    """
    raiz = ET.Element(
        "osm",
        {"version": OSM_VERSION, "generator": GENERATOR},
    )
    construtor = _Construtor(raiz, timestamp or _timestamp())

    for feature in colecao.get("features", []):
        geometria = feature.get("geometry")
        if not geometria:
            continue
        try:
            forma = shape(geometria)
        except (TypeError, ValueError) as erro:
            raise ValueError(f"Geometria inválida na feature: {erro}") from erro
        if forma.is_empty:
            continue
        _adicionar_geometria(
            construtor,
            forma,
            _tags_da_feature(feature, tags, propriedades_como_tags),
        )

    limites = construtor.limites
    if limites:
        bounds = ET.Element(
            "bounds",
            {
                "minlat": f"{limites[0]:.7f}",
                "minlon": f"{limites[1]:.7f}",
                "maxlat": f"{limites[2]:.7f}",
                "maxlon": f"{limites[3]:.7f}",
            },
        )
        raiz.insert(0, bounds)

    ET.indent(raiz, space="  ")
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True)
