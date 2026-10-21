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
