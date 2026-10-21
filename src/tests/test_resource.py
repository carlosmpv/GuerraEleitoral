import logging

import pandas as pd
import pytest


def test_resources():
    from mapa.resources import download_eleitorado_local_votacao, download_votacao_secao

    download_votacao_secao(2022)
    download_eleitorado_local_votacao(2022)


def test_cache_dataframe_reutiliza_resultado(tmp_path, monkeypatch):
    import pandas as pd

    from mapa import resources

    monkeypatch.setattr(resources, "DATAFRAME_CACHE_PATH", tmp_path)
    expected = pd.DataFrame({"municipio": ["Ribeirão Preto"], "votos": [12]})
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return expected

    first = resources.cache_dataframe("teste", {"ano": 2022}, compute)
    second = resources.cache_dataframe(
        "teste", {"ano": 2022}, lambda: pytest.fail("cache não reutilizado")
    )

    pd.testing.assert_frame_equal(first, expected)
    pd.testing.assert_frame_equal(second, expected)
    assert calls == 1


def test_filter_tse_dataset_registra_progresso_por_bloco(tmp_path, monkeypatch, caplog):
    from mapa import resources

    chunks = [
        pd.DataFrame({"NM_MUNICIPIO": ["A", "B"]}),
        pd.DataFrame({"NM_MUNICIPIO": ["A"]}),
    ]
    monkeypatch.setattr(resources.pd, "read_csv", lambda *_args, **_kwargs: chunks)
    caplog.set_level(logging.INFO, logger="mapa.resources")

    resources.filter_tse_dataset(
        tmp_path / "origem.csv",
        tmp_path / "resultado.csv",
        lambda chunk: chunk[chunk["NM_MUNICIPIO"] == "A"],
    )

    assert "blocos=1 linhas_lidas=2 linhas_selecionadas=1" in caplog.text
    assert "blocos=2 linhas_lidas=3 linhas_selecionadas=2" in caplog.text
    assert "Filtro CSV concluído" in caplog.text


def test_agregacao_rele_csv_com_aspas_invalidas(tmp_path, monkeypatch, caplog):
    import csv

    from mapa import resources

    source = tmp_path / "votacao_secao_2026_SP.csv"
    monkeypatch.setattr(resources, "DATASETS_PATH", tmp_path)
    monkeypatch.setattr(resources, "_votacao_source", lambda *_args: source)
    calls = []
    original_read_csv = pd.read_csv

    def read_csv(path, **kwargs):
        if path != source:
            return original_read_csv(path, **kwargs)
        calls.append(kwargs["quoting"])
        if len(calls) == 1:
            raise pd.errors.ParserError("EOF inside string")
        return [
            pd.DataFrame(
                {
                    "CD_MUNICIPIO": [3550308],
                    "NM_MUNICIPIO": ["SAO PAULO"],
                    "SG_UF": ["SP"],
                    "NR_VOTAVEL": ["13"],
                    "QT_VOTOS": [42],
                }
            )
        ]

    monkeypatch.setattr(resources.pd, "read_csv", read_csv)
    caplog.set_level(logging.WARNING, logger="mapa.resources")

    result_path = resources.download_votacao_agregada(2026, "SP")
    result = pd.read_csv(result_path)

    assert calls == [csv.QUOTE_MINIMAL, csv.QUOTE_NONE]
    assert result["QT_VOTOS"].tolist() == [42]
    assert "tentando leitura literal" in caplog.text
