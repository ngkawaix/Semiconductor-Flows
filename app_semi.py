import streamlit as st
import comtradeapicall as comtrade
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import requests
import math
import numpy as np

st.set_page_config(
    page_title="Semiconductor Supply Chain Intelligence",
    layout="wide",
    page_icon="🔬"
)

# ── Data loading ───────────────────────────────────────────────────────────
# Canonical Comtrade → display name mapping applied uniformly across all loaders
_COMTRADE_RENAME = {
    'Other Asia, nes':      'Taiwan',        # Comtrade lists Taiwan under this code
    'China, Hong Kong SAR': 'Hong Kong',     # Shorten for map labels
    'Viet Nam':             'Vietnam',       # Localise spelling
}

@st.cache_data
def load_global_data():
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='156,490,410,842,392',
        cmdCode='8542', flowCode='X',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    cols = ['reporterDesc','reporterISO','partnerDesc','partnerISO','period','primaryValue']
    df   = df[cols].copy()
    df   = df[df['partnerISO'] != 'W00']
    df['reporterDesc'] = df['reporterDesc'].replace(_COMTRADE_RENAME)
    df['partnerDesc']  = df['partnerDesc'].replace(_COMTRADE_RENAME)
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
    df['reporterDesc'] = df['reporterDesc'].replace(_COMTRADE_RENAME)
    df['partnerDesc']  = df['partnerDesc'].replace(_COMTRADE_RENAME)
    df['primaryValue'] = pd.to_numeric(df['primaryValue'], errors='coerce')
    return df

@st.cache_data
def load_reexport_data():
    """HS 8542: IC exports from key intermediate re-export / transit hubs.
    These countries receive chips from primary exporters and onward-ship
    to final assembly markets. Showing their outbound flows reveals the
    second hop of the supply chain (Singapore → Mexico, HK → SE Asia, etc.)
    """
    key   = st.secrets["COMTRADE_KEY"]
    years = ','.join(str(y) for y in range(2018, 2026))
    df    = comtrade.getFinalData(
        key, typeCode='C', freqCode='A', clCode='HS', period=years,
        reporterCode='344,458,702,704',   # HKG, MYS, SGP, VNM
        cmdCode='8542', flowCode='X',
        partnerCode=None, partner2Code=None, customsCode=None, motCode=None,
        maxRecords=250000, format_output='JSON', aggregateBy=None,
        breakdownMode='classic', countOnly=None, includeDesc=True
    )
    cols = ['reporterDesc','reporterISO','partnerDesc','partnerISO','period','primaryValue']
    df   = df[cols].copy()
    df   = df[df['partnerISO'] != 'W00']
    df['reporterDesc'] = df['reporterDesc'].replace(_COMTRADE_RENAME)
    df['partnerDesc']  = df['partnerDesc'].replace(_COMTRADE_RENAME)
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
    df   = pd.read_csv("semi_supply_chain_sankey_v3.csv")
    meta = pd.read_csv("node_metadata_v3.csv").set_index("node_name")
    return df, meta

# ── Canonical colour palette ───────────────────────────────────────────────
# Single canonical palette used by BOTH maps, both projections, and every
# Sankey/time-series in Tab 1. Saturation chosen for legibility on the white
# ocean: pale tints (old Japan/Netherlands/Germany) are darkened.
country_hex = {
    'Taiwan':        '#1D91C0',   # blue
    'Rep. of Korea': '#0D9488',   # teal-600
    'China':         '#DC2626',   # red — explicit, for instant recognition
    'Netherlands':   '#EA580C',   # orange-600
    'USA':           '#225EA8',   # deep blue
    'Japan':         '#65A30D',   # lime-600
    'Germany':       '#7C3AED',   # violet-600
}
country_rgba = {
    'Taiwan':        [29,  145, 192, 210],
    'Rep. of Korea': [13,  148, 136, 210],
    'China':         [220,  38,  38, 210],
    'Netherlands':   [234,  88,  12, 210],
    'USA':           [34,   94, 168, 210],
    'Japan':         [101, 163,  13, 210],
    'Germany':       [124,  58, 237, 210],
}
IC_EXPORTERS    = ['China', 'Japan', 'Rep. of Korea', 'Taiwan', 'USA']
EQUIP_EXPORTERS = ['Germany', 'Japan', 'Netherlands', 'Rep. of Korea', 'USA']
src_hex       = {k: country_hex[k] for k in IC_EXPORTERS}
equip_src_hex = {k: country_hex[k] for k in EQUIP_EXPORTERS}

# ── Re-export hub palette ───────────────────────────────────────────────────
# Intermediate transit / OSAT hubs that receive chips from primary exporters
# and forward them to final assembly markets.  Distinct from the main palette.
REEXPORT_HUBS = ['Hong Kong', 'Malaysia', 'Singapore', 'Vietnam']   # alphabetical
hub_hex = {
    'Hong Kong': '#EC4899',   # pink-500
    'Malaysia':  '#10B981',   # emerald-500
    'Singapore': '#F59E0B',   # amber-500
    'Vietnam':   '#8B5CF6',   # purple-500
}
hub_rgba = {
    'Hong Kong': [236,  72, 153, 210],
    'Malaysia':  [ 16, 185, 129, 210],
    'Singapore': [245, 158,  11, 210],
    'Vietnam':   [139,  92, 246, 210],
}
# Unified lookup used by Sankey destination coloring so the SAME country
# always gets the same colour regardless of which Sankey it appears in.
ALL_COUNTRY_HEX = {**country_hex, **hub_hex}
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
    "Broadcom":          38.9,   # FY2025 semiconductor solutions only (excl. VMware/Infra Software; total $63.9B)
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
    # Batch 1 additions — Chip Designers
    "NXP Semiconductors": 12.9,  # FY2024
    "Marvell":             7.6,  # FY2026 (Feb 2026 YE); AI-driven growth
    "Texas Instruments":  15.6,  # FY2024; ~90% IDM (own fabs)
    # TI Fabs — internal manufacturing arm
    "TI Fabs":            15.6,  # same as TI (represents TI's own manufacturing base)
    # Sub-components
    "Zeiss SMT":           5.5,  # floor estimate
    "Entegris":            3.2,  # FY2024
    "SUMCO":               2.6,  # FY2024
    "MKS Instruments":     3.6,  # FY2024
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

# ── Flow-map rendering (Plotly geo) ─────────────────────────────────────────
# Implementation note: earlier versions used pydeck. The flat MapView broke
# flows at the antimeridian, and deck.gl's experimental _GlobeView could not
# reliably occlude flows on the far side of the planet (they bled through as
# phantom "latitude lines"). Plotly's geo projections solve both by
# construction: the orthographic globe CLIPS anything beyond the horizon,
# and it ships with built-in land/ocean styling — no external GeoJSON, no
# iframe, no basemap dependency. Both projections share one styling dict so
# the 2-D and 3-D views are always identical.

OCEAN_HEX  = "#FFFFFF"
LAND_HEX   = "#B9C4D1"
BORDER_HEX = "#FFFFFF"
FRAME_HEX  = "#E2E8F0"


def _wrap_lon(lon):
    return ((lon + 180.0) % 360.0) - 180.0


def _flow_path(lat1, lon1, lat2, lon2, bow_deg, n=60):
    """
    Quadratic Bezier from (lat1,lon1) to (lat2,lon2), bowed sideways by
    bow_deg degrees, returned as a list of (wrapped_lon, lat) tuples.

    Bezier formula (t goes 0 → 1 along the curve):
        P(t) = (1-t)^2 * P0  +  2(1-t)t * C  +  t^2 * P1
    where P0 = source, P1 = target, and C = control point = the midpoint
    pushed perpendicular to the straight line by bow_deg. Positive bow bows
    the curve to the LEFT of the direction of travel, so all flows share a
    consistent, organised sweep. The target longitude is first "unwrapped"
    to its nearest representation so trans-Pacific flows take the short way.
    """
    if lon2 - lon1 > 180:
        lon2 -= 360
    elif lon2 - lon1 < -180:
        lon2 += 360

    dx, dy = lon2 - lon1, lat2 - lat1
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return []

    px, py = -dy / dist, dx / dist
    cx = (lon1 + lon2) / 2 + px * bow_deg
    cy = (lat1 + lat2) / 2 + py * bow_deg

    pts = []
    for i in range(n + 1):
        t = i / n
        lon = (1 - t) ** 2 * lon1 + 2 * (1 - t) * t * cx + t ** 2 * lon2
        lat = (1 - t) ** 2 * lat1 + 2 * (1 - t) * t * cy + t ** 2 * lat2
        pts.append((_wrap_lon(lon), max(-85.0, min(85.0, lat))))
    return pts


def build_flow_fig(df, globe=True, height=620,
                   color_col='color', width_col='width'):
    """
    Build the full flow map as a Plotly geo figure:
      per flow — a soft halo line, a saturated core line, and an arrowhead
      marker at the destination (oriented along the path via angleref);
      plus exporter dots/labels and importer dots/labels.

    Flows converging on the same destination get staggered bow magnitudes
    (1.0×, 1.35×, 0.65×, 1.7× …) so the ribbons fan apart mid-flight
    instead of stacking into one rope.
    """
    fig = go.Figure()

    # Per-destination rank → bow multiplier (fan-out of converging flows)
    bow_mult = {}
    for _, grp in df.groupby('partnerISO'):
        grp_sorted = grp.sort_values(width_col, ascending=False)
        for rank, idx in enumerate(grp_sorted.index):
            step = (rank + 1) // 2 * 0.35
            bow_mult[idx] = 1.0 + step if rank % 2 == 1 else 1.0 - step

    flows = []
    for idx, row in df.iterrows():
        dlon = row['target_lon'] - row['source_lon']
        if dlon > 180:    dlon -= 360
        elif dlon < -180: dlon += 360
        dist = math.hypot(dlon, row['target_lat'] - row['source_lat'])
        bow  = max(1.2, min(dist * 0.12, 11.0)) * bow_mult.get(idx, 1.0)

        pts = _flow_path(row['source_lat'], row['source_lon'],
                         row['target_lat'], row['target_lon'], bow_deg=bow)
        if not pts:
            continue

        # Insert a None break where the wrapped path jumps the antimeridian
        lons, lats = [], []
        for j, (lon, lat) in enumerate(pts):
            if j and lons[-1] is not None and abs(lon - lons[-1]) > 180:
                lons.append(None); lats.append(None)
            lons.append(lon); lats.append(lat)

        r, g, b = list(row[color_col])[:3]
        flows.append(dict(
            lons=lons, lats=lats, rgb=(r, g, b),
            width=float(row[width_col]),
            hover=f"{row.get('reporterDesc','')} → {row.get('partnerDesc','')}"
                  f"<br><b>{row.get('value_fmt','')}</b>",
        ))

    for f in flows:                                            # halo pass
        r, g, b = f['rgb']
        fig.add_trace(go.Scattergeo(
            lon=f['lons'], lat=f['lats'], mode='lines',
            line=dict(width=f['width'] * 2.2, color=f"rgba({r},{g},{b},0.22)"),
            hoverinfo='skip', showlegend=False,
        ))
    for f in flows:                                            # core + arrow
        r, g, b = f['rgb']
        n = len(f['lons'])
        sizes = [0] * n
        sizes[-1] = max(9, f['width'] * 2.4 + 5)
        fig.add_trace(go.Scattergeo(
            lon=f['lons'], lat=f['lats'], mode='lines+markers',
            line=dict(width=f['width'], color=f"rgba({r},{g},{b},0.95)"),
            marker=dict(symbol='arrow', size=sizes, angleref='previous',
                        color=f"rgba({r},{g},{b},1)"),
            hoverinfo='text', text=f['hover'], showlegend=False,
        ))

    # ── Country anchors ─────────────────────────────────────────────────────
    exp_df = (
        df.groupby('reporterDesc')
        .agg(lon=('source_lon', 'first'), lat=('source_lat', 'first'),
             color=(color_col, 'first'), total=('primaryValue', 'sum'))
        .reset_index()
    )
    imp_df = (
        df.groupby('partnerDesc')
        .agg(lon=('target_lon', 'first'), lat=('target_lat', 'first'),
             total=('primaryValue', 'sum'))
        .reset_index()
    )
    imp_df = imp_df[~imp_df['partnerDesc'].isin(set(exp_df['reporterDesc']))]

    fig.add_trace(go.Scattergeo(                               # importers
        lon=imp_df['lon'], lat=imp_df['lat'],
        mode='markers+text',
        marker=dict(size=7, color='white',
                    line=dict(width=1.2, color='#334155')),
        text=imp_df['partnerDesc'], textposition='top center',
        textfont=dict(size=10, color='#475569', family='Arial'),
        hoverinfo='text',
        hovertext=[f"{r.partnerDesc} (importer)<br><b>{fmt(r.total)}</b> received"
                   for r in imp_df.itertuples()],
        showlegend=False,
    ))
    fig.add_trace(go.Scattergeo(                               # exporters
        lon=exp_df['lon'], lat=exp_df['lat'],
        mode='markers+text',
        marker=dict(size=13,
                    color=[f"rgb({c[0]},{c[1]},{c[2]})" for c in exp_df['color']],
                    line=dict(width=1.6, color='#0F172A')),
        text=exp_df['reporterDesc'], textposition='top center',
        textfont=dict(size=12, color='#0F172A', family='Arial Black, Arial'),
        hoverinfo='text',
        hovertext=[f"{r.reporterDesc} (exporter)<br><b>{fmt(r.total)}</b> total"
                   for r in exp_df.itertuples()],
        showlegend=False,
    ))

    # ── Shared geo styling — identical for both projections ────────────────
    proj = (dict(type='orthographic', rotation=dict(lon=115, lat=15, roll=0))
            if globe else dict(type='natural earth'))
    fig.update_layout(
        geo=dict(
            projection=proj,
            showland=True,      landcolor=LAND_HEX,
            showocean=True,     oceancolor=OCEAN_HEX,
            showcountries=True, countrycolor=BORDER_HEX, countrywidth=0.6,
            showcoastlines=False, showlakes=False, showrivers=False,
            showframe=False,
            bgcolor=FRAME_HEX,
        ),
        paper_bgcolor=FRAME_HEX,
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        showlegend=False,
        hoverlabel=dict(bgcolor='white', font=dict(color='#0F172A')),
        # Keep the user's rotation/zoom when widgets trigger a re-render
        uirevision='flow-map',
    )
    return fig


_YLGNBU_DEST = ['#225ea8','#1d91c0','#41b6c4','#7fcdbb','#c7e9b4','#edf8b1','#ffffd9','#f7fcb9']

def build_sankey_fig(df_flow, hex_palette):
    src_nodes = list(df_flow['reporterDesc'].unique())
    tgt_nodes = list(df_flow['partnerDesc'].unique())
    all_nodes = src_nodes + tgt_nodes
    node_idx  = {n: i for i, n in enumerate(all_nodes)}
    n_tgt = len(tgt_nodes)

    # Destination node colours: use the canonical country palette for any
    # country we recognise (so China is always red, Korea always teal, etc.
    # across BOTH the IC and Equipment Sankeys), then fall back to the
    # YlGnBu sequential palette for all-other importers.
    _fb_idx = 0
    tgt_colors = []
    for t in tgt_nodes:
        if t in ALL_COUNTRY_HEX:
            tgt_colors.append(ALL_COUNTRY_HEX[t])
        else:
            tgt_colors.append(_YLGNBU_DEST[_fb_idx % len(_YLGNBU_DEST)])
            _fb_idx += 1

    node_colors = (
        [hex_palette.get(n, '#888888') for n in src_nodes] +
        tgt_colors
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
    df_reexport     = load_reexport_data()   # IC exports from intermediate hubs (SGP, HKG, MYS, VNM)

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("Controls")

st.sidebar.markdown("---")
st.sidebar.markdown("### Select Year")
st.sidebar.caption("Applies to the global map and all tabs.")
year = st.sidebar.slider("Year", 2018, 2025, 2024, label_visibility="collapsed")

projection = st.sidebar.radio(
    "Projection",
    ["🌐 3D Globe", "🗺️ Flat Map"],
    index=0,
    help="The globe is continuous, so trans-Pacific flows are never cut off. Drag to rotate.",
)
use_globe = projection.endswith("Globe")

st.sidebar.markdown("---")
st.sidebar.markdown("### IC Exporters")
st.sidebar.caption(
    "Toggles IC export flows (HS 8542) from top IC exporters to importers. "
)
selected_countries = []
for country in IC_EXPORTERS:          # alphabetical: China, Japan, Korea, Taiwan, USA
    hex_c = src_hex[country]
    if st.sidebar.checkbox(country, value=True, key=f"toggle_{country}"):
        selected_countries.append(country)

st.sidebar.markdown("### IC Re-exports Hubs")
st.sidebar.caption(
    "Overlay IC re-export flows (HS 8542) from key intermediate hubs onto the IC map. "
    "These countries receive chips from primary exporters and forward them to final "
    "assembly markets — revealing the second hop of the supply chain."
)
selected_hubs = []
for hub in REEXPORT_HUBS:             # alphabetical: Hong Kong, Malaysia, Singapore, Vietnam
    colour_swatch = hub_hex[hub]
    if st.sidebar.checkbox(hub, value=False, key=f"hub_{hub}"):
        selected_hubs.append(hub)

st.sidebar.markdown("---")
st.sidebar.markdown("### Equipment Exporters")
st.sidebar.caption("Applies to the Equipment section of Tab 1.")
selected_equip_countries = []
for country in EQUIP_EXPORTERS:       # alphabetical: Germany, Japan, Netherlands, Korea, USA
    hex_c = equip_src_hex[country]
    if st.sidebar.checkbox(country, value=True, key=f"eq_toggle_{country}"):
        selected_equip_countries.append(country)

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
        "> **Why these countries?** These five nations account for the majority of global IC exports. "
        "**Taiwan** (TSMC, MediaTek), **South Korea** (Samsung Electronics, SK Hynix), "
        "**China** (SMIC, Hua Hong Semiconductor), **USA** (Intel, Texas Instruments), "
        "**Japan** (Renesas, Kioxia, Sony Semiconductor). "
        "The Netherlands appears in the Equipment section below instead — its semiconductor "
        "story is ASML's lithography monopoly, not chip exports."
    )

    df_arcs = (
        df_global
        .merge(coords_df.rename(columns={'ISO':'reporterISO','lat':'source_lat','lon':'source_lon'}), on='reporterISO', how='inner')
        .merge(coords_df.rename(columns={'ISO':'partnerISO', 'lat':'target_lat', 'lon':'target_lon'}), on='partnerISO',  how='inner')
    )
    # All partner flows are kept — no top-N truncation (small flows like
    # equipment to Singapore or Malaysia matter to the ASEAN story).
    df_arcs = (
        df_arcs
        .groupby(['reporterDesc','reporterISO','partnerDesc','partnerISO',
                  'period','source_lat','source_lon','target_lat','target_lon'])
        ['primaryValue'].sum().reset_index()
    )

    df_year     = df_arcs[(df_arcs['period']==str(year)) & (df_arcs['reporterDesc'].isin(selected_countries))].copy()

    # ── Map ↔ Sankey consistency ────────────────────────────────────────────
    # The map keeps the YEAR's top-15 partners (beyond that, marginal utility
    # is low and the map clutters), UNIONED with the destinations the Sankey
    # below will show for the same year — so any flow visible in the Sankey
    # (e.g. Netherlands → Singapore on the equipment side) is guaranteed to
    # also appear on the map. Note the Sankey excludes exporter nations from
    # its destination side by design; the map keeps them (e.g. flows INTO
    # China and into China, Hong Kong SAR), since geography is the point here.
    sankey_dest_ic = set(
        df_global[(df_global['period'] == str(year)) &
                  (df_global['reporterDesc'].isin(selected_countries)) &
                  (~df_global['partnerDesc'].isin(set(IC_EXPORTERS)))]
        .groupby('partnerDesc')['primaryValue'].sum().nlargest(8).index
    )
    top15_ic = set(
        df_year.groupby('partnerISO')['primaryValue'].sum().nlargest(15).index
    )
    df_year = df_year[
        df_year['partnerISO'].isin(top15_ic) |
        df_year['partnerDesc'].isin(sankey_dest_ic)
    ].copy()

    # Diagnostic: partners that can never appear on the map because they have
    # no entry in the coordinates table (the coords merge is an inner join).
    _ic_known = set(coords_df['ISO'])
    _ic_missing = (
        df_global[(df_global['period'] == str(year)) &
                  (df_global['reporterDesc'].isin(selected_countries)) &
                  (~df_global['partnerISO'].isin(_ic_known))]
        .groupby('partnerDesc')['primaryValue'].sum().nlargest(5)
    )
    if not _ic_missing.empty and _ic_missing.iloc[0] > 1e9:
        st.caption(
            "⚠️ Not mappable (no coordinates on file): "
            + ", ".join(f"{k} ({fmt(v)})" for k, v in _ic_missing.items())
        )
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
        df_year['color'] = df_year['reporterDesc'].map(country_rgba)
        # Square-root scaling keeps large flows readable without drowning small
        # ones. Normalised against the ALL-YEARS maximum so ribbon widths are
        # comparable when scrubbing the year slider (a $50B flow looks the same
        # in 2019 and 2025).
        global_max_ic = df_arcs['primaryValue'].max()
        df_year['width'] = (np.sqrt(df_year['primaryValue'] / global_max_ic) * 6).clip(lower=1.0)
        df_year['value_fmt'] = df_year['primaryValue'].apply(fmt)

        # ── Re-export hub overlay ─────────────────────────────────────────
        # When hubs are toggled on, build their outbound arc dataset and
        # layer it on top of the primary exporter flows.  Same global_max_ic
        # normalisation ensures hub ribbons are visually proportional
        # (hub volumes are smaller, so arcs naturally appear thinner).
        df_hub_ic = pd.DataFrame()
        if selected_hubs and not df_reexport.empty:
            _hub_arcs = (
                df_reexport
                .merge(
                    coords_df.rename(columns={'ISO':'reporterISO','lat':'source_lat','lon':'source_lon'}),
                    on='reporterISO', how='inner'
                )
                .merge(
                    coords_df.rename(columns={'ISO':'partnerISO','lat':'target_lat','lon':'target_lon'}),
                    on='partnerISO', how='inner'
                )
                .groupby(['reporterDesc','reporterISO','partnerDesc','partnerISO',
                          'period','source_lat','source_lon','target_lat','target_lon'])
                ['primaryValue'].sum().reset_index()
            )
            _hub_yr = _hub_arcs[
                (_hub_arcs['period'] == str(year)) &
                (_hub_arcs['reporterDesc'].isin(selected_hubs))
            ].copy()
            if not _hub_yr.empty:
                # Cap at top-8 destinations per hub combined to keep the map legible
                _top_dest = set(
                    _hub_yr.groupby('partnerISO')['primaryValue'].sum().nlargest(8).index
                )
                _hub_yr = _hub_yr[_hub_yr['partnerISO'].isin(_top_dest)]
                _hub_yr['color']     = _hub_yr['reporterDesc'].map(hub_rgba)
                _hub_yr['width']     = (np.sqrt(_hub_yr['primaryValue'] / global_max_ic) * 6).clip(lower=1.0)
                _hub_yr['value_fmt'] = _hub_yr['primaryValue'].apply(fmt)
                df_hub_ic = _hub_yr

        # Merge primary and hub flows into a single figure
        df_ic_plot = (
            pd.concat([df_year, df_hub_ic], ignore_index=True)
            if not df_hub_ic.empty else df_year
        )

        _hub_key = '_'.join(sorted(selected_hubs)) if selected_hubs else 'none'
        st.plotly_chart(
            build_flow_fig(df_ic_plot, globe=use_globe),
            key=f"arc_map_{year}_{projection}_{'_'.join(sorted(selected_countries))}_{_hub_key}",
            width='stretch',
        )
        _hub_note = (
            " **Hub re-export arcs** (amber/pink/green/purple) show IC exports from "
            "the selected intermediate hubs to their top destinations."
            if selected_hubs else ""
        )
        st.caption(
            "**How to read this map** — Each line is an export flow; the arrowhead sits at the "
            "importer. Width ∝ √(trade value), colour = exporting country. "
            + ("Drag to rotate the globe; " if use_globe else "")
            + "hover any flow or dot for exact values."
            + _hub_note
        )
    else:
        st.info("Select at least one IC exporter in the sidebar to display the map.")

    st.markdown("---")
    st.subheader("IC exporters to importers")
    st.caption(
        f"Left: {len(IC_EXPORTERS)} major IC-exporting nations. "
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
    top_dest = sorted(sankey_dest_ic)   # same set the map was guaranteed to include
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
    fig_ts.add_vline(x=2022, line_dash='dash', line_color='#DC2626', opacity=0.9)
    if not df_trend.empty:
        fig_ts.add_annotation(
            x=2022.05, y=df_trend['value_B'].max()*0.95,
            text="US Export Controls<br>Oct 2022", showarrow=False,
            font=dict(color='#DC2626', size=11), xanchor='left'
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
    df_arcs_eq = (
        df_arcs_eq
        .groupby(['reporterDesc','reporterISO','partnerDesc','partnerISO',
                  'period','source_lat','source_lon','target_lat','target_lon'])
        ['primaryValue'].sum().reset_index()
    )

    df_eq_year     = df_arcs_eq[(df_arcs_eq['period']==str(year)) & (df_arcs_eq['reporterDesc'].isin(selected_equip_countries))].copy()

    # Map ↔ Sankey consistency (see IC section for rationale)
    sankey_dest_eq = set(
        df_global_equip[(df_global_equip['period'] == str(year)) &
                        (df_global_equip['reporterDesc'].isin(selected_equip_countries)) &
                        (~df_global_equip['partnerDesc'].isin(set(EQUIP_EXPORTERS)))]
        .groupby('partnerDesc')['primaryValue'].sum().nlargest(8).index
    )
    top15_eq = set(
        df_eq_year.groupby('partnerISO')['primaryValue'].sum().nlargest(15).index
    )
    df_eq_year = df_eq_year[
        df_eq_year['partnerISO'].isin(top15_eq) |
        df_eq_year['partnerDesc'].isin(sankey_dest_eq)
    ].copy()

    _eq_missing = (
        df_global_equip[(df_global_equip['period'] == str(year)) &
                        (df_global_equip['reporterDesc'].isin(selected_equip_countries)) &
                        (~df_global_equip['partnerISO'].isin(set(coords_df['ISO'])))]
        .groupby('partnerDesc')['primaryValue'].sum().nlargest(5)
    )
    if not _eq_missing.empty and _eq_missing.iloc[0] > 1e9:
        st.caption(
            "⚠️ Not mappable (no coordinates on file): "
            + ", ".join(f"{k} ({fmt(v)})" for k, v in _eq_missing.items())
        )
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
        df_eq_year['color'] = df_eq_year['reporterDesc'].map(country_rgba)
        global_max_eq = df_arcs_eq['primaryValue'].max()
        df_eq_year['width'] = (np.sqrt(df_eq_year['primaryValue'] / global_max_eq) * 6).clip(lower=1.0)
        df_eq_year['value_fmt'] = df_eq_year['primaryValue'].apply(fmt)
        st.plotly_chart(
            build_flow_fig(df_eq_year, globe=use_globe),
            key=f"arc_eq_{year}_{projection}_{'_'.join(sorted(selected_equip_countries))}",
            width='stretch',
        )
        st.caption(
            "**How to read this map** — Each line is an export flow; the arrowhead sits at the "
            "importer. Width ∝ √(trade value), colour = exporting country."
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
    top_eq_dest = sorted(sankey_dest_eq)   # same set the map was guaranteed to include
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
    fig_eq_ts.add_vline(x=2022, line_dash='dash', line_color='#DC2626', opacity=0.9)
    if not df_eq_trend_global.empty:
        fig_eq_ts.add_annotation(
            x=2022.05, y=df_eq_trend_global['value_B'].max()*0.95,
            text="US Export Controls<br>Oct 2022", showarrow=False,
            font=dict(color='#DC2626', size=11), xanchor='left'
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
            "Place **semi_supply_chain_sankey_v3.csv** and **node_metadata_v3.csv** "
            "in the same folder as app.py, then restart."
        )
        st.stop()

    # ── Build node arrays ──────────────────────────────────────────────────
    nodes_sc = sorted(set(df_sc["source"]) | set(df_sc["target"]))
    st.caption(
        "Revenue flows between named companies across five layers of the semiconductor supply chain. "
        f"FY2024/25 annual report data, {len(df_sc)} flows, {len(nodes_sc)} nodes."
    )
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
        base  = f"<b>{n}</b><br><span style='color:#64748b'>{cat}</span>"
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

    # ── White-background colour overrides ────────────────────────────────
    # The CSV stores colours tuned for the dark theme. Remap to darker
    # equivalents that have sufficient contrast on white (#WCAG AA target).
    WHITE_NODE_MAP = {
        "#84CC16": "#3B6E0E",   # lime-500  → dark lime       (chip designers)
        "#06B6D4": "#0E7490",   # cyan-400  → cyan-700        (equipment)
        "#14B8A6": "#0F766E",   # teal-400  → teal-700        (memory fabs)
        "#64748B": "#334155",   # slate-500 → slate-700       (aggregates)
        "#0EA5E9": "#0369A1",   # sky-400   → sky-700         (memory end-markets)
        "#8B5CF6": "#6D28D9",   # violet-500→ violet-700      (sub-components)
        "#F59E0B": "#B45309",   # amber-400 → amber-700       (process ctrl)
        "#D97706": "#92400E",   # amber-500 → amber-800       (raw materials)
        "#6366F1": "#4338CA",   # indigo-500→ indigo-700      (EDA)
        "#EC4899": "#BE185D",   # pink-400  → pink-700        (logic fabs)
    }

    node_colors_white = [WHITE_NODE_MAP.get(c, c) for c in node_colors_sc]

    # Recompute link colours at lower opacity so ribbons don't overpower
    # the white background (0.22 opacity vs 0.42 on dark)
    def _link_rgba(hex_src, alpha=0.22):
        h = WHITE_NODE_MAP.get(hex_src, hex_src).lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        return f"rgba({r},{g},{b},{alpha})"

    link_colors_white = [
        _link_rgba(c) for c in df_sc["node_color_hex"].tolist()
    ]

    # ── Build figure ───────────────────────────────────────────────────────
    fig_atlas = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label         = node_labels_sc,
            color         = node_colors_white,
            x             = node_x_sc,
            pad           = 20,
            thickness     = 22,
            line          = dict(color="rgba(255,255,255,0.6)", width=0.5),
            hovertemplate = "%{customdata}<extra></extra>",
            customdata    = node_hover_text_sc,
        ),
        link=dict(
            source        = df_sc["source"].map(n_idx_sc).tolist(),
            target        = df_sc["target"].map(n_idx_sc).tolist(),
            value         = df_sc["value_usd_bn"].tolist(),
            color         = link_colors_white,
            hovertemplate = (
                "<b>%{source.label}  →  %{target.label}</b><br>"
                "$%{value:.1f}B<br>"
                "Confidence: %{customdata[0]}<br>"
                "Source: %{customdata[1]}<extra></extra>"
            ),
            customdata = df_sc[["confidence_level", "source_document"]].values.tolist(),
        ),
        textfont=dict(color="#1e293b", size=10, family="Arial"),
    ))

    fig_atlas.update_layout(
        title=dict(
            text=(
                "Semiconductor Supply Chain - FY2024/25"
            ),
            font=dict(color="#0f172a", size=18, family="Arial Black, Arial"),
            x=0.5, xanchor="center",
        ),
        paper_bgcolor = "white",
        plot_bgcolor  = "white",
        font          = dict(color="#1e293b", size=10, family="Arial"),
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
            font=dict(color="#374151", size=13, family="Arial"),
        )

    # Colour legend — use white-bg mapped colours
    legend_items = [
        ("#6D28D9", "Precision Sub-Components"),
        ("#B45309", "Process Control"),
        ("#92400E", "Raw Materials & Wafers"),
        ("#0E7490", "Semiconductor Equipment"),
        ("#4338CA", "EDA & IP"),
        ("#BE185D", "Logic Fabs"),
        ("#0F766E", "Memory Fabs"),
        ("#3B6E0E", "Chip Designers"),
        ("#0369A1", "Memory End-Markets"),
        ("#334155", "Aggregates"),
    ]
    for i, (col, lbl) in enumerate(legend_items):
        fig_atlas.add_annotation(
            x=i * 0.105, y=-0.05, xref="paper", yref="paper",
            text=f"<span style='color:{col}'>■</span> {lbl}",
            showarrow=False, xanchor="left",
            font=dict(color="#374151", size=9, family="Arial"),
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
