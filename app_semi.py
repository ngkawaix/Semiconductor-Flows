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
    years = ','.join(str(y) for y in range(2018, 2025))
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
def load_asean_equip():
    """HS 8486 semiconductor equipment imports — forward-looking investment proxy."""
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2025))
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
    """HS 8542 IC exports from ASEAN — current export capability."""
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2025))
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

# ── Constants ──────────────────────────────────────────────────────────────
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

colour_map = {
    'Taiwan':       [0,180,255,200], 'Rep. of Korea':[0,255,140,200],
    'China':        [255,80,80,200], 'Netherlands':  [255,165,0,200],
    'USA':          [180,0,255,200], 'Japan':        [255,255,0,200],
}

hex_colours = {c:'#{:02x}{:02x}{:02x}'.format(*v[:3]) for c,v in colour_map.items()}

status_colours = {
    'Rising Hub':'#00FF8C','Assembly Dependent':'#FFD700',
    'Emerging':  '#00B4FF','Lagging':           '#FF5050',
}

def fmt(val):
    if pd.isna(val):      return 'N/A'
    if val >= 1e12:       return f"${val/1e12:.2f}T"
    elif val >= 1e9:      return f"${val/1e9:.1f}B"
    else:                 return f"${val/1e6:.0f}M"

def cagr(start, end, n):
    if pd.notna(start) and pd.notna(end) and start > 0 and end > 0 and n > 0:
        return round(((end/start)**(1/n)-1)*100, 1)
    return None

# ── Load all data ──────────────────────────────────────────────────────────
with st.spinner("Loading UN Comtrade data — this may take a moment on first load..."):
    df_global = load_global_data()
    df_equip  = load_asean_equip()
    df_chips  = load_asean_chips()

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("Controls")
st.sidebar.markdown("### Filter Countries")
st.sidebar.caption("Applies to the Global Supply Chain tab.")

selected_countries = []
for country, hex_c in hex_colours.items():
    if st.sidebar.checkbox(country, value=True, key=f"toggle_{country}"):
        selected_countries.append(country)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Source:** UN Comtrade  \n"
    "**Products:** HS 8486 (equipment), HS 8542 (ICs)  \n"
    "**Coverage:** 2018–2024  \n"
    "**Flow:** Exports (global), Imports/Exports (ASEAN)"
)

# ── Tabs ───────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🌍  Global Supply Chain", "🌏  ASEAN Value Chain"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GLOBAL SUPPLY CHAIN
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.title("Global Semiconductor Trade Flows (HS 8542)")
    st.caption(
        "Integrated circuit exports from major producing nations, 2018–2024. "
        "Arc width proportional to export value. Data: UN Comtrade."
    )

    # ── Prepare arc data ───────────────────────────────────────────────────
    coords_df = (
        pd.DataFrame.from_dict(country_coords, orient='index', columns=['lat','lon'])
        .reset_index().rename(columns={'index':'ISO'})
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

    # ── Year slider ────────────────────────────────────────────────────────
    year = st.slider("Select year", 2018, 2024, 2023)

    # ── Filter ────────────────────────────────────────────────────────────
    df_year     = df_arcs[(df_arcs['period']==str(year)) & (df_arcs['reporterDesc'].isin(selected_countries))].copy()
    df_year_all = df_global[df_global['period']==str(year)]
    df_prev_all = df_global[df_global['period']==str(year-1)] if year > 2018 else None

    total_cur    = df_year_all['primaryValue'].sum()
    total_prev   = df_prev_all['primaryValue'].sum() if df_prev_all is not None else None
    taiwan_share = df_year_all[df_year_all['reporterDesc']=='Taiwan']['primaryValue'].sum() / total_cur * 100
    china_share  = df_year_all[df_year_all['reporterDesc']=='China']['primaryValue'].sum()  / total_cur * 100
    yoy          = f"{((total_cur-total_prev)/total_prev*100):+.1f}% YoY" if total_prev else None

    # ── Metrics ────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("Total IC Exports",  fmt(total_cur),          delta=yoy)
    c2.metric("Taiwan's Share",    f"{taiwan_share:.1f}%")
    c3.metric("China's Share",     f"{china_share:.1f}%")
    st.markdown("---")

    # ── Arc map ────────────────────────────────────────────────────────────
    if selected_countries and not df_year.empty:
        df_year['color']     = df_year['reporterDesc'].map(colour_map)
        df_year['width']     = (df_year['primaryValue'] / df_year['primaryValue'].max() * 25).clip(lower=2)
        df_year['value_fmt'] = df_year['primaryValue'].apply(fmt)

        st.pydeck_chart(pdk.Deck(
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
        ))
    else:
        st.info("Select at least one country in the sidebar to display the map.")

    st.markdown("---")

    # ── Time series ────────────────────────────────────────────────────────
    st.subheader("IC Export Trends by Country (2018–2024)")
    df_trend = (
        df_global[df_global['reporterDesc'].isin(selected_countries)]
        .groupby(['reporterDesc','period'])['primaryValue'].sum().reset_index()
    )
    df_trend['period']  = df_trend['period'].astype(int)
    df_trend['value_B'] = df_trend['primaryValue'] / 1e9

    fig_ts = px.line(
        df_trend, x='period', y='value_B', color='reporterDesc', markers=True,
        labels={'value_B':'Export Value (USD Billion)','period':'Year','reporterDesc':'Country'},
        color_discrete_map=hex_colours,
    )
    fig_ts.add_vline(x=year, line_dash='dot',  line_color='white',   opacity=0.4)
    fig_ts.add_vline(x=2022, line_dash='dash', line_color='#FF4444', opacity=0.8)
    if not df_trend.empty:
        fig_ts.add_annotation(
            x=2022.05, y=df_trend['value_B'].max()*0.95,
            text="US Export Controls<br>Oct 2022", showarrow=False,
            font=dict(color='#FF4444', size=11), xanchor='left'
        )
    fig_ts.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font_color='white', legend_title='Country', hovermode='x unified',
        xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)'), margin=dict(t=20),
    )
    st.plotly_chart(fig_ts, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ASEAN VALUE CHAIN
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.title("ASEAN Semiconductor Value Chain")
    st.caption(
        "Which ASEAN economies are moving up the semiconductor value chain? "
        "Equipment imports proxy investment; IC exports proxy current capability."
    )

    # ── Build summary table ────────────────────────────────────────────────
    df_asean = df_equip.merge(df_chips, on=['country','year'], how='outer')

    start_yr  = 2018
    end_yr    = df_asean['year'].max()
    n_yrs     = end_yr - start_yr

    def get_val(df, country, year, col):
        row = df[(df['country']==country) & (df['year']==year)]
        return row[col].values[0] if not row.empty else None

    countries = sorted(df_asean['country'].unique())
    summary   = pd.DataFrame(index=countries)

    for col, label_s, label_e, metric in [
        ('equip_imports', 'Equip Imports 2018 ($B)', 'Equip Imports Latest ($B)', 'Equip CAGR (%)'),
        ('chip_exports',  'Chip Exports 2018 ($B)',  'Chip Exports Latest ($B)',  'Chip Export CAGR (%)'),
    ]:
        vals_s = {c: get_val(df_asean, c, start_yr, col) for c in countries}
        vals_e = {c: get_val(df_asean, c, end_yr,   col) for c in countries}
        summary[label_s] = pd.Series(vals_s) / 1e9
        summary[label_e] = pd.Series(vals_e) / 1e9
        summary[metric]  = pd.Series({
            c: cagr(vals_s[c], vals_e[c], n_yrs) for c in countries
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

    # ── Styled table ───────────────────────────────────────────────────────
    st.subheader("Value Chain Positioning Table")

    def colour_status(val):
        c = {'Rising Hub':'#00FF8C','Assembly Dependent':'#FFD700',
             'Emerging':'#00B4FF','Lagging':'#FF5050'}.get(val,'')
        return f'background-color:{c}; color:black; font-weight:bold' if c else ''

    styled = (
        summary.style
        .map(colour_status, subset=['Status'])
        .format({
            'Equip Imports 2018 ($B)':    '${:.2f}B',
            'Equip Imports Latest ($B)':  '${:.2f}B',
            'Equip CAGR (%)':             '{:.1f}%',
            'Chip Exports 2018 ($B)':     '${:.2f}B',
            'Chip Exports Latest ($B)':   '${:.2f}B',
            'Chip Export CAGR (%)':       '{:.1f}%',
            'Value Chain Ratio':          '{:.2f}x',
        }, na_rep='N/A')
    )
    st.dataframe(styled, use_container_width=True)

    st.markdown("---")

    # ── 2x2 scatter plot ───────────────────────────────────────────────────
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
                size=(sub['Chip Exports Latest ($B)'].fillna(1).clip(lower=1)*3),
                color=colour, opacity=0.85,
                line=dict(width=1, color='white')
            )
        ))

    fig_scatter.add_hline(y=med_chips, line_dash='dash', line_color='white', opacity=0.3)
    fig_scatter.add_vline(x=med_equip, line_dash='dash', line_color='white', opacity=0.3)

    for label, xpos, ypos, colour in [
        ('Rising Hub',          0.95, 0.95, '#00FF8C'),
        ('Assembly Dependent',  0.05, 0.95, '#FFD700'),
        ('Emerging',            0.95, 0.05, '#00B4FF'),
        ('Lagging',             0.05, 0.05, '#FF5050'),
    ]:
        fig_scatter.add_annotation(
            xref='paper', yref='paper', x=xpos, y=ypos,
            text=label, showarrow=False,
            font=dict(color=colour, size=11), opacity=0.5
        )

    fig_scatter.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font_color='white', legend_title='Status',
        xaxis=dict(title='Equipment Import CAGR (%)', gridcolor='rgba(255,255,255,0.1)', zeroline=False),
        yaxis=dict(title='IC Export CAGR (%)',         gridcolor='rgba(255,255,255,0.1)', zeroline=False),
        margin=dict(t=20),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")

    # ── Trend lines ────────────────────────────────────────────────────────
    st.subheader("Equipment Imports vs IC Exports Over Time")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Semiconductor Equipment Imports (HS 8486)**")
        df_eq_trend = df_equip.copy()
        df_eq_trend['value_B'] = df_eq_trend['equip_imports'] / 1e9
        fig_eq = px.line(
            df_eq_trend, x='year', y='value_B', color='country',
            markers=True,
            labels={'value_B':'USD Billion','year':'Year','country':'Country'}
        )
        fig_eq.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            font_color='white', margin=dict(t=10),
            xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    with col_b:
        st.markdown("**IC Exports (HS 8542)**")
        df_ch_trend = df_chips.copy()
        df_ch_trend['value_B'] = df_ch_trend['chip_exports'] / 1e9
        fig_ch = px.line(
            df_ch_trend, x='year', y='value_B', color='country',
            markers=True,
            labels={'value_B':'USD Billion','year':'Year','country':'Country'}
        )
        fig_ch.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            font_color='white', margin=dict(t=10),
            xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        )
        st.plotly_chart(fig_ch, use_container_width=True)
