"""Exportação de mapas estáticos para publicação no GitHub Pages."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from mapa.generator import (
    filtro_partido,
    generate_map,
    generate_map_brasil,
    generate_map_estado,
)

MAPA_PUBLIC_DIR = Path(__file__).resolve().parents[3] / "public"


def _gerar_nome_arquivo(
    tipo: str,
    ano: int,
    estado: str | None = None,
    municipio: str | None = None,
    legenda: str = "",
) -> str:
    legenda_limpa = str(legenda).replace("/", "-")
    if tipo == "brasil":
        return f"mapa-brasil-{ano}-legenda-{legenda_limpa}.html"
    elif tipo == "estado":
        return f"mapa-{estado.lower()}-{ano}-legenda-{legenda_limpa}.html"
    elif tipo == "municipio":
        muni_slug = (
            municipio.lower()
            .replace(" ", "-")
            .replace("ã", "a")
            .replace("á", "a")
            .replace("à", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )
        return f"mapa-{muni_slug}-{estado.lower()}-{ano}-legenda-{legenda_limpa}.html"
    return f"mapa-{ano}-legenda-{legenda_limpa}.html"


async def exportar_mapa_estatico(
    ano: int,
    legenda: str,
    tipo: str = "municipio",
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    escala: str = "linear",
    titulo_customizado: str | None = None,
) -> dict:
    MAPA_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    if tipo == "brasil":
        content = await generate_map_brasil(ano, filtro_partido(legenda), escala=escala, incluir_painel=False)
        nome_arquivo = _gerar_nome_arquivo("brasil", ano, legenda=legenda)
        titulo = titulo_customizado or f"Mapa do Brasil - {ano} - Legenda {legenda}"
    elif tipo == "estado":
        content = await generate_map_estado(
            ano, filtro_partido(legenda), estado=estado, escala=escala, incluir_painel=False
        )
        nome_arquivo = _gerar_nome_arquivo("estado", ano, estado=estado, legenda=legenda)
        titulo = titulo_customizado or f"Mapa {estado} - {ano} - Legenda {legenda}"
    else:
        content = await generate_map(
            ano,
            filtro_partido(legenda),
            estado=estado,
            municipio=municipio,
            escala=escala,
            incluir_painel=False,
        )
        nome_arquivo = _gerar_nome_arquivo(
            "municipio", ano, estado=estado, municipio=municipio, legenda=legenda
        )
        titulo = titulo_customizado or f"Mapa {municipio}/{estado} - {ano} - Legenda {legenda}"

    content = re.sub(r"<title>.*?</title>", f"<title>{titulo}</title>", content, count=1, flags=re.DOTALL)
    if "<title>" not in content:
        content = content.replace("<head>", f"<head>\n    <title>{titulo}</title>", 1)

    caminho = MAPA_PUBLIC_DIR / nome_arquivo
    caminho.write_text(content, encoding="utf-8")

    return {
        "arquivo": nome_arquivo,
        "caminho": str(caminho),
        "titulo": titulo,
        "url": f"./{nome_arquivo}",
    }


def gerar_index_public() -> str:
    MAPA_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    arquivos = []
    for arquivo in sorted(MAPA_PUBLIC_DIR.glob("*.html")):
        if arquivo.name == "index.html":
            continue
        nome = arquivo.name
        arquivos.append(
            {
                "nome": nome,
                "titulo": nome.replace(".html", "").replace("-", " ").title(),
                "caminho": f"./{nome}",
            }
        )

    itens_html = ""
    if not arquivos:
        itens_html = '<li class="vazio">Nenhum mapa gerado ainda. Use a interface em /exportar/estatico para gerar mapas.</li>'
    else:
        for arq in arquivos:
            itens_html += f'''                <li class="mapa-item">
                    <a href="{arq['caminho']}" target="_blank" rel="noopener">
                        <span class="mapa-nome">{arq['titulo']}</span>
                        <span class="mapa-arquivo">{arq['nome']}</span>
                    </a>
                </li>
'''

    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mapas Eleitorais - Publicação Estática</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: linear-gradient(135deg, #f4f7f8 0%, #e8eff1 100%); min-height: 100vh; }}
        header {{ background: linear-gradient(135deg, #087e8b 0%, #065a63 100%); color: white; padding: 40px 20px; text-align: center; box-shadow: 0 4px 20px rgba(8, 126, 139, 0.3); }}
        header h1 {{ margin: 0 0 10px 0; font-size: 32px; font-weight: 700; }}
        header p {{ margin: 0; opacity: 0.95; font-size: 16px; }}
        main {{ max-width: 900px; margin: 0 auto; padding: 40px 20px; }}
        .info {{ background: white; padding: 24px 28px; border-radius: 12px; margin-bottom: 32px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); border-left: 4px solid #087e8b; }}
        .info h2 {{ margin: 0 0 12px 0; font-size: 20px; color: #087e8b; }}
        .info p {{ margin: 8px 0; color: #202b35; line-height: 1.6; }}
        .mapas-section {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); }}
        .mapas-header {{ background: #f8fbfc; padding: 20px 28px; border-bottom: 2px solid #e8eff1; }}
        .mapas-header h2 {{ margin: 0; font-size: 22px; color: #202b35; }}
        .mapas-lista {{ list-style: none; margin: 0; padding: 0; }}
        .mapa-item {{ border-bottom: 1px solid #f0f4f6; transition: background 0.2s ease; }}
        .mapa-item:last-child {{ border-bottom: none; }}
        .mapa-item:hover {{ background: #f8fbfc; }}
        .mapa-item a {{ display: flex; flex-direction: column; padding: 18px 28px; text-decoration: none; color: inherit; gap: 6px; }}
        .mapa-nome {{ font-size: 16px; font-weight: 600; color: #087e8b; }}
        .mapa-arquivo {{ font-size: 13px; color: #6b7c85; font-family: 'Courier New', monospace; }}
        .vazio {{ padding: 40px 28px; text-align: center; color: #6b7c85; font-style: italic; }}
        footer {{ text-align: center; padding: 30px 20px; color: #6b7c85; font-size: 14px; }}
        .gerado-em {{ margin-top: 10px; font-size: 12px; opacity: 0.8; }}
    </style>
</head>
<body>
    <header>
        <h1>Mapas Eleitorais</h1>
        <p>Versões estáticas para publicação no GitHub Pages</p>
    </header>
    <main>
        <section class="info">
            <h2>Sobre</h2>
            <p>Estes são mapas eleitorais gerados e exportados para visualização estática. Cada mapa pode ser visualizado diretamente no navegador sem necessidade de servidor.</p>
            <p><strong>Fonte:</strong> Dados do TSE e malhas do IBGE</p>
        </section>
        <section class="mapas-section">
            <div class="mapas-header">
                <h2>Mapas Disponíveis ({len(arquivos)})</h2>
            </div>
            <ul class="mapas-lista">
{itens_html}
            </ul>
        </section>
    </main>
    <footer>
        <div>Mapas da Guerra Eleitoral</div>
        <div class="gerado-em">Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>
    </footer>
</body>
</html>
'''
    caminho_index = MAPA_PUBLIC_DIR / "index.html"
    caminho_index.write_text(html, encoding="utf-8")
    return html
