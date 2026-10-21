def test_resources():
    from mapa.resources import download_eleitorado_local_votacao, download_votacao_secao

    download_votacao_secao(2022)
    download_eleitorado_local_votacao(2022)
