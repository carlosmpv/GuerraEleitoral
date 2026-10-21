import os
import typing
import zipfile
from pathlib import Path

import pandas as pd
import requests

READING_CHUNK_SIZE = 8192

ROOT_PATH = Path(os.getcwd())
RESOURCES_PATH = ROOT_PATH / ".resources"
DOWNLOADS_PATH = RESOURCES_PATH / "downloads"
DATASETS_PATH = RESOURCES_PATH / "datasets"

RESOURCES_PATH.exists() or os.mkdir(RESOURCES_PATH)
DOWNLOADS_PATH.exists() or os.mkdir(DOWNLOADS_PATH)
DATASETS_PATH.exists() or os.mkdir(DATASETS_PATH)


def download(url: str, output: Path):
    print(f"Baixando dataset de '{url}'")
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
        },
    )

    if not response.ok:
        raise RuntimeError(response.status_code, response.content.decode("utf-8"))

    with open(output, "wb") as out:
        print(f"Escrevendo em '{output}'")
        out.writelines(response.iter_content(chunk_size=READING_CHUNK_SIZE))


def extract_zip(input: Path, output: Path):
    print(f"Extraindo {input}")
    with zipfile.ZipFile(input, "r") as ref:
        ref.extractall(output)


def filter_tse_dataset(
    input: Path,
    output: Path,
    filter: typing.Callable[[pd.DataFrame], pd.DataFrame],
):
    result = pd.DataFrame()
    for chunk in pd.read_csv(
        input, encoding="latin_1", sep=";", chunksize=READING_CHUNK_SIZE
    ):
        result = pd.concat([result, filter(chunk)])

    result.to_csv(output)


def _votacao_source(ano: int, estado: str) -> Path:
    url = f"https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_{ano}_{estado}.zip"
    downloaded_zip_path = DOWNLOADS_PATH / f"votacao_secao_{ano}_{estado}.zip"
    extracted_data_path = DOWNLOADS_PATH / f"votacao_secao_{ano}_{estado}"
    csv_data_path = extracted_data_path / f"votacao_secao_{ano}_{estado}.csv"
    if not downloaded_zip_path.exists():
        download(url, downloaded_zip_path)
    if not extracted_data_path.exists():
        extract_zip(downloaded_zip_path, extracted_data_path)
    if not csv_data_path.exists():
        raise RuntimeError(f"{csv_data_path} should exist")
    return csv_data_path


async def download_votacao_secao(
    ano: int,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    overwrite=False,
):
    result_path = DATASETS_PATH / f"votacao_secao_{municipio}_{estado}_{ano}.csv"

    if result_path.exists() and not overwrite:
        print(f"{result_path} already exists, ignoring")
        return result_path

    csv_data_path = _votacao_source(ano, estado)

    filter_tse_dataset(
        csv_data_path,
        result_path,
        lambda chunk: chunk[chunk["NM_MUNICIPIO"] == municipio.upper()],
    )

    print("Done.")
    return result_path


def download_votacao_agregada(ano: int, estado: str | None = None) -> Path:
    """Cacheia votos agregados por município para uma UF ou para o Brasil."""
    states = (
        [estado]
        if estado
        else [
            "AC",
            "AL",
            "AP",
            "AM",
            "BA",
            "CE",
            "DF",
            "ES",
            "GO",
            "MA",
            "MT",
            "MS",
            "MG",
            "PA",
            "PB",
            "PR",
            "PE",
            "PI",
            "RJ",
            "RN",
            "RS",
            "RO",
            "RR",
            "SC",
            "SP",
            "SE",
            "TO",
        ]
    )
    scope = estado or "BRASIL"
    result_path = DATASETS_PATH / f"votacao_agregada_{scope}_{ano}.csv"
    if result_path.exists():
        return result_path

    aggregated = []
    columns = ["CD_MUNICIPIO", "NM_MUNICIPIO", "SG_UF", "NR_VOTAVEL", "QT_VOTOS"]
    for state in states:
        source = _votacao_source(ano, state)
        state_groups = []
        for chunk in pd.read_csv(
            source,
            sep=";",
            encoding="latin_1",
            usecols=columns,
            chunksize=100_000,
            low_memory=False,
        ):
            state_groups.append(
                chunk.groupby(
                    ["CD_MUNICIPIO", "NM_MUNICIPIO", "SG_UF", "NR_VOTAVEL"],
                    as_index=False,
                )["QT_VOTOS"].sum()
            )
        if state_groups:
            aggregated.append(
                pd.concat(state_groups)
                .groupby(
                    ["CD_MUNICIPIO", "NM_MUNICIPIO", "SG_UF", "NR_VOTAVEL"],
                    as_index=False,
                )["QT_VOTOS"]
                .sum()
            )

    if not aggregated:
        raise RuntimeError(f"Nenhum dado de votação encontrado para {ano}")
    pd.concat(aggregated, ignore_index=True).to_csv(result_path, index=False)
    return result_path


async def download_eleitorado_local_votacao(
    ano: int,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    overwrite=False,
):
    url = f"https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip"

    result_path = (
        DATASETS_PATH / f"eleitorado_local_votacao_{municipio}_{estado}_{ano}.csv"
    )

    if result_path.exists() and not overwrite:
        print(f"{result_path} already exists, ignoring")
        return result_path

    downloaded_zip_path = DOWNLOADS_PATH / f"eleitorado_local_votacao_{ano}.zip"
    if not downloaded_zip_path.exists():
        download(url, downloaded_zip_path)

    extracted_data_path = DOWNLOADS_PATH / f"eleitorado_local_votacao_{ano}"
    if not extracted_data_path.exists():
        extract_zip(downloaded_zip_path, extracted_data_path)

    csv_data_path = extracted_data_path / f"eleitorado_local_votacao_{ano}.csv"
    if not csv_data_path.exists():
        csv_data_path = (
            extracted_data_path / f"eleitorado_local_votacao_{ano}_{estado}.csv"
        )

    if not csv_data_path.exists():
        raise RuntimeError(f"{csv_data_path} should exist")

    filter_tse_dataset(
        csv_data_path,
        result_path,
        lambda chunk: chunk[chunk["NM_MUNICIPIO"] == municipio.upper()],
    )

    print("Done.")
    return result_path
