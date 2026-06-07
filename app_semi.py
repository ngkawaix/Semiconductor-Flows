import streamlit as st
import comtradeapicall as comtrade
import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Semiconductor Supply Chain Intelligence",
    layout="wide",
    page_icon="🔬"
)

# ── Data loading ───────────────────────────────────────────────────────────
@st.cache_data
def load_global_data():
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='156,490,410,528,842,392',
        cmdCode='8542', flowCode='X',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    cols = ['reporterDesc','reporterISO','partnerDesc','partnerISO','period','primaryValue']
    df   = df[cols].copy()
    df   = df[df['partnerISO'] != 'W00']
    df['reporterDesc'] = df['reporterDesc'].replace('Other Asia, nes', 'Taiwan')
    df['partnerDesc']  = df['partnerDesc'].replace('Other Asia, nes', 'Taiwan')
    df['primaryValue'] = pd.to_numeric(df['primaryValue'], errors='coerce')
    return df

@st.cache_data
def load_global_equip_data():
    """HS 8486 — semiconductor equipment exports from the five major tool makers."""
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='528,842,392,276,410',   # Netherlands, USA, Japan, Germany, S. Korea
        cmdCode='8486', flowCode='X',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    cols = ['reporterDesc','reporterISO','partnerDesc','partnerISO','period','primaryValue']
    df   = df[cols].copy()
    df   = df[df['partnerISO'] != 'W00']
    df['reporterDesc'] = df['reporterDesc'].replace('Other Asia, nes', 'Taiwan')
    df['partnerDesc']  = df['partnerDesc'].replace('Other Asia, nes', 'Taiwan')
    df['primaryValue'] = pd.to_numeric(df['primaryValue'], errors='coerce')
    return df

@st.cache_data
def load_asean_equip():
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='702,458,704,764,608,360',
        cmdCode='8486', flowCode='M',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    df = (
        df[df['partnerISO'] != 'W00']
        .assign(primaryValue=lambda d: pd.to_numeric(d['primaryValue'], errors='coerce'))
        .groupby(['reporterDesc', 'period'])['primaryValue']
        .sum().reset_index()
        .rename(columns={'reporterDesc':'country','period':'year','primaryValue':'equip_imports'})
    )
    df['year'] = df['year'].astype(int)
    return df

@st.cache_data
def load_asean_chips():
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='702,458,704,764,608,360',
        cmdCode='8542', flowCode='X',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    df = (
        df[df['partnerISO'] != 'W00']
        .assign(primaryValue=lambda d: pd.to_numeric(d['primaryValue'], errors='coerce'))
        .groupby(['reporterDesc', 'period'])['primaryValue']
        .sum().reset_index()
        .rename(columns={'reporterDesc':'country','period':'year','primaryValue':'chip_exports'})
    )
    df['year'] = df['year'].astype(int)
    return df

# ── Unified colour palette (YlGnBu-inspired, muted and professional) ───────
# Hex colours used across all Plotly charts and Sankey
src_hex = {
    'Taiwan':        '#1d91c0',
    'Rep. of Korea': '#41b6c4',
    'China':         '#D85A30',
    'Netherlands':   '#7fcdbb',
    'USA':           '#225ea8',
    'Japan':         '#c7e9b4',
}

# RGBA for pydeck ArcLayer (converted from src_hex)
colour_map = {
    'Taiwan':        [29,  145, 192, 210],
    'Rep. of Korea': [65,  182, 196, 210],
    'China':         [216,  90,  48, 210],
    'Netherlands':   [127, 205, 187, 210],
    'USA':           [34,   94, 168, 210],
    'Japan':         [199, 233, 180, 210],
}

# Equipment producer colours (HS 8486) — Germany added as muted purple
equip_src_hex = {
    'Netherlands':   '#7fcdbb',
    'USA':           '#225ea8',
    'Japan':         '#c7e9b4',
    'Germany':       '#9e9ac8',
    'Rep. of Korea': '#41b6c4',
}

equip_colour_map = {
    'Netherlands':   [127, 205, 187, 210],
    'USA':           [34,   94, 168, 210],
    'Japan':         [199, 233, 180, 210],
    'Germany':       [158, 154, 200, 210],
    'Rep. of Korea': [65,  182, 196, 210],
}

# YlGnBu status colours for ASEAN table
status_colours = {
    'Rising Hub':         '#1d91c0',
    'Assembly Dependent': '#41b6c4',
    'Emerging':           '#7fcdbb',
    'Lagging':            '#c7e9b4',
}

# ── Helpers ────────────────────────────────────────────────────────────────
country_coords = {
    'CHN':(35.8617,104.1954),'TWN':(23.6978,120.9605),'KOR':(35.9078,127.7669),
    'NLD':(52.1326,5.2913),  'USA':(37.0902,-95.7129), 'JPN':(36.2048,138.2529),
    'HKG':(22.3193,114.1694),'VNM':(14.0583,108.2772),'SGP':(1.3521,103.8198),
    'MYS':(4.2105,101.9758), 'MEX':(23.6345,-102.5528),'PHL':(12.8797,121.7740),
    'DEU':(51.1657,10.4515), 'GBR':(55.3781,-3.4360), 'IND':(20.5937,78.9629),
    'THA':(15.8700,100.9925),'IDN':(-0.7893,113.9213),'IRL':(53.1424,-7.6921),
    'BRA':(-14.235,-51.9253),'AUS':(-25.274,133.7751), 'CZE':(49.8175,15.4730),
    'ISR':(31.0461,34.8516), 'POL':(51.9194,19.1451), 'SAU':(23.8859,45.0792),
}

def fmt(val):
    if pd.isna(val):  return 'N/A'
    if val >= 1e12:   return f"${val/1e12:.2f}T"
    elif val >= 1e9:  return f"${val/1e9:.1f}B"
    else:             return f"${val/1e6:.0f}M"

def cagr(start, end, n):
    if pd.notna(start) and pd.notna(end) and start > 0 and end > 0 and n > 0:
        return round(((end/start)**(1/n)-1)*100, 1)
    return None

def hex_to_rgba(hex_color, alpha=0.45):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

@st.cache_data
def build_asean_summary(df_equip, df_chips):
    df_asean = df_equip.merge(df_chips, on=['country','year'], how='outer')

    start_yr = 2018

    def get_val(df, country, yr, col):
        row = df[(df['country']==country) & (df['year']==yr)]
        return row[col].values[0] if not row.empty else None

    countries_asean = sorted(df_asean['country'].unique())

    # Use each country's own latest reported year — avoids None values when
    # some countries have filed 2025 data and others haven't yet
    latest_yr = {
        c: int(df_asean[df_asean['country'] == c]['year'].max())
        for c in countries_asean
    }

    summary = pd.DataFrame(index=countries_asean)

    for col, label_s, label_e, metric in [
        ('equip_imports', 'Equip Imports 2018 ($B)', 'Equip Imports Latest ($B)', 'Equip CAGR (%)'),
        ('chip_exports',  'Chip Exports 2018 ($B)',  'Chip Exports Latest ($B)',  'Chip Export CAGR (%)'),
    ]:
        vals_s = {c: get_val(df_asean, c, start_yr,     col) for c in countries_asean}
        vals_e = {c: get_val(df_asean, c, latest_yr[c], col) for c in countries_asean}
        summary[label_s] = pd.Series(vals_s) / 1e9
        summary[label_e] = pd.Series(vals_e) / 1e9
        summary[metric]  = pd.Series({
            c: cagr(vals_s[c], vals_e[c], latest_yr[c] - start_yr)
            for c in countries_asean
        })

    summary['Value Chain Ratio'] = (
        summary['Chip Exports Latest ($B)'] / summary['Equip Imports Latest ($B)']
    ).round(2)

    med_equip = summary['Equip CAGR (%)'].median()
    med_chips = summary['Chip Export CAGR (%)'].median()

    def classify(row):
        hi_e = row['Equip CAGR (%)']      >= med_equip
        hi_c = row['Chip Export CAGR (%)'] >= med_chips
        if   hi_e and hi_c:  return 'Rising Hub'
        elif hi_c:           return 'Assembly Dependent'
        elif hi_e:           return 'Emerging'
        else:                return 'Lagging'

    summary['Status'] = summary.apply(classify, axis=1)
    summary = summary.round(2).sort_values('Chip Export CAGR (%)', ascending=False)

    return summary, med_equip, med_chips

# ── Load all data ──────────────────────────────────────────────────────────
with st.spinner("Loading UN Comtrade data — this may take a moment on first load..."):
    df_global       = load_global_data()
    df_global_equip = load_global_equip_data()
    df_equip        = load_asean_equip()
    df_chips        = load_asean_chips()

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("Controls")
st.sidebar.markdown("### IC Producers")
st.sidebar.caption("Applies to the IC section of Tab 1.")

selected_countries = []
for country, hex_c in src_hex.items():
    label = f'<span style="color:{hex_c}; font-size:16px">■</span> {country}'
    if st.sidebar.checkbox(country, value=True, key=f"toggle_{country}"):
        selected_countries.append(country)

st.sidebar.markdown("---")
st.sidebar.markdown("### Equipment Exporters")
st.sidebar.caption("Applies to the Equipment section of Tab 1.")

selected_equip_countries = []
for country, hex_c in equip_src_hex.items():
    if st.sidebar.checkbox(country, value=True, key=f"eq_toggle_{country}"):
        selected_equip_countries.append(country)

st.sidebar.markdown("---")
st.sidebar.markdown("### Select Year")
st.sidebar.caption("Applies to the Global Supply Chain tab.")
year = st.sidebar.slider("Year", 2018, 2025, 2024, label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Source:** UN Comtrade  \n"
    "**Products:** HS 8486 (equipment), HS 8542 (ICs)  \n"
    "**Coverage:** 2018–2025  \n"
    "**Flow:** Exports (global), Imports/Exports (ASEAN)"
)

# ── Tabs ───────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🌍  Global Supply Chain", "🌏  ASEAN Value Chain"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GLOBAL SUPPLY CHAIN
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.title("Global Semiconductor Trade Flows")

    # Shared coordinate lookup used by both arc maps
    coords_df = (
        pd.DataFrame.from_dict(country_coords, orient='index', columns=['lat','lon'])
        .reset_index().rename(columns={'index':'ISO'})
    )

    # ══ SECTION 1 — INTEGRATED CIRCUITS (HS 8542) ════════════════════════════
    st.header("🔬 Integrated Circuits (HS 8542)")
    st.caption(
        "Exports from major IC-producing nations. "
        "Left = exporters, right = destination markets. "
        "Arc width proportional to export value. Data: UN Comtrade."
    )

    df_arcs = (
        df_global
        .merge(coords_df.rename(columns={'ISO':'reporterISO','lat':'source_lat','lon':'source_lon'}), on='reporterISO', how='inner')
        .merge(coords_df.rename(columns={'ISO':'partnerISO', 'lat':'target_lat', 'lon':'target_lon'}), on='partnerISO',  how='inner')
    )
    top_partners = (
        df_arcs.groupby('partnerISO')['primaryValue']
        .sum().sort_values(ascending=False).head(15).index.tolist()
    )
    df_arcs = (
        df_arcs[df_arcs['partnerISO'].isin(top_partners) & (df_arcs['target_lat'] < 60)]
        .groupby(['reporterDesc','reporterISO','partnerDesc','partnerISO',
                  'period','source_lat','source_lon','target_lat','target_lon'])
        ['primaryValue'].sum().reset_index()
    )

    df_year     = df_arcs[(df_arcs['period']==str(year)) & (df_arcs['reporterDesc'].isin(selected_countries))].copy()
    df_year_all = df_global[df_global['period']==str(year)]
    df_prev_all = df_global[df_global['period']==str(year-1)] if year > 2018 else None

    total_cur    = df_year_all['primaryValue'].sum()
    total_prev   = df_prev_all['primaryValue'].sum() if df_prev_all is not None else None
    taiwan_share = df_year_all[df_year_all['reporterDesc']=='Taiwan']['primaryValue'].sum() / total_cur * 100
    china_share  = df_year_all[df_year_all['reporterDesc']=='China']['primaryValue'].sum()  / total_cur * 100
    yoy          = f"{((total_cur-total_prev)/total_prev*100):+.1f}% YoY" if total_prev else None

    c1, c2, c3 = st.columns(3)
    c1.metric("Total IC Exports",  fmt(total_cur),        delta=yoy)
    c2.metric("Taiwan's Share",    f"{taiwan_share:.1f}%")
    c3.metric("China's Share",     f"{china_share:.1f}%")
    st.markdown("---")

    if selected_countries and not df_year.empty:
        df_year['color']     = df_year['reporterDesc'].map(colour_map)
        df_year['width']     = (df_year['primaryValue'] / df_year['primaryValue'].max() * 25).clip(lower=2)
        df_year['value_fmt'] = df_year['primaryValue'].apply(fmt)
        st.pydeck_chart(
            pdk.Deck(
                layers=[pdk.Layer(
                    'ArcLayer', data=df_year,
                    get_source_position=['source_lon','source_lat'],
                    get_target_position=['target_lon','target_lat'],
                    get_source_color='color', get_target_color='color',
                    get_width='width', pickable=True, auto_highlight=True,
                )],
                initial_view_state=pdk.ViewState(latitude=25, longitude=60, zoom=2, pitch=20),
                map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
                tooltip={'text': '{reporterDesc} → {partnerDesc}\n{value_fmt}'}
            ),
            key=f"arc_map_{year}_{'_'.join(sorted(selected_countries))}"
        )
    else:
        st.info("Select at least one IC producer in the sidebar to display the map.")

    st.markdown("---")

    # ── IC Sankey ──────────────────────────────────────────────────────────
    st.subheader("Supply chain flow — IC producers to destinations")
    st.caption(
        "Left: 6 major IC-producing nations. "
        "Right: their top 8 export destinations for the selected year (excluding producers)."
    )

    producer_set = set(colour_map.keys())
    df_sk = (
        df_global[df_global['period'] == str(year)]
        .groupby(['reporterDesc', 'partnerDesc'])['primaryValue']
        .sum().reset_index()
    )
    df_sk = df_sk[
        df_sk['reporterDesc'].isin(selected_countries) &
        ~df_sk['partnerDesc'].isin(producer_set)
    ]
    top_dest = df_sk.groupby('partnerDesc')['primaryValue'].sum().nlargest(8).index
    df_sk    = df_sk[df_sk['partnerDesc'].isin(top_dest)]

    if not df_sk.empty:
        src_nodes = list(df_sk['reporterDesc'].unique())
        tgt_nodes = list(df_sk['partnerDesc'].unique())
        all_nodes = src_nodes + tgt_nodes
        node_idx  = {n: i for i, n in enumerate(all_nodes)}
        n_src = len(src_nodes);  n_tgt = len(tgt_nodes)
        node_x = [0.01] * n_src + [0.99] * n_tgt
        node_y = (
            [round((i + 0.5) / n_src, 3) for i in range(n_src)] +
            [round((i + 0.5) / n_tgt, 3) for i in range(n_tgt)]
        )
        ylgnbu_dest = ['#225ea8','#1d91c0','#41b6c4','#7fcdbb',
                       '#c7e9b4','#edf8b1','#ffffd9','#f7fcb9']
        node_colors = (
            [src_hex.get(n, '#888888') for n in src_nodes] +
            [ylgnbu_dest[i % len(ylgnbu_dest)] for i in range(n_tgt)]
        )
        link_sources = [node_idx[r] for r in df_sk['reporterDesc']]
        link_targets  = [node_idx[t] for t in df_sk['partnerDesc']]
        link_values   = (df_sk['primaryValue'] / 1e9).round(1).tolist()
        link_colors   = [hex_to_rgba(src_hex.get(r, '#888888')) for r in df_sk['reporterDesc']]
        fig_sk = go.Figure(go.Sankey(
            arrangement='fixed',
            node=dict(pad=20, thickness=20, label=all_nodes, color=node_colors,
                      x=node_x, y=node_y,
                      hovertemplate='%{label}<br>$%{value:.1f}B<extra></extra>'),
            link=dict(source=link_sources, target=link_targets, value=link_values,
                      color=link_colors,
                      hovertemplate='%{source.label} → %{target.label}<br>$%{value:.1f}B<extra></extra>'),
            textfont=dict(size=13, color='#1a1a1a', family='sans-serif'),
        ))
        fig_sk.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                             margin=dict(t=10, b=10, l=10, r=10), height=500)
        st.plotly_chart(fig_sk, width='stretch')
    else:
        st.info("Select at least one IC producer in the sidebar to display the Sankey.")

    st.markdown("---")

    # ── IC Time series ─────────────────────────────────────────────────────
    st.subheader("IC Export Trends by Country (2018–2025)")
    df_trend = (
        df_global[df_global['reporterDesc'].isin(selected_countries)]
        .groupby(['reporterDesc','period'])['primaryValue'].sum().reset_index()
    )
    df_trend['period']  = df_trend['period'].astype(int)
    df_trend['value_B'] = df_trend['primaryValue'] / 1e9
    fig_ts = px.line(
        df_trend, x='period', y='value_B', color='reporterDesc', markers=True,
        labels={'value_B':'Export Value (USD Billion)','period':'Year','reporterDesc':'Country'},
        color_discrete_map=src_hex,
    )
    fig_ts.add_vline(x=year, line_dash='dot',  line_color='#888888', opacity=0.5)
    fig_ts.add_vline(x=2022, line_dash='dash', line_color='#D85A30', opacity=0.9)
    if not df_trend.empty:
        fig_ts.add_annotation(
            x=2022.05, y=df_trend['value_B'].max()*0.95,
            text="US Export Controls<br>Oct 2022", showarrow=False,
            font=dict(color='#D85A30', size=11), xanchor='left'
        )
    fig_ts.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        legend_title='Country', hovermode='x unified',
        xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(0,0,0,0.08)'),
        yaxis=dict(gridcolor='rgba(0,0,0,0.08)'), margin=dict(t=20),
    )
    st.plotly_chart(fig_ts, width='stretch')

    # ══ SECTION 2 — SEMICONDUCTOR EQUIPMENT (HS 8486) ════════════════════════
    st.divider()
    st.header("⚙️ Semiconductor Equipment (HS 8486)")
    st.caption(
        "Exports of lithography machines (EUV/DUV), etch tools, deposition systems, and metrology. "
        "Left = equipment exporters, right = fab nations buying equipment. "
        "Data: UN Comtrade."
    )

    df_arcs_eq = (
        df_global_equip
        .merge(coords_df.rename(columns={'ISO':'reporterISO','lat':'source_lat','lon':'source_lon'}), on='reporterISO', how='inner')
        .merge(coords_df.rename(columns={'ISO':'partnerISO', 'lat':'target_lat', 'lon':'target_lon'}), on='partnerISO',  how='inner')
    )
    top_partners_eq = (
        df_arcs_eq.groupby('partnerISO')['primaryValue']
        .sum().sort_values(ascending=False).head(15).index.tolist()
    )
    df_arcs_eq = (
        df_arcs_eq[df_arcs_eq['partnerISO'].isin(top_partners_eq) & (df_arcs_eq['target_lat'] < 60)]
        .groupby(['reporterDesc','reporterISO','partnerDesc','partnerISO',
                  'period','source_lat','source_lon','target_lat','target_lon'])
        ['primaryValue'].sum().reset_index()
    )

    df_eq_year     = df_arcs_eq[(df_arcs_eq['period']==str(year)) & (df_arcs_eq['reporterDesc'].isin(selected_equip_countries))].copy()
    df_eq_year_all = df_global_equip[df_global_equip['period']==str(year)]
    df_eq_prev_all = df_global_equip[df_global_equip['period']==str(year-1)] if year > 2018 else None

    total_eq_cur  = df_eq_year_all['primaryValue'].sum()
    total_eq_prev = df_eq_prev_all['primaryValue'].sum() if df_eq_prev_all is not None else None
    yoy_eq        = f"{((total_eq_cur-total_eq_prev)/total_eq_prev*100):+.1f}% YoY" if total_eq_prev else None
    nld_share     = (
        df_eq_year_all[df_eq_year_all['reporterDesc']=='Netherlands']['primaryValue'].sum()
        / total_eq_cur * 100
    ) if total_eq_cur > 0 else 0

    producer_set_eq = set(equip_colour_map.keys())
    top_eq_dest_ser = (
        df_eq_year_all[~df_eq_year_all['partnerDesc'].isin(producer_set_eq)]
        .groupby('partnerDesc')['primaryValue'].sum()
    )
    top_eq_importer = top_eq_dest_ser.idxmax() if not top_eq_dest_ser.empty else 'N/A'

    e1, e2, e3 = st.columns(3)
    e1.metric("Total Equipment Exports",    fmt(total_eq_cur), delta=yoy_eq)
    e2.metric("Netherlands' Share (ASML)",  f"{nld_share:.1f}%")
    e3.metric("Largest Equipment Buyer",    top_eq_importer)
    st.markdown("---")

    if selected_equip_countries and not df_eq_year.empty:
        df_eq_year['color']     = df_eq_year['reporterDesc'].map(equip_colour_map)
        df_eq_year['width']     = (df_eq_year['primaryValue'] / df_eq_year['primaryValue'].max() * 25).clip(lower=2)
        df_eq_year['value_fmt'] = df_eq_year['primaryValue'].apply(fmt)
        st.pydeck_chart(
            pdk.Deck(
                layers=[pdk.Layer(
                    'ArcLayer', data=df_eq_year,
                    get_source_position=['source_lon','source_lat'],
                    get_target_position=['target_lon','target_lat'],
                    get_source_color='color', get_target_color='color',
                    get_width='width', pickable=True, auto_highlight=True,
                )],
                initial_view_state=pdk.ViewState(latitude=25, longitude=60, zoom=2, pitch=20),
                map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
                tooltip={'text': '{reporterDesc} → {partnerDesc}\n{value_fmt}'}
            ),
            key=f"arc_eq_{year}_{'_'.join(sorted(selected_equip_countries))}"
        )
    else:
        st.info("Select at least one equipment exporter in the sidebar to display the map.")

    st.markdown("---")

    # ── Equipment Sankey ───────────────────────────────────────────────────
    st.subheader("Supply chain flow — equipment makers to fab nations")
    st.caption(
        "Left: 5 major equipment-exporting nations. "
        "Right: their top 8 destination markets for the selected year (excluding equipment producers)."
    )

    df_sk_eq = (
        df_global_equip[df_global_equip['period'] == str(year)]
        .groupby(['reporterDesc', 'partnerDesc'])['primaryValue']
        .sum().reset_index()
    )
    df_sk_eq = df_sk_eq[
        df_sk_eq['reporterDesc'].isin(selected_equip_countries) &
        ~df_sk_eq['partnerDesc'].isin(producer_set_eq)
    ]
    top_eq_dest = df_sk_eq.groupby('partnerDesc')['primaryValue'].sum().nlargest(8).index
    df_sk_eq    = df_sk_eq[df_sk_eq['partnerDesc'].isin(top_eq_dest)]

    if not df_sk_eq.empty:
        eq_src_nodes = list(df_sk_eq['reporterDesc'].unique())
        eq_tgt_nodes = list(df_sk_eq['partnerDesc'].unique())
        eq_all_nodes = eq_src_nodes + eq_tgt_nodes
        eq_node_idx  = {n: i for i, n in enumerate(eq_all_nodes)}
        eq_n_src = len(eq_src_nodes);  eq_n_tgt = len(eq_tgt_nodes)
        eq_node_x = [0.01] * eq_n_src + [0.99] * eq_n_tgt
        eq_node_y = (
            [round((i + 0.5) / eq_n_src, 3) for i in range(eq_n_src)] +
            [round((i + 0.5) / eq_n_tgt, 3) for i in range(eq_n_tgt)]
        )
        ylgnbu_dest = ['#225ea8','#1d91c0','#41b6c4','#7fcdbb',
                       '#c7e9b4','#edf8b1','#ffffd9','#f7fcb9']
        eq_node_colors = (
            [equip_src_hex.get(n, '#888888') for n in eq_src_nodes] +
            [ylgnbu_dest[i % len(ylgnbu_dest)] for i in range(eq_n_tgt)]
        )
        eq_link_sources = [eq_node_idx[r] for r in df_sk_eq['reporterDesc']]
        eq_link_targets  = [eq_node_idx[t] for t in df_sk_eq['partnerDesc']]
        eq_link_values   = (df_sk_eq['primaryValue'] / 1e9).round(1).tolist()
        eq_link_colors   = [hex_to_rgba(equip_src_hex.get(r, '#888888')) for r in df_sk_eq['reporterDesc']]
        fig_sk_eq = go.Figure(go.Sankey(
            arrangement='fixed',
            node=dict(pad=20, thickness=20, label=eq_all_nodes, color=eq_node_colors,
                      x=eq_node_x, y=eq_node_y,
                      hovertemplate='%{label}<br>$%{value:.1f}B<extra></extra>'),
            link=dict(source=eq_link_sources, target=eq_link_targets, value=eq_link_values,
                      color=eq_link_colors,
                      hovertemplate='%{source.label} → %{target.label}<br>$%{value:.1f}B<extra></extra>'),
            textfont=dict(size=13, color='#1a1a1a', family='sans-serif'),
        ))
        fig_sk_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                                margin=dict(t=10, b=10, l=10, r=10), height=500)
        st.plotly_chart(fig_sk_eq, width='stretch')
    else:
        st.info("Select at least one equipment exporter in the sidebar to display the Sankey.")

    st.markdown("---")

    # ── Equipment Time series ──────────────────────────────────────────────
    st.subheader("Equipment Export Trends by Country (2018–2025)")
    df_eq_trend_global = (
        df_global_equip[df_global_equip['reporterDesc'].isin(selected_equip_countries)]
        .groupby(['reporterDesc','period'])['primaryValue'].sum().reset_index()
    )
    df_eq_trend_global['period']  = df_eq_trend_global['period'].astype(int)
    df_eq_trend_global['value_B'] = df_eq_trend_global['primaryValue'] / 1e9
    fig_eq_ts = px.line(
        df_eq_trend_global, x='period', y='value_B', color='reporterDesc', markers=True,
        labels={'value_B':'Export Value (USD Billion)','period':'Year','reporterDesc':'Country'},
        color_discrete_map=equip_src_hex,
    )
    fig_eq_ts.add_vline(x=year, line_dash='dot',  line_color='#888888', opacity=0.5)
    fig_eq_ts.add_vline(x=2022, line_dash='dash', line_color='#D85A30', opacity=0.9)
    if not df_eq_trend_global.empty:
        fig_eq_ts.add_annotation(
            x=2022.05, y=df_eq_trend_global['value_B'].max()*0.95,
            text="US Export Controls<br>Oct 2022", showarrow=False,
            font=dict(color='#D85A30', size=11), xanchor='left'
        )
    fig_eq_ts.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        legend_title='Country', hovermode='x unified',
        xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(0,0,0,0.08)'),
        yaxis=dict(gridcolor='rgba(0,0,0,0.08)'), margin=dict(t=20),
    )
    st.plotly_chart(fig_eq_ts, width='stretch')



# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ASEAN VALUE CHAIN
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.title("ASEAN Semiconductor Value Chain")
    st.caption(
        "Which ASEAN economies are moving up the semiconductor value chain? "
        "Equipment imports proxy investment; IC exports proxy current capability."
    )

    summary, med_equip, med_chips = build_asean_summary(df_equip, df_chips)

    st.subheader("Value Chain Positioning Table")

    def colour_status(val):
        c = {
            'Rising Hub':         '#1d91c0',
            'Assembly Dependent': '#41b6c4',
            'Emerging':           '#7fcdbb',
            'Lagging':            '#c7e9b4',
        }.get(val, '')
        return f'background-color:{c}; color:#0c2c84; font-weight:600' if c else ''

    styled = (
        summary.style
        .map(colour_status, subset=['Status'])
        .format({
            'Equip Imports 2018 ($B)':   '${:.2f}B',
            'Equip Imports Latest ($B)': '${:.2f}B',
            'Equip CAGR (%)':            '{:.1f}%',
            'Chip Exports 2018 ($B)':    '${:.2f}B',
            'Chip Exports Latest ($B)':  '${:.2f}B',
            'Chip Export CAGR (%)':      '{:.1f}%',
            'Value Chain Ratio':         '{:.2f}x',
        }, na_rep='N/A')
    )
    st.dataframe(styled, width='stretch')

    st.markdown("---")

    st.subheader("Value Chain Quadrant Analysis")
    st.caption(
        "X-axis: equipment import CAGR (investment proxy). "
        "Y-axis: IC export CAGR (capability proxy). "
        "Bubble size: current IC export volume."
    )

    df_plot = summary.reset_index().rename(columns={'index':'country'})
    fig_scatter = go.Figure()

    for status, colour in status_colours.items():
        sub = df_plot[df_plot['Status']==status]
        if sub.empty: continue
        fig_scatter.add_trace(go.Scatter(
            x=sub['Equip CAGR (%)'], y=sub['Chip Export CAGR (%)'],
            mode='markers+text', name=status,
            text=sub['country'], textposition='top center',
            marker=dict(
                size=(sub['Chip Exports Latest ($B)'].fillna(1).clip(lower=1) ** 0.5 * 8),
                color=colour, opacity=0.9,
                line=dict(width=1.5, color='#225ea8')
            )
        ))

    fig_scatter.add_hline(y=med_chips, line_dash='dash', line_color='#888888', opacity=0.4)
    fig_scatter.add_vline(x=med_equip, line_dash='dash', line_color='#888888', opacity=0.4)

    for label, xpos, ypos, colour in [
        ('Rising Hub',         0.95, 0.95, '#1d91c0'),
        ('Assembly Dependent', 0.05, 0.95, '#41b6c4'),
        ('Emerging',           0.95, 0.05, '#7fcdbb'),
        ('Lagging',            0.05, 0.05, '#c7e9b4'),
    ]:
        fig_scatter.add_annotation(
            xref='paper', yref='paper', x=xpos, y=ypos,
            text=label, showarrow=False,
            font=dict(color=colour, size=12), opacity=0.7
        )

    fig_scatter.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        legend_title='Status',
        xaxis=dict(title='Equipment Import CAGR (%)', gridcolor='rgba(0,0,0,0.08)', zeroline=False),
        yaxis=dict(title='IC Export CAGR (%)',        gridcolor='rgba(0,0,0,0.08)', zeroline=False),
        margin=dict(t=20),
    )
    st.plotly_chart(fig_scatter, width='stretch')

    st.markdown("---")

    st.subheader("Equipment Imports vs IC Exports Over Time")
    col_a, col_b = st.columns(2)

    # Shared YlGnBu colour sequence for ASEAN countries
    ylgnbu_seq = ['#225ea8','#1d91c0','#41b6c4','#7fcdbb','#c7e9b4','#edf8b1']
    asean_countries = sorted(df_equip['country'].unique())
    asean_colours   = {c: ylgnbu_seq[i % len(ylgnbu_seq)] for i, c in enumerate(asean_countries)}

    with col_a:
        st.markdown("**Semiconductor Equipment Imports (HS 8486)**")
        df_eq_trend            = df_equip.copy()
        df_eq_trend['value_B'] = df_eq_trend['equip_imports'] / 1e9
        fig_eq = px.line(
            df_eq_trend, x='year', y='value_B', color='country', markers=True,
            labels={'value_B':'USD Billion','year':'Year','country':'Country'},
            color_discrete_map=asean_colours,
        )
        fig_eq.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=10),
            xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(0,0,0,0.08)'),
            yaxis=dict(gridcolor='rgba(0,0,0,0.08)'),
        )
        st.plotly_chart(fig_eq, width='stretch')

    with col_b:
        st.markdown("**IC Exports (HS 8542)**")
        df_ch_trend            = df_chips.copy()
        df_ch_trend['value_B'] = df_ch_trend['chip_exports'] / 1e9
        fig_ch = px.line(
            df_ch_trend, x='year', y='value_B', color='country', markers=True,
            labels={'value_B':'USD Billion','year':'Year','country':'Country'},
            color_discrete_map=asean_colours,
        )
        fig_ch.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=10),
            xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(0,0,0,0.08)'),
            yaxis=dict(gridcolor='rgba(0,0,0,0.08)'),
        )
        st.plotly_chart(fig_ch, width='stretch')
