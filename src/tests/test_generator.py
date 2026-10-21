import asyncio
import logging

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from mapa import api, generator


def _fake_municipalities():
    return [
        {
            "nome": "Ribeirão Preto",
            "id": "3543402",
            "microrregiao": {"mesorregiao": {"UF": {"sigla": "SP"}}},
        }
    ]


@pytest.mark.parametrize("escala", ["linear", "quantil", "log"])
def test_normalizar_e_heatmap_params(escala):
    valores = [1, 4, 20, 100]

    color_for, colormap = generator.normalizar(valores, escala)
    params = generator.heatmap_params(valores, escala)

    assert color_for(4).startswith("#")
    assert colormap.vmin <= colormap.vmax
    assert params["max_val"] == pytest.approx(88.0)
    assert params["radius"] > 0
    assert params["gradient"][0.0] == generator._PALETTE[0]


def test_normalizar_rejeita_escala_invalida():
    with pytest.raises(ValueError, match="escala"):
        generator.normalizar([1, 2], "desconhecida")


def test_centroide_mapa_usa_ponto_representativo():
    malha = {
        "features": [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                }
            }
        ]
    }

    assert generator.centroide_mapa(malha) == (1.0, 1.0)


def test_centroide_mapa_repara_poligono_invalido():
    malha = {
        "features": [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
                }
            }
        ]
    }

    latitude, longitude = generator.centroide_mapa(malha)

    assert 0 <= latitude <= 2
    assert 0 <= longitude <= 2


def test_votos_usam_nome_oficial_e_uf_para_obter_codigo_ibge(monkeypatch):
    monkeypatch.setattr(generator, "_fetch_municipios_ibge", _fake_municipalities)
    votos = pd.DataFrame(
        {
            "CD_MUNICIPIO": [69698],
            "NM_MUNICIPIO": ["RIBEIRÃO PRETO"],
            "SG_UF": ["SP"],
            "QT_VOTOS": [12],
        }
    )

    assert generator._votes_by_municipality(votos) == {
        ("3543402", "Ribeirão Preto"): 12
    }


def test_geojson_renderiza_contagem_e_tooltip_sem_heatmap(monkeypatch):
    monkeypatch.setattr(generator, "_fetch_municipios_ibge", _fake_municipalities)
    votos = pd.DataFrame(
        {
            "CD_MUNICIPIO": [69698],
            "NM_MUNICIPIO": ["RIBEIRÃO PRETO"],
            "SG_UF": ["SP"],
            "QT_VOTOS": [12],
        }
    )
    malha = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"codarea": "3543402"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    mapa = generator._create_map([0, 0], 4)

    generator._add_geojson_layer(mapa, malha, votos, "quantil")
    rendered = mapa.get_root().render()

    assert "Ribeir\\u00e3o Preto" in rendered
    assert '"votos": 12.0' in rendered
    assert "HeatMap" not in rendered


def test_mapa_brasil_preserva_opcoes_de_legenda_e_registra_progresso(
    monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(generator, "_fetch_municipios_ibge", _fake_municipalities)
    monkeypatch.setattr(
        generator,
        "_fetch_malha_ibge",
        lambda _level, _id: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"codarea": "3543402"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        generator,
        "_load_votes",
        lambda *_args: asyncio.sleep(
            0,
            result=pd.DataFrame(
                {
                    "CD_MUNICIPIO": [69698, 69698],
                    "NM_MUNICIPIO": ["RIBEIRÃO PRETO", "RIBEIRÃO PRETO"],
                    "SG_UF": ["SP", "SP"],
                    "NR_VOTAVEL": ["13", "22"],
                    "QT_VOTOS": [12, 5],
                }
            ),
        ),
    )
    monkeypatch.setattr(generator, "resolver_view", lambda *_args: ([0.5, 0.5], 4))

    rendered = asyncio.run(
        generator.generate_map_brasil(2022, generator.filtro_partido("13"))
    )

    assert 'name="legenda"' in rendered
    assert 'value="22"' in rendered
    assert "Iniciando mapa de malha" in caplog.text
    assert "Mapa pronto" in caplog.text


def test_painel_preserva_filtros_sem_requisicao_em_change(monkeypatch):
    monkeypatch.setattr(generator, "_fetch_municipios_ibge", _fake_municipalities)
    mapa = generator._create_map([0, 0], 4)

    generator.render_painel_filtros(
        mapa, 2022, "SP", "Ribeirão Preto", "13", "quantil", ["13", 22]
    )
    rendered = mapa.get_root().render()

    assert 'name="ano"' in rendered
    assert 'name="estado"' in rendered
    assert 'name="municipio"' in rendered
    assert 'name="legenda"' in rendered
    assert 'name="escala"' in rendered
    assert 'name="estado" required' not in rendered
    assert 'name="municipio" required' not in rendered
    assert 'value="22"' in rendered
    assert "@media (max-width: 700px)" in rendered
    assert "pointerdown" in rendered
    assert 'id="mapa-loading"' in rendered
    assert "Carregando novo mapa..." in rendered
    assert 'id="mapa-baixar"' in rendered
    assert "Baixar imagem PNG" in rendered
    assert "html2canvas(mapElement" in rendered
    assert "Tiles do mapa indisponíveis" in rendered
    assert "mapa-eleitoral.png" in rendered
    assert '"crossOrigin": "anonymous"' in rendered
    assert "addEventListener('submit'" in rendered
    assert "right: 18px; bottom: 18px" in rendered
    assert "window.location" in rendered


def test_pagina_inicial_carrega_sao_paulo_unidade_popular():
    response = TestClient(api).get("/")

    assert response.status_code == 200
    assert 'src="/ano/2026/estado/SP/legenda/80?escala=linear"' in response.text
    assert "Carregando mapa de São Paulo · Unidade Popular" in response.text
    assert 'id="home-loading"' in response.text
