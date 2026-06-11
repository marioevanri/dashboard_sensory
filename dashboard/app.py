"""
app.py
======
QC Sensory Dashboard — Entry point utama.

Menjalankan: streamlit run dashboard/app.py

Semua logic tab ada di folder tabs/:
    tab1_overview.py     — Overview & KPI
    tab2_gap.py          — Gap Analysis
    tab3_parameter.py    — Parameter Sensory
    tab4_shift_analyst.py — Shift & Performa Analis
    tab5_daily_report.py — Daily Report
"""

import sys
import streamlit as st
import pandas as pd
from pathlib import Path

# ── PATH SETUP ────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from config import RAW_FOLDER, CACHE_FILE
from load_data import load_with_cache

# ── IMPORT TAB MODULES ────────────────────────────────────────────
from tabs.tab1_overview      import render as _render_tab1
from tabs.tab2_gap           import render as _render_tab2
from tabs.tab3_parameter     import render as _render_tab3
from tabs.tab4_shift_analyst import render as _render_tab4
from tabs.tab5_daily_report  import render as _render_tab5

# ── PAGE CONFIG ───────────────────────────────────────────────────
st.set_page_config(
    page_title="QC Sensory Dashboard",
    page_icon="🧪",
    layout="wide",
)

# ── CUSTOM CSS & FOOTER ───────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricDelta"] svg { display: none; }

footer { visibility: hidden; }

.custom-footer {
    position: fixed;
    bottom: 0; left: 0;
    width: 100%;
    background-color: rgba(240, 242, 246, 0.95);
    border-top: 1px solid #ddd;
    padding: 6px 20px;
    font-size: 12px;
    color: #888;
    text-align: center;
    z-index: 999;
}
</style>

<div class="custom-footer">
    Dibuat oleh <strong>Mario Evanri</strong> &nbsp;·&nbsp;
    QC Sensory Dashboard &nbsp;·&nbsp;
    Built with Python, Streamlit &amp; Plotly
</div>
""", unsafe_allow_html=True)

# ── LOAD DATA ─────────────────────────────────────────────────────
@st.cache_data(show_spinner="⏳ Memuat data...")
def get_data(force: bool = False) -> pd.DataFrame:
    return load_with_cache(RAW_FOLDER, force_reload=force)

def reload() -> None:
    st.cache_data.clear()
    load_with_cache(RAW_FOLDER, force_reload=True)
    st.rerun()

# ── SIDEBAR ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧪 QC Sensory")
    if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
        reload()

    df_all = get_data(False)

    st.divider()
    st.subheader("Filter")

    # Rentang tanggal
    min_d = df_all["Date"].min().date()
    max_d = df_all["Date"].max().date()
    _date_val = st.date_input(
        "Rentang tanggal", value=(min_d, max_d),
        min_value=min_d, max_value=max_d,
    )
    if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2:
        d1, d2 = _date_val
    else:
        d1 = d2 = _date_val[0] if _date_val else min_d

    # Produk
    all_prods = sorted(df_all["Product_Name"].dropna().unique())
    sel_prods = st.multiselect("Produk", all_prods, placeholder="Semua produk")

    # Plant
    sel_plants = st.multiselect(
        "Plant",
        ["Plant 1","Plant 2","Blending","Unknown"],
        default=["Plant 1","Plant 2","Blending","Unknown"],
    )

    # Shift
    all_shifts = sorted(
        df_all["Shift_Code"].dropna().unique(),
        key=lambda x: (float(x) if str(x).replace(".","").isdigit() else 99),
    )
    sel_shifts = st.multiselect("Shift", all_shifts, default=all_shifts)

# ── FILTER ────────────────────────────────────────────────────────
mask = (
    (df_all["Date"].dt.date >= d1) &
    (df_all["Date"].dt.date <= d2) &
    (df_all["Plant"].isin(sel_plants if sel_plants
                          else ["Plant 1","Plant 2","Blending","Unknown"])) &
    (df_all["Shift_Code"].isin(sel_shifts if sel_shifts else all_shifts))
)
if sel_prods:
    mask &= df_all["Product_Name"].isin(sel_prods)

df = df_all[mask].copy()

# ── TABS ──────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📈 Gap Analysis",
    "🔬 Parameter",
    "🏭 Shift & Analis",
    "📋 Daily Report",
])

with tab1:
    _render_tab1(df)

with tab2:
    _render_tab2(df)

with tab3:
    _render_tab3(df)

with tab4:
    _render_tab4(df)

with tab5:
    _render_tab5(df, df_all, all_prods)
