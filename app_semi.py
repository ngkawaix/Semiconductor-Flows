import streamlit as st
import comtradeapicall as comtrade
import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import os

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
    """HS 8486: semiconductor equipment exports from the five major tool makers."""
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='528,842,392,276,410',
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

@st.cache_data
def load_sankey_data():
    """Load company-level supply chain atlas data from CSV files."""
    df   = pd.read_csv("semi_supply_chain_sankey_v2.csv")
    meta = pd.read_csv("node_metadata_v2.csv").set_index("node_name")
    return df, meta

# ── Canonical colour palette ───────────────────────────────────────────────
country_hex = {
    'Taiwan':        '#1d91c0',
    'Rep. of Korea': '#41b6c4',
    'China':         '#D85A30',
    'Netherlands':   '#7fcdbb',
    'USA':           '#225ea8',
    'Japan':         '#c7e9b4',
    'Germany':       '#9e9ac8',
}
country_rgba = {
    'Taiwan':        [29,  145, 192, 210],
    'Rep. of Korea': [65,  182, 196, 210],
    'China':         [216,  90,  48, 210],
    'Netherlands':   [127, 205, 187, 210],
    'USA':           [34,   94, 168, 210],
    'Japan':         [199, 233, 180, 210],
    'Germany':       [158, 154, 200, 210],
}
IC_EXPORTERS    = ['Taiwan', 'Rep. of Korea', 'China', 'Netherlands', 'USA', 'Japan']
EQUIP_EXPORTERS = ['Netherlands', 'USA', 'Japan', 'Germany', 'Rep. of Korea']
src_hex       = {k: country_hex[k] for k in IC_EXPORTERS}
equip_src_hex = {k: country_hex[k] for k in EQUIP_EXPORTERS}
status_colours = {
    'Rising Hub':         '#1d91c0',
    'Assembly Dependent': '#41b6c4',
    'Emerging':           '#7fcdbb',
    'Lagging':            '#c7e9b4',
}

# ── Actual disclosed revenues for named companies (USD billions) ────────────
# Used to label terminal nodes in the supply chain atlas with real revenue
# rather than supply chain inflow cost (which understates chip designer value)
DISCLOSED_REVENUE = {
    # Chip Designers — FY2025/26 (terminal nodes; label = actual company revenue)
    "Nvidia":           215.9,   # FY2026 (Jan 2026 YE)
    "AMD":               34.6,   # FY2025 (Dec 2025 YE)
    "Broadcom":          63.9,   # FY2025 (Nov 2025 YE)
    "Qualcomm":          44.3,   # FY2025 (Sep 2025 YE)
    "MediaTek":          18.6,   # FY2025 (Dec 2025 YE)
    "Intel Chips":       43.1,   # FY2025 CCG $30.3B + DCAI $12.8B
    "Apple Silicon":     19.9,   # TSMC fab cost only (Apple doesn't sell chips)
    # Foundry & Memory
    "TSMC":             118.0,   # FY2025
    "Samsung Memory":    74.4,   # FY2025
    "Samsung Foundry":   17.0,   # FY2025 analyst estimate
    "SK Hynix":          67.9,   # FY2025
    "Micron":            37.4,   # FY2025
    "GlobalFoundries":    6.75,  # FY2024
    "Intel Fabs":        17.5,   # FY2025 intersegment
    # Equipment
    "ASML":              36.0,   # FY2025
    "Applied Materials": 28.4,   # FY2025
    "Lam Research":      18.4,   # FY2025
    "Tokyo Electron":    16.2,   # FY2025
    "KLA":               12.2,   # FY2025
    "Screen Holdings":    4.2,   # FY2025
    # EDA & IP
    "Arm Holdings":       4.0,   # FY2025
    "Synopsys":           7.1,   # FY2025
    "Cadence":            5.3,   # FY2025
    # Sub-components
    "Zeiss SMT":          5.5,   # floor estimate
    "Entegris":           3.2,   # FY2024
    "SUMCO":              2.6,   # FY2024
    "MKS Instruments":    3.6,   # FY2024
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

_YLGNBU_DEST = ['#225ea8','#1d91c0','#41b6c4','#7fcdbb','#c7e9b4','#edf8b1','#ffffd9','#f7fcb9']

def build_sankey_fig(df_flow, hex_palette):
    src_nodes = list(df_flow['reporterDesc'].unique())
    tgt_nodes = list(df_flow['partnerDesc'].unique())
    all_nodes = src_nodes + tgt_nodes
    node_idx  = {n: i for i, n in enumerate(all_nodes)}
    n_tgt = len(tgt_nodes)
    node_colors = (
        [hex_palette.get(n, '#888888') for n in src_nodes] +
        [_YLGNBU_DEST[i % len(_YLGNBU_DEST)] for i in range(n_tgt)]
    )
    link_sources = [node_idx[r] for r in df_flow['reporterDesc']]
    link_targets  = [node_idx[t] for t in df_flow['partnerDesc']]
    link_values   = (df_flow['primaryValue'] / 1e9).round(1).tolist()
    link_colors   = [hex_to_rgba(hex_palette.get(r, '#888888')) for r in df_flow['reporterDesc']]
    height = max(480, max(len(src_nodes), len(tgt_nodes)) * 60 + 100)
    fig = go.Figure(go.Sankey(
        node=dict(
            pad=20, thickness=20,
            label=all_nodes, color=node_colors,
            hovertemplate='%{label}<br>$%{value:.1f}B<extra></extra>',
        ),
        link=dict(
            source=link_sources, target=link_targets,
            value=link_values,   color=link_colors,
            hovertemplate='%{source.label} → %{target.label}<br>$%{value:.1f}B<extra></extra>',
        ),
        textfont=dict(size=13, color='#1a1a1a', family='sans-serif'),
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=20, b=20, l=10, r=10),
        height=height,
    )
    return fig

@st.cache_data
def build_asean_summary(df_equip, df_chips):
    df_asean = df_equip.merge(df_chips, on=['country','year'], how='outer')
    start_yr = 2018

    def get_val(df, country, yr, col):
        row = df[(df['country']==country) & (df['year']==yr)]
        return row[col].values[0] if not row.empty else None

    countries_asean = sorted(df_asean['country'].unique())
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
with st.spinner("Loading UN Comtrade data. This may take a moment on first load..."):
    df_global       = load_global_data()
    df_global_equip = load_global_equip_data()
    df_equip        = load_asean_equip()
    df_chips        = load_asean_chips()

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("Controls")
st.sidebar.markdown("### IC Exporters")
st.sidebar.caption("Applies to the IC section of Tab 1.")
selected_countries = []
for country, hex_c in src_hex.items():
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
tab1, tab2, tab3 = st.tabs([
    "🌍  Global Supply Chain",
    "🏭  ASEAN Value Chain",
    "🏢  Company Supply Chain Atlas",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GLOBAL SUPPLY CHAIN
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.title("Global Semiconductor Trade Flows")

    coords_df = (
        pd.DataFrame.from_dict(country_coords, orient='index', columns=['lat','lon'])
        .reset_index().rename(columns={'index':'ISO'})
    )

    # ══ SECTION 1 — INTEGRATED CIRCUITS (HS 8542) ════════════════════════════
    st.header("🔬 Integrated Circuits (HS 8542)")
    st.caption(
        "Exports from major IC-exporting nations. "
        "Left = exporters, right = importers. "
        "Arc width proportional to export value. Data: UN Comtrade."
    )
    st.markdown(
        "> **Why these countries?** These six nations account for the majority of global IC exports. "
        "**Taiwan** (TSMC, MediaTek), **South Korea** (Samsung Electronics, SK Hynix), "
        "**China** (SMIC, Hua Hong Semiconductor), **USA** (Intel, Texas Instruments), "
        "**Japan** (Renesas, Kioxia, Sony Semiconductor), "
        "**Netherlands** (NXP Semiconductors)."
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
        df_year['color']     = df_year['reporterDesc'].map(country_rgba)
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
        st.info("Select at least one IC exporter in the sidebar to display the map.")

    st.markdown("---")
    st.subheader("IC exporters to importers")
    st.caption(
        "Left: 6 major IC-exporting nations. "
        "Right: their top 8 importing countries for the selected year (excluding other exporters)."
    )

    producer_set = set(IC_EXPORTERS)
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
        st.plotly_chart(build_sankey_fig(df_sk, src_hex), width='stretch')
    else:
        st.info("Select at least one IC exporter in the sidebar to display the Sankey.")

    st.markdown("---")
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
        "Left = exporters, right = importers. Data: UN Comtrade."
    )
    st.markdown(
        "> **Why these countries?** These five nations control the critical tooling that every chip fab depends on. "
        "**Netherlands** (ASML, sole maker of EUV lithography), "
        "**USA** (Applied Materials, Lam Research, KLA), "
        "**Japan** (Tokyo Electron, Nikon, Canon, Advantest), "
        "**Germany** (Carl Zeiss, whose optics are inside every ASML machine; Aixtron), "
        "**South Korea** (Samsung's equipment division, Jusung Engineering)."
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
    producer_set_eq = set(EQUIP_EXPORTERS)
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
        df_eq_year['color']     = df_eq_year['reporterDesc'].map(country_rgba)
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
    st.subheader("Equipment exporters to importers")
    st.caption(
        "Left: 5 major equipment-exporting nations. "
        "Right: their top 8 importing countries for the selected year (excluding other exporters)."
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
        st.plotly_chart(build_sankey_fig(df_sk_eq, equip_src_hex), width='stretch')
    else:
        st.info("Select at least one equipment exporter in the sidebar to display the Sankey.")

    st.markdown("---")
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


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPANY SUPPLY CHAIN ATLAS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.title("Company-Level Supply Chain Atlas")
    st.caption(
        "Revenue flows between named companies across five layers of the semiconductor supply chain. "
        "FY2024/25 annual report data, 105 flows, 46 nodes."
    )

    st.info(
        "**Reading the chart** — Node width = revenue flowing through that company. "
        "Named chip designers (Nvidia, AMD, etc.) show their **total disclosed revenue**, "
        "not just the portion modelled here. "
        "The gap between a node's inflow (what it pays suppliers) and its outflow "
        "(what customers pay it) is the company's **value-add**: design IP, process R&D, "
        "software stack, and margin. Hover any node or link for source citations.",
        icon="ℹ️"
    )

    # ── Load atlas data ────────────────────────────────────────────────────
    try:
        df_sc, meta_sc = load_sankey_data()
    except FileNotFoundError:
        st.error(
            "Atlas data files not found. "
            "Place **semi_supply_chain_sankey_v2.csv** and **node_metadata_v2.csv** "
            "in the same folder as app.py, then restart."
        )
        st.stop()

    # ── Build node arrays ──────────────────────────────────────────────────
    nodes_sc = sorted(set(df_sc["source"]) | set(df_sc["target"]))
    n_idx_sc = {n: i for i, n in enumerate(nodes_sc)}

    def get_meta_sc(col, default):
        return [
            meta_sc.loc[n, col] if n in meta_sc.index else default
            for n in nodes_sc
        ]

    node_colors_sc = get_meta_sc("color_hex", "#64748B")
    node_x_sc = [
        max(0.001, min(0.999, float(v)))
        for v in get_meta_sc("x_position_hint", 0.5)
    ]
    # EDA/IP to leftmost column — long ribbons to chip designers (YouTube style)
    for i, n in enumerate(nodes_sc):
        if n in {"Arm Holdings", "Synopsys", "Cadence"}:
            node_x_sc[i] = 0.01

    # ── Labels: use actual disclosed revenues for named companies ──────────
    outflow_sc = df_sc.groupby("source")["value_usd_bn"].sum().to_dict()
    inflow_sc  = df_sc.groupby("target")["value_usd_bn"].sum().to_dict()

    def node_label_sc(n):
        # Named companies: show actual disclosed revenue
        if n in DISCLOSED_REVENUE:
            return f"{n}\n${DISCLOSED_REVENUE[n]:.0f}B"
        # Aggregate/residual nodes: show flow value
        val = outflow_sc.get(n) or inflow_sc.get(n) or 0
        return f"{n}\n${val:.0f}B"

    def node_hover_sc(n):
        if n not in meta_sc.index:
            return f"<b>{n}</b>"
        cat   = meta_sc.loc[n, "node_category"]
        ann   = str(meta_sc.loc[n, "annotation"]).strip()
        title = str(meta_sc.loc[n, "annotation_title"]).strip()
        src   = str(meta_sc.loc[n, "annotation_source"]).strip()
        rev   = DISCLOSED_REVENUE.get(n)
        base  = f"<b>{n}</b><br><span style='color:#94a3b8'>{cat}</span>"
        if rev:
            base += f"<br>Disclosed revenue: <b>${rev:.1f}B</b>"
        if ann and ann != "nan":
            return (
                f"{base}<br><br><i>{title}</i><br>"
                f"{ann.replace(chr(10), '<br>')}<br><br>"
                f"<span style='color:#64748b;font-size:10px'>{src}</span>"
            )
        return base

    node_labels_sc     = [node_label_sc(n) for n in nodes_sc]
    node_hover_text_sc = [node_hover_sc(n) for n in nodes_sc]

    # ── Build figure ───────────────────────────────────────────────────────
    BG = "#07071a"

    fig_atlas = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label         = node_labels_sc,
            color         = node_colors_sc,
            x             = node_x_sc,
            pad           = 20,
            thickness     = 22,
            line          = dict(color="rgba(0,0,0,0)", width=0),
            hovertemplate = "%{customdata}<extra></extra>",
            customdata    = node_hover_text_sc,
        ),
        link=dict(
            source        = df_sc["source"].map(n_idx_sc).tolist(),
            target        = df_sc["target"].map(n_idx_sc).tolist(),
            value         = df_sc["value_usd_bn"].tolist(),
            color         = df_sc["link_color_rgba"].tolist(),
            hovertemplate = (
                "<b>%{source.label}  →  %{target.label}</b><br>"
                "$%{value:.1f}B<br>"
                "Confidence: %{customdata[0]}<br>"
                "Source: %{customdata[1]}<extra></extra>"
            ),
            customdata = df_sc[["confidence_level", "source_document"]].values.tolist(),
        ),
    ))

    fig_atlas.update_layout(
        title=dict(
            text=(
                "Semiconductor Supply Chain — FY2024/25"
                "<br><span style='font-size:13px;color:#94a3b8'>"
                "Link colour = source node category  ·  "
                "Hover nodes/links for citations and segment data"
                "</span>"
            ),
            font=dict(color="black", size=18, family="Arial Black, Arial"),
            x=0.5, xanchor="center",
        ),
        font          = dict(color="black", size=10, family="Arial"),
        height        = 980,
        margin        = dict(l=10, r=10, t=100, b=60),
    )

    # Column headers
    for x_pos, label in [
        (0.01, "Component Tools"),
        (0.23, "Advanced Tools"),
        (0.56, "Fabricators"),
        (0.88, "Chip Designers"),
    ]:
        fig_atlas.add_annotation(
            x=x_pos, y=1.055, xref="paper", yref="paper",
            text=f"<b>{label}</b>", showarrow=False,
            font=dict(color="#94a3b8", size=13, family="Arial"),
        )

    # Colour legend
    legend_items = [
        ("#8B5CF6", "Precision Sub-Components"),
        ("#F59E0B", "Process Control"),
        ("#D97706", "Raw Materials & Wafers"),
        ("#06B6D4", "Semiconductor Equipment"),
        ("#6366F1", "EDA & IP"),
        ("#EC4899", "Logic Fabs"),
        ("#14B8A6", "Memory Fabs"),
        ("#84CC16", "Chip Designers"),
        ("#64748B", "Aggregates"),
    ]
    for i, (col, lbl) in enumerate(legend_items):
        fig_atlas.add_annotation(
            x=i * 0.115, y=-0.05, xref="paper", yref="paper",
            text=f"<span style='color:{col}'>■</span> {lbl}",
            showarrow=False, xanchor="left",
            font=dict(color="#94a3b8", size=9, family="Arial"),
        )

    st.plotly_chart(fig_atlas, width='stretch')

    # ── Data quality note ──────────────────────────────────────────────────
    with st.expander("📊 Data quality breakdown"):
        conf_counts = df_sc["confidence_level"].value_counts().reset_index()
        conf_counts.columns = ["Confidence Level", "Flow Count"]
        conf_counts["% of flows"] = (conf_counts["Flow Count"] / len(df_sc) * 100).round(1)

        CONF_COLORS = {
            "DIRECTLY_DISCLOSED":          "#14B8A6",
            "DIRECTLY_DISCLOSED_FLOOR":    "#06B6D4",
            "DIRECTLY_DISCLOSED_RESIDUAL": "#6366F1",
            "INFERRED":                    "#F59E0B",
            "ANALYST_ESTIMATE":            "#EC4899",
            "ANALYST_ESTIMATE_RESIDUAL":   "#EF4444",
        }

        def style_conf(val):
            c = CONF_COLORS.get(val, "#94a3b8")
            return f"background-color:{c}20; color:{c}; font-weight:bold"

        st.dataframe(
            conf_counts.style.map(style_conf, subset=["Confidence Level"]),
            width="stretch",
        )
        st.caption(
            "**Teal/cyan/indigo** = hard data from public filings.  "
            "**Amber** = percentage disclosed, company identity inferred from consensus.  "
            "**Pink/red** = analyst estimates from geographic/application proxies."
        )
