import streamlit as st
import comtradeapicall as comtrade
import pandas as pd
import pydeck as pdk
import plotly.express as px

st.set_page_config(page_title="Global Semiconductor Trade Flows", layout="wide")
st.title("Global Semiconductor Trade Flows (HS 8542)")
st.caption(
    "Integrated circuit exports from major semiconductor-producing nations, 2018–2024. "
    "Data: UN Comtrade. Arc width proportional to export value."
)

# ── Data loading ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Fetching data from UN Commtrade...")
def load_data():
    subscription_key = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2025))

    df_raw = comtrade.getFinalData(
        subscription_key,
        typeCode='C', freqCode='A', clCode='HS',
        period=years,
        reporterCode='156,490,410,528,842,392',
        cmdCode='8542', flowCode='X',
        partnerCode=None, partner2Code=None,
        customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON',
        aggregateBy=None, breakdownMode='classic',
        countOnly=None, includeDesc=True
    )

    cols = ['reporterDesc', 'reporterISO', 'partnerDesc',
            'partnerISO', 'period', 'primaryValue']
    df = df_raw[cols].copy()
    df = df[df['partnerISO'] != 'W00']
    df['reporterDesc'] = df['reporterDesc'].replace('Other Asia, nes', 'Taiwan')
    df['partnerDesc']  = df['partnerDesc'].replace('Other Asia, nes', 'Taiwan')
    df['primaryValue'] = pd.to_numeric(df['primaryValue'], errors='coerce')
    return df

# ── Constants ──────────────────────────────────────────────────────────────
country_coords = {
    'CHN': (35.8617,  104.1954), 'TWN': (23.6978,  120.9605),
    'KOR': (35.9078,  127.7669), 'NLD': (52.1326,    5.2913),
    'USA': (37.0902,  -95.7129), 'JPN': (36.2048,  138.2529),
    'HKG': (22.3193,  114.1694), 'VNM': (14.0583,  108.2772),
    'SGP': ( 1.3521,  103.8198), 'MYS': ( 4.2105,  101.9758),
    'MEX': (23.6345, -102.5528), 'PHL': (12.8797,  121.7740),
    'DEU': (51.1657,   10.4515), 'GBR': (55.3781,   -3.4360),
    'IND': (20.5937,   78.9629), 'THA': (15.8700,  100.9925),
    'IDN': (-0.7893,  113.9213), 'IRL': (53.1424,   -7.6921),
    'BRA': (-14.235,  -51.9253), 'AUS': (-25.274,  133.7751),
    'CZE': (49.8175,   15.4730), 'ISR': (31.0461,   34.8516),
    'POL': (51.9194,   19.1451), 'SAU': (23.8859,   45.0792),
}

colour_map = {
    'Taiwan':        [0,   180, 255, 200],
    'Rep. of Korea': [0,   255, 140, 200],
    'China':         [255,  80,  80, 200],
    'Netherlands':   [255, 165,   0, 200],
    'USA':           [180,   0, 255, 200],
    'Japan':         [255, 255,   0, 200],
}

hex_colours = {
    country: '#{:02x}{:02x}{:02x}'.format(*c[:3])
    for country, c in colour_map.items()
}

# ── Load and prepare arc data ──────────────────────────────────────────────
df = load_data()

coords_df = pd.DataFrame.from_dict(
    country_coords, orient='index', columns=['lat', 'lon']
).reset_index().rename(columns={'index': 'ISO'})

df_arcs = df.merge(
    coords_df.rename(columns={'ISO': 'reporterISO', 'lat': 'source_lat', 'lon': 'source_lon'}),
    on='reporterISO', how='inner'
).merge(
    coords_df.rename(columns={'ISO': 'partnerISO', 'lat': 'target_lat', 'lon': 'target_lon'}),
    on='partnerISO', how='inner'
)

top_partners = (
    df_arcs.groupby('partnerISO')['primaryValue']
    .sum().sort_values(ascending=False).head(15).index.tolist()
)
df_arcs = df_arcs[df_arcs['partnerISO'].isin(top_partners)]
df_arcs = df_arcs[df_arcs['target_lat'] < 60]
df_arcs = df_arcs.groupby([
    'reporterDesc', 'reporterISO', 'partnerDesc', 'partnerISO',
    'period', 'source_lat', 'source_lon', 'target_lat', 'target_lon'
])['primaryValue'].sum().reset_index()

# ── Sidebar — country toggles ──────────────────────────────────────────────
st.sidebar.markdown("## Filter Countries")
st.sidebar.markdown("Toggle countries on or off to isolate specific flows.")
st.sidebar.markdown("")

selected_countries = []
for country, hex_c in hex_colours.items():
    checked = st.sidebar.checkbox(
        label=country,
        value=True,
        key=f"toggle_{country}"
    )
    if checked:
        selected_countries.append(country)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Source:** UN Comtrade  \n"
    "**Product:** HS 8542 — Electronic integrated circuits  \n"
    "**Flow:** Exports  \n"
    "**Coverage:** 2018–2024"
)

# ── Year slider ────────────────────────────────────────────────────────────
year = st.slider("Select year", 2018, 2024, 2023)

# ── Filter to selected year and countries ──────────────────────────────────
df_year     = df_arcs[
    (df_arcs['period'] == str(year)) &
    (df_arcs['reporterDesc'].isin(selected_countries))
].copy()

df_year_all = df[df['period'] == str(year)]
df_prev_all = df[df['period'] == str(year - 1)] if year > 2018 else None

def fmt(val):
    if val >= 1e12:
        return f"${val/1e12:.2f}T"
    elif val >= 1e9:
        return f"${val/1e9:.1f}B"
    else:
        return f"${val/1e6:.0f}M"

# ── Metrics cards ──────────────────────────────────────────────────────────
total_cur    = df_year_all['primaryValue'].sum()
total_prev   = df_prev_all['primaryValue'].sum() if df_prev_all is not None else None
taiwan_val   = df_year_all[df_year_all['reporterDesc'] == 'Taiwan']['primaryValue'].sum()
taiwan_share = taiwan_val / total_cur * 100 if total_cur > 0 else 0
china_val    = df_year_all[df_year_all['reporterDesc'] == 'China']['primaryValue'].sum()
china_share  = china_val / total_cur * 100 if total_cur > 0 else 0

yoy_delta = (
    f"{((total_cur - total_prev) / total_prev * 100):+.1f}% YoY"
    if total_prev else None
)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total IC Exports", fmt(total_cur), delta=yoy_delta)
with col2:
    st.metric("Taiwan's Share", f"{taiwan_share:.1f}%")
with col3:
    st.metric("China's Share", f"{china_share:.1f}%")

st.markdown("---")

# ── Arc map ────────────────────────────────────────────────────────────────
if selected_countries:
    df_year['color']     = df_year['reporterDesc'].map(colour_map)
    max_val              = df_year['primaryValue'].max()
    df_year['width']     = (df_year['primaryValue'] / max_val * 25).clip(lower=2)
    df_year['value_fmt'] = df_year['primaryValue'].apply(fmt)

    arc_layer = pdk.Layer(
        'ArcLayer', data=df_year,
        get_source_position=['source_lon', 'source_lat'],
        get_target_position=['target_lon', 'target_lat'],
        get_source_color='color', get_target_color='color',
        get_width='width', pickable=True, auto_highlight=True,
    )

    view = pdk.ViewState(latitude=25, longitude=60, zoom=2, pitch=20)

    st.pydeck_chart(pdk.Deck(
        layers=[arc_layer],
        initial_view_state=view,
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        tooltip={'text': '{reporterDesc} → {partnerDesc}\n{value_fmt}'}
    ))
else:
    st.info("Select at least one country in the sidebar to display the map.")

st.markdown("---")

# ── Time series chart ──────────────────────────────────────────────────────
st.subheader("IC Export Trends by Country (2018–2024)")

df_trend = (
    df.groupby(['reporterDesc', 'period'])['primaryValue']
    .sum()
    .reset_index()
)
df_trend['period']  = df_trend['period'].astype(int)
df_trend['value_B'] = df_trend['primaryValue'] / 1e9

# Filter trend chart to match selected countries
df_trend = df_trend[df_trend['reporterDesc'].isin(selected_countries)]

fig = px.line(
    df_trend,
    x='period', y='value_B',
    color='reporterDesc',
    markers=True,
    labels={
        'value_B':      'Export Value (USD Billion)',
        'period':       'Year',
        'reporterDesc': 'Country'
    },
    color_discrete_map=hex_colours,
)

fig.add_vline(x=year,   line_dash='dot',  line_color='white',   opacity=0.4)
fig.add_vline(x=2022,   line_dash='dash', line_color='#FF4444', opacity=0.8)
fig.add_annotation(
    x=2022.05,
    y=df_trend['value_B'].max() * 0.95 if not df_trend.empty else 1,
    text="US Export Controls<br>Oct 2022",
    showarrow=False,
    font=dict(color='#FF4444', size=11),
    xanchor='left',
)

fig.update_layout(
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)',
    font_color='white',
    legend_title='Country',
    xaxis=dict(tickmode='linear', dtick=1, gridcolor='rgba(255,255,255,0.1)'),
    yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
    hovermode='x unified',
    margin=dict(t=20),
)

st.plotly_chart(fig, use_container_width=True)
