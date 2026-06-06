import streamlit as st
import comtradeapicall as comtrade
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="Global Semiconductor Trade Flows", layout="wide")
st.title("Global Semiconductor Trade Flows (HS 8542)")
st.caption("Integrated circuit exports from major producing nations, 2018–2024")

# ── Data loading ───────────────────────────────────────────────────────────
@st.cache_data
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

# ── Controls ───────────────────────────────────────────────────────────────
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

year = st.slider("Select year", 2018, 2024, 2023)

df_year = df_arcs[df_arcs['period'] == str(year)].copy()
df_year['color'] = df_year['reporterDesc'].map(colour_map)
max_val = df_year['primaryValue'].max()
df_year['width'] = (df_year['primaryValue'] / max_val * 25).clip(lower=2)

# ── Map ────────────────────────────────────────────────────────────────────
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
    tooltip={'text': '{reporterDesc} → {partnerDesc}\n${primaryValue}'}
))

# ── Legend ─────────────────────────────────────────────────────────────────
st.sidebar.markdown("## Legend")
for country, colour in colour_map.items():
    hex_colour = '#{:02x}{:02x}{:02x}'.format(*colour[:3])
    st.sidebar.markdown(
        f'<span style="color:{hex_colour}">■</span> {country}',
        unsafe_allow_html=True
    )