from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from mapa.export import (
    FORMATO_GEOJSON,
    FORMATO_OSM,
    FORMATO_ZIP,
    FORMATOS,
    MEDIA_TYPES,
    exportar_locais_votacao,
    exportar_votos_municipio,
)
from mapa.export.estatico import exportar_mapa_estatico, gerar_index_public
from mapa.generator import (
    filtro_partido,
    generate_map,
    generate_map_brasil,
    generate_map_estado,
)

api = FastAPI()

# [-21.179104, -47.884856]


@api.get("/ano/{ano}/estado/{estado}/municipio/{municipio}/legenda/{legenda}")
async def map(
    ano: int,
    estado: str,
    municipio: str,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
):
    content = await generate_map(
        ano,
        filtro_partido(legenda),
        estado=estado,
        municipio=municipio,
        escala=escala,
    )

    return HTMLResponse(content=content)


@api.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTMLResponse(
        content="""<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mapa eleitoral de São Paulo · Unidade Popular</title>
    <style>
        * { box-sizing: border-box; }
        html, body, main, iframe { width: 100%; height: 100%; margin: 0; border: 0; }
        body { overflow: hidden; background: #e8eff1; font: 15px/1.4 system-ui, sans-serif; color: #202b35; }
        #home-loading { position: fixed; inset: 0; z-index: 10; display: grid; place-content: center; justify-items: center; gap: 14px; background: #f4f7f8; transition: opacity 180ms ease, visibility 180ms ease; }
        #home-loading.is-hidden { visibility: hidden; opacity: 0; pointer-events: none; }
        .home-spinner { width: 30px; height: 30px; border: 3px solid #c6d5d9; border-top-color: #087e8b; border-radius: 50%; animation: spin 750ms linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <main>
        <iframe id="mapa-brasil" title="Mapa eleitoral de São Paulo, Unidade Popular" src="/ano/2026/estado/SP/legenda/80?escala=linear"></iframe>
    </main>
    <div id="home-loading" role="status" aria-live="polite">
        <span class="home-spinner" aria-hidden="true"></span>
        <span>Carregando mapa de São Paulo · Unidade Popular</span>
    </div>
    <script>
        document.getElementById('mapa-brasil').addEventListener('load', () => {
            document.getElementById('home-loading').classList.add('is-hidden');
        }, { once: true });
    </script>
</body>
</html>"""
    )


@api.get("/exportar/osm/votos-municipio")
async def exportar_osm_votos_municipio(
    ano: int = 2026,
    estado: str = "SP",
    legenda: str = "80",
    formato: Literal["osm", "geojson", "zip"] = "zip",
):
    try:
        content, filename = await exportar_votos_municipio(
            ano, estado, legenda, formato=formato
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=MEDIA_TYPES.get(formato, "application/octet-stream"), headers=headers)


@api.get("/exportar/osm/locais-votacao")
async def exportar_osm_locais_votacao(
    ano: int = 2026,
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    legenda: str = "80",
    formato: Literal["osm", "geojson", "zip"] = "zip",
):
    try:
        content, filename = await exportar_locais_votacao(
            ano, estado, municipio, legenda, formato=formato
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=MEDIA_TYPES.get(formato, "application/octet-stream"), headers=headers)


@api.get("/exportar/osm")
async def exportar_osm_guias():
    return HTMLResponse(
        content="""<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Exportar camadas para OpenStreetMap</title>
    <style>
        body{font-family:system-ui,sans-serif;margin:40px auto;max-width:820px;line-height:1.6;background:#f7fafb;color:#202b35}
        h1{font-size:28px;margin-bottom:8px}
        .sub{color:#50616b;margin-bottom:32px}
        .card{background:#fff;border-radius:12px;box-shadow:0 20px 60px #0b1f2b12;padding:28px;margin-bottom:24px}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
        label{display:flex;flex-direction:column;font-weight:600;font-size:14px;gap:6px}
        input,select{padding:10px 12px;border-radius:10px;border:1px solid #c7d4d9;font:inherit}
        .actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
        .btn{display:inline-flex;align-items:center;gap:8px;padding:11px 18px;border-radius:999px;text-decoration:none;font-weight:700}
        .btn-primary{background:#087e8b;color:#fff}
        .btn-ghost{background:transparent;color:#087e8b}
        code{background:#f1f6f7;padding:2px 6px;border-radius:6px}
    </style>
</head>
<body>
    <header>
        <h1>Exportar camadas para OpenStreetMap</h1>
        <p class="sub">Gere um arquivo .OSM ou .GEOJSON com as camadas do mapa para abrir no JOSM/iD, publicar no uMap ou compartilhar com outras pessoas.</p>
    </header>
    <section class="card">
        <h2>1) Votos por município (polígonos)</h2>
        <p>Ideal para visualizar o resultado da legenda por município no mesmo formato vetorial do seu mapa.</p>
        <div class="grid">
            <label>Ano<input id="m-ano" value="2026"></label>
            <label>Estado<input id="m-uf" value="SP"></label>
            <label>Legenda<input id="m-legenda" value="80"></label>
            <label>Formato<select id="m-formato"><option value="zip">.ZIP (OSM + GeoJSON + manifesto)</option><option value="osm">.OSM (OpenStreetMap XML)</option><option value="geojson">.GEOJSON</option></select></label>
        </div>
        <div class="actions">
            <a class="btn btn-primary" id="m-link" href="#">Baixar camada de municípios</a>
            <a class="btn btn-ghost" href="/ano/2026/estado/SP/legenda/80" target="_blank">Ver mapa atual</a>
        </div>
    </section>
    <section class="card">
        <h2>2) Locais de votação (pontos)</h2>
        <p>Exporta cada local de votação com nome, endereço, bairro, zona, seções, eleitorado e votos da legenda filtrada.</p>
        <div class="grid">
            <label>Ano<input id="l-ano" value="2026"></label>
            <label>Estado<input id="l-uf" value="SP"></label>
            <label>Município<input id="l-muni" value="Ribeirão Preto"></label>
            <label>Legenda<input id="l-legenda" value="80"></label>
            <label>Formato<select id="l-formato"><option value="zip">.ZIP (OSM + GeoJSON + manifesto)</option><option value="osm">.OSM (OpenStreetMap XML)</option><option value="geojson">.GEOJSON</option></select></label>
        </div>
        <div class="actions">
            <a class="btn btn-primary" id="l-link" href="#">Baixar camada de locais de votação</a>
        </div>
    </section>
    <section class="card">
        <h2>Exportação estática para GitHub Pages</h2>
        <p>Gere versões HTML limpas (sem formulários) para publicar na pasta <code>mapa/</code>.</p>
        <div class="actions">
            <a class="btn btn-primary" href="/exportar/estatico/gerar-index">Gerar/Atualizar index.html</a>
        </div>
    </section>
    <section class="card">
        <h2>Como usar</h2>
        <ul>
            <li><strong>JOSM/iD:</strong> abra o <code>.osm</code> — todos os objetos têm IDs negativos, por isso são tratados como novos e não alteram elementos existentes.</li>
            <li><strong>uMap (compartilhar sem alterar o OSM):</strong> importe o <code>.geojson</code> em <a href="https://umap.openstreetmap.fr">umap.openstreetmap.fr</a> e publique o mapa.</li>
            <li><strong>QGIS/ArcGIS:</strong> abra o <code>.geojson</code> diretamente.</li>
        </ul>
        <p>As tags usam o prefixo <code>eleitoral:*</code> para manter o arquivo organizado e fácil de filtrar depois.</p>
    </section>
    <script>
        function bind(id,p){
            const el=document.getElementById(id); if(!el)return;
            const update=()=>{const a=document.getElementById(p.link); if(!a)return; a.href=p.url();};
            ['change','input'].forEach(ev=>{['m-ano','m-uf','m-legenda','m-formato','l-ano','l-uf','l-muni','l-legenda','l-formato'].forEach(k=>{const x=document.getElementById(k); if(x&&p.keys.includes(k)){x.addEventListener(ev,update);}});});
            update();
        }
        bind('m-link',{keys:['m-ano','m-uf','m-legenda','m-formato'], link:'m-link', url:()=>`/exportar/osm/votos-municipio?ano=${document.getElementById('m-ano').value}&estado=${encodeURIComponent(document.getElementById('m-uf').value)}&legenda=${encodeURIComponent(document.getElementById('m-legenda').value)}&formato=${document.getElementById('m-formato').value}`});
        bind('l-link',{keys:['l-ano','l-uf','l-muni','l-legenda','l-formato'], link:'l-link', url:()=>`/exportar/osm/locais-votacao?ano=${document.getElementById('l-ano').value}&estado=${encodeURIComponent(document.getElementById('l-uf').value)}&municipio=${encodeURIComponent(document.getElementById('l-muni').value)}&legenda=${encodeURIComponent(document.getElementById('l-legenda').value)}&formato=${document.getElementById('l-formato').value}`});
    </script>
</body>
</html>"""
    )


@api.get("/exportar/estatico")
async def exportar_estatico_gui():
    return HTMLResponse(
        content="""<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Exportar mapas estáticos para GitHub Pages</title>
    <style>
        body{font-family:system-ui,sans-serif;margin:40px auto;max-width:900px;line-height:1.6;background:#f7fafb;color:#202b35}
        h1{font-size:28px;margin-bottom:8px}
        .sub{color:#50616b;margin-bottom:32px}
        .card{background:#fff;border-radius:12px;box-shadow:0 20px 60px #0b1f2b12;padding:28px;margin-bottom:24px}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
        label{display:flex;flex-direction:column;font-weight:600;font-size:14px;gap:6px}
        input,select{padding:10px 12px;border-radius:10px;border:1px solid #c7d4d9;font:inherit}
        .actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
        .btn{display:inline-flex;align-items:center;gap:8px;padding:11px 18px;border-radius:999px;text-decoration:none;font-weight:700}
        .btn-primary{background:#087e8b;color:#fff}
        .btn-ghost{background:transparent;color:#087e8b}
        .btn-secondary{background:#f1f6f7;color:#087e8b;border:1px solid #c7d4d9}
        .note{background:#f8fbfc;padding:16px;border-radius:8px;margin-top:16px;border-left:3px solid #087e8b}
        code{background:#f1f6f7;padding:2px 6px;border-radius:6px}
    </style>
</head>
<body>
    <header>
        <h1>Exportar mapas estáticos</h1>
        <p class="sub">Gera arquivos HTML limpos em <code>mapa/</code> para publicação direta no GitHub Pages.</p>
    </header>
    <section class="card">
        <h2>1) Mapa Municipal (Ribeirão Preto)</h2>
        <p>Mapa com heatmap e pontos dos locais de votação. Sem painel de filtros.</p>
        <div class="grid">
            <label>Ano<input id="m-ano" value="2026"></label>
            <label>Estado<input id="m-uf" value="SP"></label>
            <label>Município<input id="m-muni" value="Ribeirão Preto"></label>
            <label>Legenda<input id="m-leg" value="80"></label>
            <label>Escala<select id="m-esc"><option value="linear">Linear</option><option value="quantil">Quantil</option><option value="log">Log</option></select></label>
        </div>
        <div class="actions">
            <button class="btn btn-primary" onclick="exportar('municipio')">Publicar</button>
            <a class="btn btn-ghost" href="/exportar/estatico/gerar-index">Gerar/Atualizar index.html</a>
            <a class="btn btn-ghost" href="/index.html" target="_blank">Ver index</a>
        </div>
        <div id="m-status" class="note" style="display:none"></div>
    </section>
    <section class="card">
        <h2>2) Mapa por Estado</h2>
        <p>Mapa coroplético por município. Sem painel de filtros.</p>
        <div class="grid">
            <label>Ano<input id="e-ano" value="2026"></label>
            <label>Estado<input id="e-uf" value="SP"></label>
            <label>Legenda<input id="e-leg" value="80"></label>
            <label>Escala<select id="e-esc"><option value="linear">Linear</option><option value="quantil">Quantil</option><option value="log">Log</option></select></label>
        </div>
        <div class="actions">
            <button class="btn btn-primary" onclick="exportar('estado')">Publicar</button>
        </div>
        <div id="e-status" class="note" style="display:none"></div>
    </section>
    <section class="card">
        <h2>3) Mapa do Brasil</h2>
        <p>Mapa coroplético por estado/município. Sem painel de filtros.</p>
        <div class="grid">
            <label>Ano<input id="b-ano" value="2026"></label>
            <label>Legenda<input id="b-leg" value="80"></label>
            <label>Escala<select id="b-esc"><option value="linear">Linear</option><option value="quantil">Quantil</option><option value="log">Log</option></select></label>
        </div>
        <div class="actions">
            <button class="btn btn-primary" onclick="exportar('brasil')">Publicar</button>
        </div>
        <div id="b-status" class="note" style="display:none"></div>
    </section>
    <section class="card">
        <h2>Instruções</h2>
        <ol>
            <li>Exporte os mapas que deseja publicar usando os botões acima.</li>
            <li>Clique em "Gerar/Atualizar index.html" para criar a lista com todos os mapas em <code>mapa/</code>.</li>
            <li>Suba a pasta <code>mapa/</code> inteira no seu repositório do GitHub e ative o GitHub Pages apontando para ela.</li>
        </ol>
        <p>Os arquivos gerados não possuem formulário, filtros ou botões interativos - apenas o mapa visual.</p>
    </section>
    <script>
        async function exportar(tipo){
            let url='', statusId='';
            if(tipo==='municipio'){
                const ano=document.getElementById('m-ano').value;
                const estado=document.getElementById('m-uf').value;
                const municipio=document.getElementById('m-muni').value;
                const legenda=document.getElementById('m-leg').value;
                const escala=document.getElementById('m-esc').value;
                url=`/exportar/estatico/gerar?ano=${ano}&tipo=municipio&estado=${encodeURIComponent(estado)}&municipio=${encodeURIComponent(municipio)}&legenda=${encodeURIComponent(legenda)}&escala=${escala}`;
                statusId='m-status';
            }else if(tipo==='estado'){
                const ano=document.getElementById('e-ano').value;
                const estado=document.getElementById('e-uf').value;
                const legenda=document.getElementById('e-leg').value;
                const escala=document.getElementById('e-esc').value;
                url=`/exportar/estatico/gerar?ano=${ano}&tipo=estado&estado=${encodeURIComponent(estado)}&legenda=${encodeURIComponent(legenda)}&escala=${escala}`;
                statusId='e-status';
            }else if(tipo==='brasil'){
                const ano=document.getElementById('b-ano').value;
                const legenda=document.getElementById('b-leg').value;
                const escala=document.getElementById('b-esc').value;
                url=`/exportar/estatico/gerar?ano=${ano}&tipo=brasil&legenda=${encodeURIComponent(legenda)}&escala=${escala}`;
                statusId='b-status';
            }
            const status=document.getElementById(statusId);
            status.style.display='block';
            status.textContent='Gerando mapa... Isso pode levar alguns minutos.';
            try{
                const resp=await fetch(url);
                const data=await resp.json();
                if(resp.ok){
                    status.innerHTML=`✅ <strong>${data.titulo}</strong><br>Arquivo: <code>${data.arquivo}</code><br><a href="./${data.arquivo}" target="_blank">Visualizar</a>`;
                }else{
                    status.textContent='❌ Erro: '+(data.detail||'Desconhecido');
                }
            }catch(e){
                status.textContent='❌ Erro: '+e;
            }
        }
    </script>
</body>
</html>"""
    )


@api.get("/exportar/estatico/gerar")
async def exportar_estatico_gerar(
    ano: int = 2026,
    tipo: Literal["brasil", "estado", "municipio"] = "municipio",
    estado: str = "SP",
    municipio: str = "Ribeirão Preto",
    legenda: str = "80",
    escala: Literal["linear", "quantil", "log"] = "linear",
    titulo: str | None = None,
):
    try:
        resultado = await exportar_mapa_estatico(
            ano=ano,
            legenda=legenda,
            tipo=tipo,
            estado=estado,
            municipio=municipio,
            escala=escala,
            titulo_customizado=titulo,
        )
        return resultado
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.get("/exportar/estatico/gerar-index")
async def exportar_estatico_index():
    try:
        html = gerar_index_public()
        return HTMLResponse(content=html)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@api.get("/ano/{ano}/brasil/legenda/{legenda}")
async def map_brasil(
    ano: int,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
) -> HTMLResponse:
    content = await generate_map_brasil(ano, filtro_partido(legenda), escala=escala)
    return HTMLResponse(content=content)


@api.get("/ano/{ano}/estado/{estado}/legenda/{legenda}")
async def map_estado(
    ano: int,
    estado: str,
    legenda: str,
    escala: Literal["linear", "quantil", "log"] = "linear",
) -> HTMLResponse:
    content = await generate_map_estado(
        ano, filtro_partido(legenda), estado=estado, escala=escala
    )
    return HTMLResponse(content=content)


def main() -> None:
    uvicorn.run(api, host="0.0.0.0", port=8000)
