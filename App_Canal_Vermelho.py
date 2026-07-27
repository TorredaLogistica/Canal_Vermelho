import io
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Canal Vermelho | OTIF", page_icon="🔴", layout="wide")

RED = "#E00000"
GREEN = "#00AE3D"
BLUE = "#168CF4"
DARK_BLUE = "#1827A8"
ORANGE = "#F06A35"
BLACK = "#111827"
GRID = "#E9EDF3"

st.markdown("""
<style>
.block-container{padding-top:.8rem;padding-bottom:2rem;max-width:1850px}
[data-testid="stSidebar"]{background:#F7F8FB;border-right:1px solid #E3E7EE}
.title{font-size:2rem;font-weight:850;color:#172033;margin:0}
.subtitle{color:#667085;margin:.15rem 0 1rem}
.kpi{background:#FFF;border:1px solid #D9DEE7;border-radius:22px;min-height:128px;padding:15px;
box-shadow:0 5px 10px rgba(16,24,40,.13);display:flex;flex-direction:column;justify-content:center;text-align:center}
.kpi-title{font-size:.83rem;font-weight:800;color:#606775;min-height:35px;display:flex;align-items:center;justify-content:center}
.kpi-value{font-size:2.15rem;font-weight:850;line-height:1.1;margin-top:5px}
.kpi-help{font-size:.72rem;color:#98A2B3;margin-top:6px}
.section-title{font-size:1rem;font-weight:850;margin:0 0 .4rem;color:#263247}
.panel{background:#FFF;border:1px solid #222;border-radius:24px;padding:14px 16px 9px;margin-bottom:12px}
div[data-testid="stPlotlyChart"]{background:#FFF;border:0!important;border-radius:0;padding:0!important;margin:0!important}
[data-testid="stVerticalBlockBorderWrapper"]{border:1px solid #D0D5DD!important;border-radius:22px!important;background:#FFF!important;padding:14px 16px 12px!important;margin-bottom:38px!important;overflow:visible!important}
[data-testid="stHorizontalBlock"]{gap:2.25rem!important}
[data-testid="stDataFrame"]{margin-bottom:30px!important}
.chart-section-gap{height:34px;clear:both}
.chart-section-gap-lg{height:52px;clear:both}
.daily-heading{margin:16px 0 24px!important;padding-top:10px!important;clear:both}
[data-testid="stDataFrame"]{border:1px solid #D7DCE5;border-radius:10px;overflow:hidden}

.section-spacer{height:28px;clear:both}
.section-spacer-lg{height:52px;clear:both}
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]{margin-bottom:8px}
[data-testid="stDataFrame"]{margin-bottom:24px}
</style>
""", unsafe_allow_html=True)


def normalize(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value.strip()).lower()


def br_int(value):
    return f"{int(round(value)):,.0f}".replace(",", ".")


def br_dec(value, decimals=2):
    if pd.isna(value):
        return "-"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def br_pct(value):
    return f"{value * 100:.2f}%".replace(".", ",")


def kpi(title, value, color, help_text=""):
    st.markdown(
        f'<div class="kpi"><div class="kpi-title">{title}</div>'
        f'<div class="kpi-value" style="color:{color}">{value}</div>'
        f'<div class="kpi-help">{help_text}</div></div>',
        unsafe_allow_html=True,
    )


def parse_excel_date(series):
    """Converte datas reais, textos e números seriais vindos do XLSB."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    # Preserva objetos que já sejam datas/datetimes antes de testar números.
    object_date_mask = series.map(
        lambda value: isinstance(value, (pd.Timestamp, date)) and not pd.isna(value)
    )
    if object_date_mask.any():
        result.loc[object_date_mask] = pd.to_datetime(
            series.loc[object_date_mask], errors="coerce"
        )

    remaining = ~object_date_mask
    numeric = pd.to_numeric(series.where(remaining), errors="coerce")
    # Faixa plausível de números seriais do Excel, evitando interpretar outros códigos como data.
    numeric_mask = numeric.between(1, 100000, inclusive="both")
    if numeric_mask.any():
        result.loc[numeric_mask] = pd.to_datetime(
            numeric.loc[numeric_mask], unit="D", origin="1899-12-30", errors="coerce"
        )

    text_mask = remaining & ~numeric_mask & series.notna()
    if text_mask.any():
        result.loc[text_mask] = pd.to_datetime(
            series.loc[text_mask], errors="coerce", dayfirst=True
        )
    return result


def prepare_data(df):
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    for col in [c for c in df.columns if c.startswith("Data ") or c == "Mes Referencia"]:
        df[col] = parse_excel_date(df[col])
    for col in [c for c in df.columns if c.startswith("Dias ")]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Pedido" in df.columns:
        df["Pedido"] = df["Pedido"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        df.loc[df["Pedido"].isin(["", "nan", "None", "<NA>"]), "Pedido"] = pd.NA

    raw_cv = df.get("Canal Vermelho", pd.Series(index=df.index, dtype="object")).map(normalize)
    df["CV"] = np.where(raw_cv.isin(["sim", "s", "yes", "1", "true"]), "Sim", "Não")

    if "Data Pedido" not in df.columns:
        raise ValueError("A coluna obrigatória 'Data Pedido' não foi encontrada na base XLSB.")
    df["Referencia"] = parse_excel_date(df["Data Pedido"])
    df = df[df["Referencia"].notna()].copy()
    df["MesRef"] = df["Referencia"].dt.to_period("M")
    df["Dia"] = df["Referencia"].dt.day
    return df


CACHE_VERSION = "v7_net_layout_fast"

REQUIRED_COLUMNS = [
    "Data Pedido", "Pedido", "Canal Vermelho",
    "Transportadora", "Empresa Padrao", "CD Origem",
    "Dias Realizado Faturamento", "Dias Realizado Expedicao",
    "Dias Aguard. Protocolo", "Dias Aguard.Romaneio", "Dias Aguard. Coleta",
    "Dias Realizado Entrega", "Dias Realizado Total",
]


@st.cache_resource(show_spinner=False, max_entries=2)
def load_base(xlsb_path_text):
    """Prioriza Base OTIF.parquet; XLSB é fallback apenas para gerar o Parquet."""
    xlsb_path = Path(xlsb_path_text)
    parquet_path = xlsb_path.with_suffix(".parquet")
    cache_path = xlsb_path.with_name(f"{xlsb_path.stem}_cache.parquet")

    # 1) Parquet oficial previamente gerado: abertura em poucos segundos.
    if parquet_path.exists():
        return pd.read_parquet(parquet_path, engine="pyarrow"), "Parquet rápido"

    # 2) Cache local de uma execução anterior.
    if cache_path.exists() and cache_path.stat().st_mtime >= xlsb_path.stat().st_mtime:
        cached = pd.read_parquet(cache_path, engine="pyarrow")
        if {"Pedido", "CV", "Referencia", "MesRef", "Dia"}.issubset(cached.columns):
            return cached, "Cache Parquet"

    # 3) Primeira conversão. XLSB é lento por natureza; ocorre somente uma vez.
    raw = pd.read_excel(
        xlsb_path, sheet_name=0, engine="pyxlsb",
        usecols=lambda column: str(column).strip() in REQUIRED_COLUMNS,
    )
    prepared = prepare_data(raw)
    temp = cache_path.with_suffix(".tmp.parquet")
    prepared.to_parquet(temp, engine="pyarrow", index=False, compression="snappy")
    temp.replace(cache_path)
    return prepared, "XLSB convertido para cache"


def unique_sorted(df, column):
    if column not in df.columns:
        return []
    return sorted([v for v in df[column].dropna().unique().tolist() if str(v).strip()], key=str)


def filter_values(df, column, values):
    if values and column in df.columns:
        return df[df[column].isin(values)]
    return df


def count_orders(df):
    if "Pedido" in df.columns:
        return int(df["Pedido"].nunique(dropna=True))
    return int(len(df))


def period_label(period):
    return f"{period.month:02d}/{period.year}"


def month_name(period):
    names = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return names[period.month - 1]


def avg_or_nan(df, column):
    return df[column].mean() if column in df.columns else np.nan


def ranking_summary(base, dimension):
    """Ranking decrescente do percentual de pedidos distintos em Canal Vermelho."""
    rows = []
    if dimension not in base.columns:
        return pd.DataFrame(
            columns=[dimension, "Total Pedidos", "Com Canal Vermelho", "% Canal Vermelho"]
        )
    for value, group in base.groupby(dimension, dropna=False):
        total = count_orders(group)
        with_red = count_orders(group[group["CV"] == "Sim"])
        rows.append({
            dimension: "Não informado" if pd.isna(value) else value,
            "Total Pedidos": total,
            "Com Canal Vermelho": with_red,
            "% Canal Vermelho": with_red / total if total else 0,
        })
    return pd.DataFrame(rows).sort_values(
        ["% Canal Vermelho", "Com Canal Vermelho"],
        ascending=[False, False],
    ).reset_index(drop=True)


def current_month_table(df, cv_value):
    part = df[df["CV"] == cv_value]
    rows = []
    for cd, group in part.groupby("CD Origem", dropna=False):
        rows.append({
            "CD Origem": "Não informado" if pd.isna(cd) else cd,
            "Qtde Pedidos": count_orders(group),
            "Faturamento": avg_or_nan(group, "Dias Realizado Faturamento"),
            "Protocolo": avg_or_nan(group, "Dias Aguard. Protocolo"),
            "Romaneio": avg_or_nan(group, "Dias Aguard.Romaneio"),
            "Coleta": avg_or_nan(group, "Dias Aguard. Coleta"),
            "Entrega": avg_or_nan(group, "Dias Realizado Entrega"),
            "Total": avg_or_nan(group, "Dias Realizado Total"),
        })
    result = pd.DataFrame(rows)
    total = pd.DataFrame([{
        "CD Origem": "TOTAL",
        "Qtde Pedidos": count_orders(part),
        "Faturamento": avg_or_nan(part, "Dias Realizado Faturamento"),
        "Protocolo": avg_or_nan(part, "Dias Aguard. Protocolo"),
        "Romaneio": avg_or_nan(part, "Dias Aguard.Romaneio"),
        "Coleta": avg_or_nan(part, "Dias Aguard. Coleta"),
        "Entrega": avg_or_nan(part, "Dias Realizado Entrega"),
        "Total": avg_or_nan(part, "Dias Realizado Total"),
    }])
    if result.empty:
        result = total
    else:
        result = pd.concat([result.sort_values("CD Origem"), total], ignore_index=True)
    return result


def style_table(df, title, color):
    display = df.copy()
    for col in ["Faturamento", "Protocolo", "Romaneio", "Coleta", "Entrega", "Total"]:
        display[col] = display[col].map(lambda x: br_dec(x, 2))
    display["Qtde Pedidos"] = display["Qtde Pedidos"].map(br_int)

    def highlight_total(row):
        if str(row["CD Origem"]).strip().upper() == "TOTAL":
            return [
                "background-color:#FFF1F2;color:#9F1239;font-weight:800;"
                "border-top:2px solid #E00000;border-bottom:2px solid #E00000"
            ] * len(row)
        return [""] * len(row)

    styled = display.style.apply(highlight_total, axis=1)
    st.markdown(
        f'<div class="section-title" style="color:{color};font-size:1.08rem;margin:10px 0 12px">{title}</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(500, 88 + len(display) * 35),
        column_config={
            "CD Origem": st.column_config.TextColumn("CD Origem", width="medium"),
            "Qtde Pedidos": st.column_config.TextColumn("Qtde Pedidos", width="small"),
            "Faturamento": st.column_config.TextColumn("Faturamento", width="small"),
            "Protocolo": st.column_config.TextColumn("Protocolo", width="small"),
            "Romaneio": st.column_config.TextColumn("Romaneio", width="small"),
            "Coleta": st.column_config.TextColumn("Coleta", width="small"),
            "Entrega": st.column_config.TextColumn("Entrega", width="small"),
            "Total": st.column_config.TextColumn("Total", width="small"),
        },
    )


st.markdown('<p class="title">🔴 Indicador Canal Vermelho</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Acompanhamento mensal de pedidos, tempos operacionais e evolução dos últimos seis meses</p>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Base de dados")
    # Leitura automática: não existe seleção manual de arquivo.
    candidates = [
        Path("Base OTIF.xlsb"),
        Path("data/Base OTIF.xlsb"),
        Path(__file__).resolve().parent / "Base OTIF.xlsb",
        Path(__file__).resolve().parent / "data" / "Base OTIF.xlsb",
    ]
    base_path = next((candidate for candidate in candidates if candidate.exists()), None)
    if base_path is None:
        st.error("Base OTIF.xlsb não encontrada. Coloque o arquivo na mesma pasta do App ou na pasta data.")
        st.stop()
    try:
        with st.spinner("Abrindo base otimizada..."):
            df, load_mode = load_base(str(base_path.resolve()))
    except Exception as exc:
        st.error(f"Não foi possível ler a base: {exc}")
        st.stop()

    st.caption(f"Fonte: {base_path.name} • {br_int(len(df))} linhas • {load_mode}")
    st.divider()
    st.markdown("### Visualização")
    visualization = st.radio(
        "Modo de visualização",
        ["📊 Visão Diária", "📈 Evolução Mensal"],
        index=0,
        label_visibility="collapsed",
    )
    accumulated_months = 6
    if visualization == "📈 Evolução Mensal":
        accumulated_months = st.radio(
            "Período acumulado (meses)",
            [3, 6, 9, 12],
            index=1,
            horizontal=True,
        )

    st.divider()
    st.markdown("### Filtros")

    periods = sorted(df["MesRef"].dropna().unique().tolist())
    current_period = pd.Period(date.today(), freq="M")
    default_period = current_period if current_period in periods else periods[-1]
    if current_period not in periods:
        st.caption(f"O mês atual {period_label(current_period)} não existe na base. Foi selecionado o último mês disponível.")
    labels = [period_label(p) for p in periods]
    selected_label = st.selectbox(
        "Mês/Ano Referência",
        labels,
        index=periods.index(default_period),
    )
    selected_period = periods[labels.index(selected_label)]

    # As listas são encadeadas para mostrar somente opções válidas do mês selecionado.
    option_base = df[df["MesRef"] == selected_period]
    selected_transporters = st.multiselect("Transportadora", unique_sorted(option_base, "Transportadora"), placeholder="Todas")
    option_company = filter_values(option_base, "Transportadora", selected_transporters)
    company_options = unique_sorted(option_company, "Empresa Padrao")
    default_company = [value for value in company_options if normalize(value) == "net"]
    selected_companies = st.multiselect(
        "Empresa Padrão", company_options, default=default_company, placeholder="Todas"
    )
    option_cd = filter_values(option_company, "Empresa Padrao", selected_companies)
    selected_cds = st.multiselect("CD Origem", unique_sorted(option_cd, "CD Origem"), placeholder="Todos")

# Transportadora, Empresa Padrão e CD Origem afetam o mês escolhido e a janela histórica.
filtered_all = filter_values(df, "Transportadora", selected_transporters)
filtered_all = filter_values(filtered_all, "Empresa Padrao", selected_companies)
filtered_all = filter_values(filtered_all, "CD Origem", selected_cds)
if visualization == "📊 Visão Diária":
    current = filtered_all[filtered_all["MesRef"] == selected_period].copy()

    if current.empty:
        st.warning("Nenhum registro encontrado para a combinação de filtros selecionada.")
        st.stop()

    # Últimos seis meses terminando no mês selecionado, mesmo quando algum mês não possui registros.
    last_6_periods = pd.period_range(end=selected_period, periods=6, freq="M")
    history = filtered_all[filtered_all["MesRef"].isin(last_6_periods)].copy()

    n_total = count_orders(current)
    current_red = current[current["CV"] == "Sim"].copy()
    n_red = count_orders(current_red)
    n_green = max(0, n_total - n_red)
    pct_red = n_red / n_total if n_total else 0
    pct_green = n_green / n_total if n_total else 0
    active_red_days = int(current_red.loc[current_red["Pedido"].notna(), "Dia"].nunique())
    elapsed_days_current = max(1, active_red_days)
    avg_red = n_red / elapsed_days_current

    st.markdown(f"### Referência selecionada: {period_label(selected_period)}")

    # CARDS: sempre correspondem ao mês selecionado.
    k1, k2, k3, k4 = st.columns([1, 1, 1, 1])
    with k1:
        kpi("Canal Vermelho (%)", br_pct(pct_red), RED, f"{br_int(n_red)} pedidos no mês")
    with k2:
        kpi("Sem Canal Vermelho (%)", br_pct(pct_green), GREEN, f"{br_int(n_green)} pedidos no mês")
    with k3:
        kpi("Média Diária Canal Vermelho", br_int(avg_red), RED, f"{br_int(n_red)} pedidos / {elapsed_days_current} dias")
    with k4:
        kpi("Total Mês de Canal Vermelho", br_int(n_red), RED, period_label(selected_period))

    st.markdown('<div class="section-spacer"></div>', unsafe_allow_html=True)

    # PRINT 1: tabelas em largura total para eliminar a rolagem horizontal.
    style_table(current_month_table(current, "Sim"), "COM CANAL VERMELHO", RED)
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    style_table(current_month_table(current, "Não"), "SEM CANAL VERMELHO", GREEN)
    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)

    # Base mensal completa para os três gráficos históricos.
    monthly_rows = []
    for period in last_6_periods:
        month_data = history[history["MesRef"] == period]
        for cv_value in ["Sim", "Não"]:
            part = month_data[month_data["CV"] == cv_value]
            monthly_rows.append({
                "MesRef": period,
                "Mês": month_name(period),
                "CV": cv_value,
                "Pedidos": count_orders(part),
                "Faturamento": avg_or_nan(part, "Dias Realizado Faturamento"),
                "Expedição": avg_or_nan(part, "Dias Realizado Expedicao") if "Dias Realizado Expedicao" in part.columns else (
                    np.nansum([avg_or_nan(part, "Dias Aguard. Protocolo"), avg_or_nan(part, "Dias Aguard.Romaneio"), avg_or_nan(part, "Dias Aguard. Coleta")])
                    if not part.empty else np.nan
                ),
                "Entrega": avg_or_nan(part, "Dias Realizado Entrega"),
                "Total": avg_or_nan(part, "Dias Realizado Total"),
            })
    monthly = pd.DataFrame(monthly_rows)


    def historical_combo(cv_value, title):
        plot = monthly[monthly["CV"] == cv_value]
        x = [month_name(p) for p in last_6_periods]
        fig = go.Figure()
        fig.add_bar(x=x, y=plot["Faturamento"], name="Faturamento", marker_color=BLUE,
                    text=plot["Faturamento"].map(lambda v: "" if pd.isna(v) else br_dec(v, 2)), textposition="inside")
        fig.add_bar(x=x, y=plot["Expedição"], name="Expedição", marker_color=DARK_BLUE,
                    text=plot["Expedição"].map(lambda v: "" if pd.isna(v) else br_dec(v, 2)), textposition="inside")
        fig.add_bar(x=x, y=plot["Entrega"], name="Entrega", marker_color=ORANGE,
                    text=plot["Entrega"].map(lambda v: "" if pd.isna(v) else br_dec(v, 2)), textposition="inside")
        fig.add_scatter(
            x=x, y=plot["Pedidos"], name="Qtde Pedidos", mode="lines+markers", yaxis="y2",
            line=dict(color=BLACK, width=5, dash="dot"),
            marker=dict(size=13, color=BLACK, line=dict(color="white", width=2)),
            cliponaxis=False,
        )
        for month, volume in zip(x, plot["Pedidos"]):
            fig.add_annotation(
                x=month, y=volume, yref="y2", text=f"<b>{br_int(volume)}</b>",
                showarrow=False, yshift=24, bgcolor="#111827", bordercolor="white",
                borderwidth=1.5, borderpad=5, font=dict(size=13, color="white"),
            )
        fig.update_layout(
            title=dict(text=title, x=0.02, y=0.98, font=dict(size=18, color="#172033")),
            barmode="stack", height=485, margin=dict(l=48, r=72, t=120, b=68),
            paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Arial", color="#525866"),
            legend=dict(orientation="h", y=1.11, x=0, yanchor="bottom"),
            yaxis=dict(title="Média de dias", gridcolor=GRID),
            yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False, rangemode="tozero"),
            xaxis=dict(title=f"Últimos 6 meses até {period_label(selected_period)}"),
            hovermode="x unified",
        )
        return fig

    # PRINT 2: esquerda Sem Canal Vermelho e direita Com Canal Vermelho.
    g1, g2 = st.columns(2, gap="large")
    with g1:
        with st.container(border=True):
            st.plotly_chart(historical_combo("Não", "SEM CANAL VERMELHO — últimos 6 meses"), use_container_width=True)
    with g2:
        with st.container(border=True):
            st.plotly_chart(historical_combo("Sim", "COM CANAL VERMELHO — últimos 6 meses"), use_container_width=True)
    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)

    # Barras horizontais percentuais dos últimos seis meses.
    percent_rows = []
    for period in last_6_periods:
        month_data = history[history["MesRef"] == period]
        total = count_orders(month_data)
        red_count = count_orders(month_data[month_data["CV"] == "Sim"])
        red_pct = red_count / total if total else 0
        percent_rows.append({"Mês": month_name(period), "Sim": red_pct, "Não": 1 - red_pct if total else 0})
    percent = pd.DataFrame(percent_rows)
    fig_pct = go.Figure()
    fig_pct.add_bar(y=percent["Mês"], x=percent["Sim"], name="Com Canal Vermelho", orientation="h", marker_color=DARK_BLUE,
                    text=percent["Sim"].map(lambda v: br_pct(v) if v > 0 else ""), textposition="inside")
    fig_pct.add_bar(y=percent["Mês"], x=percent["Não"], name="Sem Canal Vermelho", orientation="h", marker_color=BLUE,
                    text=percent["Não"].map(lambda v: br_pct(v) if v > 0 else ""), textposition="inside")
    fig_pct.update_layout(
        title="Percentual mensal — Com e Sem Canal Vermelho", barmode="stack", height=430,
        margin=dict(l=30, r=25, t=75, b=30), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Arial", color="#525866"), legend=dict(orientation="h", y=1.12, x=0),
        xaxis=dict(tickformat=".0%", range=[0, 1], title=None, gridcolor=GRID), yaxis=dict(title=None, autorange="reversed"),
        hovermode="y unified",
    )
    with st.container(border=True):
        st.plotly_chart(fig_pct, use_container_width=True)
    st.markdown('<div class="chart-section-gap-lg"></div>', unsafe_allow_html=True)
    st.markdown(f'<h3 class="daily-heading">Medição diária — {period_label(selected_period)}</h3>', unsafe_allow_html=True)

    # PRINT 3: somente dias que possuem volume.
    if "Pedido" in current.columns:
        daily = current.groupby(["Dia", "CV"])["Pedido"].nunique().unstack(fill_value=0)
    else:
        daily = current.groupby(["Dia", "CV"]).size().unstack(fill_value=0)
    if "Sim" not in daily.columns:
        daily["Sim"] = 0
    if "Não" not in daily.columns:
        daily["Não"] = 0
    daily["Total"] = daily["Sim"] + daily["Não"]
    daily = daily[daily["Total"] > 0].sort_index()

    red_daily = daily.loc[daily["Sim"] > 0, "Sim"]
    red_days = red_daily.index.astype(int).tolist()
    volume_days = daily.index.astype(int).tolist()
    elapsed_days = max(1, len(red_days))
    avg_daily_red = red_daily.sum() / elapsed_days

    fig_red = go.Figure()
    fig_red.add_bar(x=red_days, y=red_daily.values, name="Canal Vermelho", marker_color=RED,
                    text=red_daily.map(br_int).tolist(), textposition="outside")
    fig_red.add_scatter(
        x=red_days, y=[avg_daily_red] * len(red_days),
        name=f"Média diária: {br_int(avg_daily_red)}", mode="lines+markers",
        line=dict(color=BLACK, width=5, dash="dot"), marker=dict(size=8, color=BLACK),
    )
    fig_red.update_layout(
        title=dict(text="Canal Vermelho por dia + média diária", x=0.02, y=0.98),
        height=515, margin=dict(l=48, r=38, t=112, b=65),
        paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Arial", color="#525866"),
        legend=dict(orientation="h", y=1.10, x=0, yanchor="bottom"),
        xaxis=dict(title="Dias com Canal Vermelho", type="category"),
        yaxis=dict(title="Pedidos", gridcolor=GRID, rangemode="tozero"), hovermode="x unified",
    )

    # Direita: volumes Sim e Não empilhados, com total no topo de cada dia.
    fig_volume = go.Figure()
    fig_volume.add_bar(x=volume_days, y=daily["Não"].values, name="Sem Canal Vermelho", marker_color=GREEN,
                       text=daily["Não"].map(lambda v: br_int(v) if v > 0 else "").tolist(), textposition="inside")
    fig_volume.add_bar(x=volume_days, y=daily["Sim"].values, name="Com Canal Vermelho", marker_color=RED,
                       text=daily["Sim"].map(lambda v: br_int(v) if v > 0 else "").tolist(), textposition="inside")
    fig_volume.add_scatter(x=volume_days, y=daily["Total"].values, name="Volume total", mode="text",
                           text=daily["Total"].map(br_int).tolist(), textposition="top center",
                           textfont=dict(color="#4B5563", size=12), hoverinfo="skip")
    fig_volume.update_layout(
        title=dict(text="Volume diário — Com x Sem Canal Vermelho", x=0.02, y=0.98),
        barmode="stack", height=515, margin=dict(l=48, r=38, t=112, b=65),
        paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Arial", color="#525866"),
        legend=dict(orientation="h", y=1.10, x=0, yanchor="bottom"),
        xaxis=dict(title="Dias com volume", type="category"), yaxis=dict(title="Pedidos", gridcolor=GRID, rangemode="tozero"),
        hovermode="x unified",
    )

    d1, d2 = st.columns(2, gap="large")
    with d1:
        with st.container(border=True):
            st.plotly_chart(fig_red, use_container_width=True)
    with d2:
        with st.container(border=True):
            st.plotly_chart(fig_volume, use_container_width=True)
    st.markdown('<div class="chart-section-gap-lg"></div>', unsafe_allow_html=True)

    # Rankings do mês selecionado, utilizando a mesma regra da Evolução Mensal.
    st.markdown(
        f"### Ranking mensal do maior para o menor % de Canal Vermelho — {period_label(selected_period)}"
    )
    daily_ranking_cd = ranking_summary(current, "CD Origem")
    daily_ranking_transportadora = ranking_summary(current, "Transportadora")

    daily_rank_col1, daily_rank_col2 = st.columns(2, gap="large")
    with daily_rank_col1:
        daily_top_cd = daily_ranking_cd.head(20).sort_values("% Canal Vermelho")
        fig_daily_rank_cd = go.Figure(go.Bar(
            x=daily_top_cd["% Canal Vermelho"],
            y=daily_top_cd["CD Origem"],
            orientation="h",
            marker_color=RED,
            text=daily_top_cd["% Canal Vermelho"].map(br_pct),
            textposition="outside",
        ))
        daily_cd_max = float(daily_top_cd["% Canal Vermelho"].max()) if not daily_top_cd.empty else 0
        daily_cd_axis_max = min(1.0, max(0.15, daily_cd_max * 1.28))
        fig_daily_rank_cd.update_traces(
            texttemplate="%{text}", textfont=dict(size=13), cliponaxis=False,
        )
        fig_daily_rank_cd.update_layout(
            title=dict(text="Ranking por CD Origem", x=0.02, y=0.97),
            height=max(460, len(daily_top_cd) * 34),
            margin=dict(l=55, r=135, t=90, b=60),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(
                title="% Canal Vermelho", tickformat=".0%", gridcolor=GRID,
                range=[0, daily_cd_axis_max], fixedrange=False,
            ),
            yaxis_title=None,
        )
        with st.container(border=True):
            st.plotly_chart(fig_daily_rank_cd, use_container_width=True)

    with daily_rank_col2:
        daily_top_transp = daily_ranking_transportadora.head(20).sort_values("% Canal Vermelho")
        fig_daily_rank_transp = go.Figure(go.Bar(
            x=daily_top_transp["% Canal Vermelho"],
            y=daily_top_transp["Transportadora"],
            orientation="h",
            marker_color=ORANGE,
            text=daily_top_transp["% Canal Vermelho"].map(br_pct),
            textposition="outside",
        ))
        daily_transp_max = float(daily_top_transp["% Canal Vermelho"].max()) if not daily_top_transp.empty else 0
        daily_transp_axis_max = min(1.0, max(0.20, daily_transp_max * 1.22))
        fig_daily_rank_transp.update_traces(
            texttemplate="%{text}", textfont=dict(size=13), cliponaxis=False,
        )
        fig_daily_rank_transp.update_layout(
            title=dict(text="Ranking por Transportadora", x=0.02, y=0.97),
            height=max(460, len(daily_top_transp) * 34),
            margin=dict(l=55, r=145, t=90, b=60),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(
                title="% Canal Vermelho", tickformat=".0%", gridcolor=GRID,
                range=[0, daily_transp_axis_max], fixedrange=False,
            ),
            yaxis_title=None,
        )
        with st.container(border=True):
            st.plotly_chart(fig_daily_rank_transp, use_container_width=True)

    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)
    st.markdown("#### Tabelas dos Rankings do mês")

    daily_table_rank_cd = daily_ranking_cd.copy()
    daily_table_rank_cd["% Canal Vermelho"] = daily_table_rank_cd["% Canal Vermelho"].map(br_pct)
    st.markdown("##### Ranking por CD Origem")
    st.dataframe(daily_table_rank_cd, use_container_width=True, hide_index=True)

    daily_table_rank_transportadora = daily_ranking_transportadora.copy()
    daily_table_rank_transportadora["% Canal Vermelho"] = daily_table_rank_transportadora["% Canal Vermelho"].map(br_pct)
    st.markdown("##### Ranking por Transportadora")
    st.dataframe(daily_table_rank_transportadora, use_container_width=True, hide_index=True)

    daily_ranking_excel = io.BytesIO()
    with pd.ExcelWriter(daily_ranking_excel, engine="openpyxl") as writer:
        daily_ranking_cd.to_excel(writer, sheet_name="Ranking CD", index=False)
        daily_ranking_transportadora.to_excel(writer, sheet_name="Ranking Transportadora", index=False)
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="E30613")
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 3, 35)

    st.download_button(
        "⬇️ Baixar Rankings do mês em Excel",
        data=daily_ranking_excel.getvalue(),
        file_name=f"rankings_canal_vermelho_{period_label(selected_period).replace('/', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)
    with st.expander("Ver base filtrada do mês"):
        preferred = ["Referencia", "Pedido", "Transportadora", "Empresa Padrao", "CD Origem", "Canal Vermelho", "CV",
                     "Dias Realizado Faturamento", "Dias Aguard. Protocolo", "Dias Aguard.Romaneio",
                     "Dias Aguard. Coleta", "Dias Realizado Entrega", "Dias Realizado Total"]
        columns = [col for col in preferred if col in current.columns]
        st.dataframe(current[columns].sort_values("Referencia"), use_container_width=True, hide_index=True)
        csv = current[columns].to_csv(index=False, sep=";", decimal=",", date_format="%d/%m/%Y").encode("utf-8-sig")
        st.download_button("⬇️ Baixar dados filtrados", csv, f"canal_vermelho_{selected_period}.csv", "text/csv")
else:
    # EVOLUÇÃO MENSAL: janela encerrada no Mês/Ano Referência selecionado.
    evolution_periods = pd.period_range(end=selected_period, periods=accumulated_months, freq="M")
    evolution_base = filtered_all[filtered_all["MesRef"].isin(evolution_periods)].copy()

    if evolution_base.empty:
        st.warning("Não existem dados para o período acumulado e filtros selecionados.")
        st.stop()

    def monthly_summary(base, period_list):
        rows = []
        for period in period_list:
            month_data = base[base["MesRef"] == period]
            total = count_orders(month_data)
            with_red = count_orders(month_data[month_data["CV"] == "Sim"])
            without_red = max(0, total - with_red)
            rows.append({
                "Mês/Ano": period_label(period),
                "Período": period,
                "Total Pedidos": total,
                "Com Canal Vermelho": with_red,
                "Sem Canal Vermelho": without_red,
                "% Com Canal Vermelho": with_red / total if total else 0,
                "% Sem Canal Vermelho": without_red / total if total else 0,
            })
        return pd.DataFrame(rows)

    evolution = monthly_summary(evolution_base, evolution_periods)
    ranking_cd = ranking_summary(evolution_base, "CD Origem")
    ranking_transportadora = ranking_summary(evolution_base, "Transportadora")

    st.markdown(
        f"### Evolução Mensal — acumulado de {accumulated_months} meses até {period_label(selected_period)}"
    )

    # Gráfico 1: evolução percentual.
    fig_evolution_pct = go.Figure()
    fig_evolution_pct.add_scatter(
        x=evolution["Mês/Ano"], y=evolution["% Com Canal Vermelho"],
        name="% Com Canal Vermelho", mode="lines+markers+text",
        line=dict(color=RED, width=4), marker=dict(size=10),
        text=evolution["% Com Canal Vermelho"].map(br_pct), textposition="top center",
    )
    fig_evolution_pct.add_scatter(
        x=evolution["Mês/Ano"], y=evolution["% Sem Canal Vermelho"],
        name="% Sem Canal Vermelho", mode="lines+markers+text",
        line=dict(color=GREEN, width=4), marker=dict(size=10),
        text=evolution["% Sem Canal Vermelho"].map(br_pct), textposition="bottom center",
    )
    fig_evolution_pct.update_layout(
        title="Evolução mensal percentual — Com x Sem Canal Vermelho",
        height=550, margin=dict(l=60, r=45, t=100, b=125),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Arial", color="#525866"),
        legend=dict(
            orientation="h", x=0.5, y=-0.24,
            xanchor="center", yanchor="top",
            bgcolor="rgba(255,255,255,0.95)",
            font=dict(size=13),
        ),
        xaxis=dict(title="Mês/Ano"),
        yaxis=dict(title="Percentual", tickformat=".0%", range=[0, 1.08], gridcolor=GRID),
        hovermode="x unified",
    )
    with st.container(border=True):
        st.plotly_chart(fig_evolution_pct, use_container_width=True)

    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)

    # Gráfico 2: evolução em volume.
    fig_evolution_volume = go.Figure()
    fig_evolution_volume.add_scatter(
        x=evolution["Mês/Ano"], y=evolution["Com Canal Vermelho"],
        name="Volume Com Canal Vermelho", mode="lines+markers+text",
        line=dict(color=RED, width=4), marker=dict(size=10),
        text=evolution["Com Canal Vermelho"].map(br_int), textposition="top center",
    )
    fig_evolution_volume.add_scatter(
        x=evolution["Mês/Ano"], y=evolution["Sem Canal Vermelho"],
        name="Volume Sem Canal Vermelho", mode="lines+markers+text",
        line=dict(color=GREEN, width=4), marker=dict(size=10),
        text=evolution["Sem Canal Vermelho"].map(br_int), textposition="bottom center",
    )
    fig_evolution_volume.update_layout(
        title="Evolução mensal em volume — Com x Sem Canal Vermelho",
        height=550, margin=dict(l=60, r=45, t=100, b=125),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Arial", color="#525866"),
        legend=dict(
            orientation="h", x=0.5, y=-0.24,
            xanchor="center", yanchor="top",
            bgcolor="rgba(255,255,255,0.95)",
            font=dict(size=13),
        ),
        xaxis=dict(title="Mês/Ano"), yaxis=dict(title="Pedidos distintos", gridcolor=GRID),
        hovermode="x unified",
    )
    with st.container(border=True):
        st.plotly_chart(fig_evolution_volume, use_container_width=True)

    st.markdown('<div class="chart-section-gap-lg"></div>', unsafe_allow_html=True)
    st.markdown("### Ranking do maior para o menor % de Canal Vermelho")

    rank_col1, rank_col2 = st.columns(2, gap="large")
    with rank_col1:
        top_cd = ranking_cd.head(20).sort_values("% Canal Vermelho")
        fig_rank_cd = go.Figure(go.Bar(
            x=top_cd["% Canal Vermelho"], y=top_cd["CD Origem"], orientation="h",
            marker_color=RED, text=top_cd["% Canal Vermelho"].map(br_pct),
            textposition="outside",
        ))
        cd_max = float(top_cd["% Canal Vermelho"].max()) if not top_cd.empty else 0
        cd_axis_max = min(1.0, max(0.15, cd_max * 1.40))
        fig_rank_cd.update_traces(
            texttemplate="%{text}",
            textfont=dict(size=13),
            cliponaxis=False,
        )
        fig_rank_cd.update_layout(
            title="Ranking por CD Origem", height=max(440, len(top_cd) * 32),
            margin=dict(l=40, r=175, t=80, b=50), paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(
                title="% Canal Vermelho", tickformat=".0%", gridcolor=GRID,
                range=[0, cd_axis_max],
            ),
            yaxis_title=None,
        )
        with st.container(border=True):
            st.plotly_chart(fig_rank_cd, use_container_width=True)

    with rank_col2:
        top_transp = ranking_transportadora.head(20).sort_values("% Canal Vermelho")
        fig_rank_transp = go.Figure(go.Bar(
            x=top_transp["% Canal Vermelho"], y=top_transp["Transportadora"], orientation="h",
            marker_color=ORANGE, text=top_transp["% Canal Vermelho"].map(br_pct),
            textposition="outside",
        ))
        transp_max = float(top_transp["% Canal Vermelho"].max()) if not top_transp.empty else 0
        transp_axis_max = min(1.0, max(0.20, transp_max * 1.32))
        fig_rank_transp.update_traces(
            texttemplate="%{text}",
            textfont=dict(size=13),
            cliponaxis=False,
        )
        fig_rank_transp.update_layout(
            title="Ranking por Transportadora", height=max(440, len(top_transp) * 32),
            margin=dict(l=40, r=190, t=80, b=50), paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(
                title="% Canal Vermelho", tickformat=".0%", gridcolor=GRID,
                range=[0, transp_axis_max],
            ),
            yaxis_title=None,
        )
        with st.container(border=True):
            st.plotly_chart(fig_rank_transp, use_container_width=True)

    st.markdown('<div class="chart-section-gap"></div>', unsafe_allow_html=True)
    st.markdown("### Tabelas da Evolução Mensal")

    table_pct = evolution[["Mês/Ano", "% Com Canal Vermelho", "% Sem Canal Vermelho"]].copy()
    table_pct["% Com Canal Vermelho"] = table_pct["% Com Canal Vermelho"].map(br_pct)
    table_pct["% Sem Canal Vermelho"] = table_pct["% Sem Canal Vermelho"].map(br_pct)
    st.markdown("#### Percentuais por mês")
    st.dataframe(table_pct, use_container_width=True, hide_index=True)

    table_volume = evolution[["Mês/Ano", "Total Pedidos", "Com Canal Vermelho", "Sem Canal Vermelho"]].copy()
    st.markdown("#### Volumes por mês")
    st.dataframe(table_volume, use_container_width=True, hide_index=True)

    table_rank_cd = ranking_cd.copy()
    table_rank_cd["% Canal Vermelho"] = table_rank_cd["% Canal Vermelho"].map(br_pct)
    st.markdown("#### Ranking por CD Origem")
    st.dataframe(table_rank_cd, use_container_width=True, hide_index=True)

    table_rank_transportadora = ranking_transportadora.copy()
    table_rank_transportadora["% Canal Vermelho"] = table_rank_transportadora["% Canal Vermelho"].map(br_pct)
    st.markdown("#### Ranking por Transportadora")
    st.dataframe(table_rank_transportadora, use_container_width=True, hide_index=True)

    # Excel com as tabelas e a base filtrada do período.
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        export_summary = evolution.drop(columns=["Período"]).copy()
        export_summary.to_excel(writer, sheet_name="Resumo Mensal", index=False)
        ranking_cd.to_excel(writer, sheet_name="Ranking CD", index=False)
        ranking_transportadora.to_excel(writer, sheet_name="Ranking Transportadora", index=False)
        export_cols = [
            c for c in ["Referencia", "Pedido", "Transportadora", "Empresa Padrao", "CD Origem", "Canal Vermelho", "CV"]
            if c in evolution_base.columns
        ]
        evolution_base[export_cols].sort_values("Referencia").to_excel(
            writer, sheet_name="Base Filtrada", index=False
        )
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="E30613")
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 3, 35)

    st.download_button(
        "⬇️ Baixar Evolução Mensal e Rankings em Excel",
        data=excel_buffer.getvalue(),
        file_name=f"evolucao_mensal_canal_vermelho_{period_label(selected_period).replace('/', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
