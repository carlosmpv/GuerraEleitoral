# Mapas da guerra eleitoral

## Features

- [ ] Extração de dados
    - [ ] Dados agregados de votação e locais de votação (https://dadosabertos.tse.jus.br/dataset/resultados-2022)
        - [ ] Download automático por ano e estado das votações
            - [ ] Extração dos municípios em diferentes planilhas para otimizar o acesso
        - [ ] Download automático por ano e estado dos locais de votação (https://dadosabertos.tse.jus.br/dataset/eleitorado-2026)
    - [ ] GeoJSON das zonas eleitorais

- [ ] Malha de bairros
    https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/bairros/shp/UF/
    **Não está completo, não há a malha de bairros para a maioria dos municípios de são paulo, por sorte temos de ribeirão preto

- [ ] Visualização
    - [ ] Mapa de calor blob
        - [ ] Filtros de busca
            - [ ] Município (Ribeirão preto apenas a princípio)
            - [ ] Ano
            - [ ] Legenda
            - [ ] Número votável
            - [ ] Calor invertido (regiões mais quentes onde há menos votos)
    - [ ] Mapa de calor por zona eleitoral
        - [ ] Filtros de busca
            - [ ] Município (Ribeirão preto apenas a princípio)
            - [ ] Ano
            - [ ] Legenda
            - [ ] Número votável
            - [ ] Calor invertido (regiões mais quentes onde há menos votos)
            - [ ] Colorir por partido mais votado
    - [ ] Listas
        - [ ] Filtros de busca
            - [ ] Município (Ribeirão preto apenas a princípio)
            - [ ] Ano
            - [ ] Legenda
            - [ ] Número votável
        - [ ] Ordenação
            - [ ] Mais votado
            - [ ] Menos votado
            - [ ] Região com mais votos de `Legenda/Nr votável`
            - [ ] Região com menos votos de `Legenda/Nr votável`
    
## MVP

- A unidade popular foi legalizada em 2019, então é relevante apenas o eleitorado de 2020 em diante
- O software será apresentado primeiramente apenas para a UP de ribeirão, não há necessidade de selecionar outros municípios
- O mais importante agora é 

## Deploy

Os mapas devem ser pré renderizados antes de subir para o github, serão servidos como um site estático