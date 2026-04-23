# Dashboard Imobiliário Brasil

Dashboard interativo para analisar valorização imobiliária no Brasil, comparar cidades e bairros e separar crescimento nominal de crescimento real ajustado pela inflação.

## Stack

- Python
- Streamlit
- Plotly
- Pandas
- API SGS do Banco Central do Brasil

## Estrutura

- `app.py`: aplicação principal
- `dashboard/config.py`: caminhos, paleta e constantes
- `dashboard/data.py`: carga de Excel, APIs e transformações
- `dashboard/charts.py`: gráficos Plotly
- `dashboard/ui.py`: tema e componentes visuais
- `dados/`: arquivos locais usados pelo dashboard

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Fontes

- Banco Central do Brasil, SGS:
  - `433`: IPCA
  - `21340`: IVG-R
  - `25419`: MVG-R
- ABECIP:
  - `igmi-r-serie-historica-fevereiro2026.xlsx`
- FipeZap:
  - `fipezap-serieshistoricas.xlsx`
  - `fipezap_por_estado.xlsx`

## Premissas atuais

- O ajuste real usa o IPCA acumulado até a última referência disponível da série.
- O gráfico secundário de comparações rebaseia todas as séries para `100` no início do período selecionado.
- A aba de bairros usa a base longa disponível em `fipezap_por_estado.xlsx`, que hoje cobre 12 cidades.
