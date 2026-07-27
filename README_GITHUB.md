# Indicador Canal Vermelho

Aplicação Streamlit preparada para implantação pelo GitHub no Streamlit Community Cloud.

## Estrutura recomendada

```text
repositorio/
├── App_Canal_Vermelho.py
├── requirements.txt
├── packages.txt
├── .gitignore
├── .streamlit/
│   └── config.toml
└── data/
    └── Base OTIF.parquet
```

## Opção 1 — Base no próprio repositório

Coloque a base otimizada como `data/Base OTIF.parquet`. O aplicativo procura primeiro o Parquet e não exige seleção manual de arquivo.

## Opção 2 — Base por URL

No painel do Streamlit Community Cloud, abra **Settings > Secrets** e informe:

```toml
BASE_URL = "https://raw.githubusercontent.com/USUARIO/REPOSITORIO/BRANCH/caminho/Base%20OTIF.parquet"
```

O aplicativo prioriza `BASE_URL` quando o Secret estiver configurado.

## Publicação

1. Crie o repositório no GitHub.
2. Envie os arquivos mantendo a estrutura acima.
3. No Streamlit Community Cloud, crie um novo aplicativo.
4. Selecione o repositório, a branch e `App_Canal_Vermelho.py` como arquivo principal.
5. Configure `BASE_URL` somente se a base não estiver dentro do repositório.
6. Faça o deploy.

## Execução local

```bash
python -m pip install -r requirements.txt
python -m streamlit run App_Canal_Vermelho.py
```
