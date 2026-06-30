"""
app.py
======
QC Sensory Dashboard — Entry point utama.
Jalankan: streamlit run dashboard/app.py
"""

import sys
import streamlit as st
import pandas as pd
from pathlib import Path

# ── PATH SETUP ────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from config import RAW_FOLDER
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

# ── CSS & FOOTER ──────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricDelta"] svg { display: none; }
footer { visibility: hidden; }
.custom-footer {
    position: fixed; bottom: 0; left: 0; width: 100%;
    background-color: rgba(240,242,246,0.95);
    border-top: 1px solid #ddd;
    padding: 6px 20px; font-size: 12px; color: #888;
    text-align: center; z-index: 999;
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

    # Rentang tanggal tersedia
    min_d = df_all["Date"].min().date()
    max_d = df_all["Date"].max().date()

    st.divider()
    st.subheader("Filter")

    # ── Preset rentang tanggal ────────────────────────────────────
    import datetime
    today    = max_d  # pakai max tanggal data, bukan hari ini

    # ── Bangun preset otomatis berdasarkan tahun yang tersedia ───
    # Tahun "penuh" = ada data di semua 12 bulan
    _years_avail = sorted(
        df_all["Date"].dropna().dt.year.unique().tolist()
    )
    _year_presets = {}
    for _y in _years_avail:
        _y_data = df_all[df_all["Date"].dt.year == _y]["Date"]
        _months  = _y_data.dt.month.nunique()
        _label   = f"Tahun {_y} (Full)" if _months == 12 else f"Tahun {_y} ({_months} bulan)"
        _y_start = datetime.date(_y, 1, 1)
        _y_end   = datetime.date(_y, 12, 31)
        _year_presets[_label] = (_y_start, _y_end)

    # Preset bulan ini dan 30 hari
    _this_month_start = today.replace(day=1)
    _30d_start        = today - datetime.timedelta(days=30)

    presets = {
        "30 Hari Terakhir": (_30d_start, today),
        "Bulan Ini":        (_this_month_start, today),
        **_year_presets,
        "Semua Data":       (min_d, max_d),
        "Custom":           None,
    }

    # Default ke tahun penuh terbaru (12 bulan)
    _full_years = [k for k,_ in _year_presets.items() if "Full" in k]
    _default_idx = list(presets.keys()).index(_full_years[-1]) if _full_years else 0

    sel_preset = st.selectbox(
        "Periode",
        list(presets.keys()),
        index=_default_idx,
        key="preset_period",
    )

    if sel_preset == "Custom" or presets[sel_preset] is None:
        _date_val = st.date_input(
            "Rentang tanggal",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            key="custom_date",
        )
        if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2:
            d1, d2 = _date_val
        else:
            d1 = d2 = _date_val[0] if _date_val else min_d
    else:
        d1, d2 = presets[sel_preset]
        # Clamp ke range data yang tersedia
        d1 = max(d1, min_d)
        d2 = min(d2, max_d)
        st.caption(f"📅 {d1.strftime('%d %b %Y')} — {d2.strftime('%d %b %Y')}")

    # ── Filter lainnya ────────────────────────────────────────────
    all_prods = sorted(df_all["Product_Name"].dropna().unique())
    sel_prods = st.multiselect("Produk", all_prods, placeholder="Semua produk")

    sel_plants = st.multiselect(
        "Plant",
        ["Plant 1", "Plant 2", "Blending", "Unknown"],
        default=["Plant 1", "Plant 2", "Blending", "Unknown"],
    )

    all_shifts = sorted(
        df_all["Shift_Code"].dropna().unique(),
        key=lambda x: (float(x) if str(x).replace(".", "").isdigit() else 99),
    )
    sel_shifts = st.multiselect("Shift", all_shifts, default=all_shifts)

# ── APPLY FILTER ─────────────────────────────────────────────────
mask = (
    (df_all["Date"].dt.date >= d1) &
    (df_all["Date"].dt.date <= d2) &
    (df_all["Plant"].isin(
        sel_plants if sel_plants else ["Plant 1","Plant 2","Blending","Unknown"]
    )) &
    (df_all["Shift_Code"].isin(sel_shifts if sel_shifts else all_shifts))
)
if sel_prods:
    mask &= df_all["Product_Name"].isin(sel_prods)

df = df_all[mask].copy()

# ── TABS ──────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📈 Gap Analysis",
    "🔬 Parameter & Produk",
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
