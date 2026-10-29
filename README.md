# VulcanTech Smart Metals

Projeto integrador de dados industriais: preparação dos sensores, previsão de falhas, estimativa didática de OEE, inspeção visual de solda e API REST.

## Executar localmente

Requer Python 3.10 ou superior. No PowerShell do Windows, crie um ambiente e instale as dependências antes de iniciar a API:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/criar_imagens_demo.py
.\.venv\Scripts\python.exe -m notebook notebooks/tratamento_dados.ipynb
.\.venv\Scripts\python.exe src/treinar_modelo.py
.\.venv\Scripts\python.exe -m uvicorn api:app --app-dir src --reload
```

O uso de `python -m uvicorn` garante que a API seja executada pelo mesmo Python em que as dependências foram instaladas, mesmo que `uvicorn` não esteja no `PATH`. Abra `http://127.0.0.1:8000/docs` para experimentar a API. Os endpoints `POST /inspecionar-solda` e `POST /inspecionar-termica` recebem imagens (`multipart/form-data`) e retornam métricas e uma imagem anotada. A análise térmica aceita `brilho_minimo` entre 120 e 250.

O painel de métricas pode ser iniciado em outro terminal:

```bash
python -m streamlit run src/dashboard.py
```

Ou inicie API e painel com Docker Compose:

```bash
docker compose up --build
```

Painel: `http://localhost:8501`. API: `http://localhost:8000/docs`.

## Site da dashboard

Com os dados preparados, abra outro PowerShell na pasta do projeto e sirva somente os arquivos estáticos da dashboard:

```powershell
py -m http.server 0 --bind 127.0.0.1 --directory site
```

O Python exibirá no terminal o endereço e a porta livre escolhida. Abra esse endereço diretamente (por exemplo, `http://127.0.0.1:53124/`). Isso publica apenas a pasta `site`, sem expor o restante do repositório. Os filtros, gráficos e tabelas usam `site/data/sensores_preparados.csv`, atualizado ao executar todas as células de `notebooks/tratamento_dados.ipynb`. O notebook também salva o CSV de treinamento em `saida/sensores_preparados.csv`. Para habilitar previsão e visão computacional, mantenha a API rodando na porta 8000. O painel histórico abre mesmo com a API desligada.

Na seção de visão computacional, as imagens de referência ficam somente no backend e não aparecem no painel. Ao escolher uma imagem, a análise começa automaticamente e retorna **APROVADO** ou **REPROVADO**, com os critérios que reprovaram. No cordão, a triagem verifica continuidade, largura/orientação, nitidez, perfil de bordas e candidatos circulares escuros comparados à referência. Na termografia, verifica extensão e posição da faixa HAZ, além da cobertura quente, com tolerância de 15% em relação à referência. Imagens fora do padrão ou sem sinais suficientes são reprovadas. É possível reenviar ou reanalisar a mesma imagem; ajuste o limiar térmico antes de reanalisar.

## Arquivos principais

- `notebooks/tratamento_dados.ipynb`: diagnóstico de ausências, limites físicos, Z-score por liga, interpolação por célula, janelas de 30 min/2 h, IEM e exportação dos CSVs preparados.
- `src/treinar_modelo.py`: divisão temporal 70/30, ponderação de classes, comparação Random Forest/Extra Trees, recall, matriz de confusão, importância via modelo e estimativa de OEE.
- `src/inspecao_solda.py`: nitidez, Canny, contornos, candidatos heurísticos a porosidade e segmentação HSV para imagens térmicas.
- `src/api.py`: endpoints `/prever` e `/inspecionar-solda` com schemas Pydantic.
- `src/dashboard.py`: painel simples de desempenho e inspeção.
- `relatorio_tecnico.md`: parecer sobre operação, dados e riscos.
- `imagens/`: imagens de referência fornecidas para inspeção, além de exemplos sintéticos de apoio.

## Limites de interpretação

O OEE é uma simulação, pois o arquivo não possui duração de paradas, ciclo ideal ou quantidade de peças aprovadas. A decisão de visão computacional é uma triagem heurística baseada nas referências recebidas: não certifica qualidade industrial, e a segmentação térmica não fornece temperatura em °C. Calibre e valide os critérios com imagens rotuladas e engenheiros responsáveis antes de usá-los em produção ou conectar a um CLP.
