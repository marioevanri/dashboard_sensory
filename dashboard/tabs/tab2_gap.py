"""tab2_gap.py — Gap Analysis KimFis vs Verifikator."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from config import STATUS_ORDER, STATUS_COLORS, STATUS_NUM


def classify_gap(kf: str, vf: str) -> str | None:
    """
    Klasifikasi gap berdasarkan MAKNA, bukan hanya jarak.

    Kategori (3):
        "Melibatkan TP 3"  — salah satu atau keduanya TP 3 (off taste,
                             tidak punya arah +/-), prioritas tertinggi
        "Beda Arah"        — keduanya punya arah (+/-) tapi berlawanan
                             contoh: TP 1- vs TP 1+, TP 2- vs TP 1+
        "Beda Intensitas"  — semua mismatch lainnya: sama arah atau
                             salah satunya Pass, berapapun jaraknya
                             contoh: Pass→TP 1-, TP 1-→TP 2-, Pass→TP 2-

    Returns None jika match atau status tidak dikenal.
    """
    if kf not in STATUS_NUM or vf not in STATUS_NUM or kf == vf:
        return None

    signed = {"TP 2-", "TP 1-", "TP 1+", "TP 2+"}

    # Prioritas 1: TP 3 = off taste, kategori sendiri
    if kf == "TP 3" or vf == "TP 3":
        return "Melibatkan TP 3"

    # Prioritas 2: keduanya punya arah dan berlawanan tanda
    if (kf in signed and vf in signed and
            STATUS_NUM[kf] * STATUS_NUM[vf] < 0):
        return "Beda Arah"

    # Sisanya: sama arah / via Pass — berapapun jaraknya
    return "Beda Intensitas"


def render(df: pd.DataFrame) -> None:
    """Render Tab 2 — Gap Analysis."""
    st.subheader("Gap Analysis — KimFis vs Verifikator")

    df_mm = df[df["Comparison"] == "MISMATCH"].copy()

    if df_mm.empty:
        st.info("Tidak ada mismatch pada filter yang dipilih.")
        return

    col_a, col_b = st.columns(2)

    # ── Top Gap Type ──────────────────────────────────────────────
    with col_a:
        st.subheader("Top Gap Type")
        gap_df = df_mm["Gap_Type"].value_counts().reset_index()
        gap_df.columns = ["Gap Type","Jumlah"]
        gap_df["% dari Mismatch"] = (gap_df["Jumlah"] / len(df_mm) * 100).round(1)
        gap_df["Label"] = gap_df.apply(
            lambda r: f"{r['Jumlah']}x  |  {r['% dari Mismatch']}%", axis=1)
        gap_df = gap_df.sort_values("Jumlah", ascending=True)

        fig = px.bar(gap_df, x="Jumlah", y="Gap Type", orientation="h",
                     text="Label", color="Jumlah",
                     color_continuous_scale=["#B5D4F4","#D32F2F"],
                     template="plotly_white", height=400)
        fig.update_traces(textposition="inside", insidetextanchor="middle")
        fig.update_coloraxes(showscale=False)
        fig.update_layout(yaxis={"categoryorder":"total ascending"},
                          margin=dict(t=20,b=20,l=10,r=10),
                          xaxis_title="Jumlah Kejadian", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    # ── Heatmap dengan warna gap ──────────────────────────────────
    with col_b:
        st.subheader("Heatmap KimFis × Verifikator")
        _render_heatmap(df)
        _render_gap_breakdown(df_mm, len(df_mm))

    st.divider()
    _render_sankey(df)
    st.divider()

    col_c, col_d = st.columns(2)
    with col_c:
        _render_trend(df)
    with col_d:
        _render_breakdown_produk(df_mm)

    st.divider()


def _render_heatmap(df: pd.DataFrame) -> None:
    """Heatmap dengan warna berdasarkan jarak gap."""
    import numpy as np

    heat_df = (
        df[df["Comparison"].isin(["MATCH","MISMATCH"])]
        .groupby(["KF_Status","Verif_Status"]).size().reset_index(name="Jumlah")
    )
    heat_pivot = heat_df.pivot_table(
        index="KF_Status", columns="Verif_Status", values="Jumlah", fill_value=0)
    vr = [s for s in STATUS_ORDER if s in heat_pivot.index]
    vc = [s for s in STATUS_ORDER if s in heat_pivot.columns]
    heat_pivot = heat_pivot.loc[vr, vc]

    z_arr     = np.array([[abs(STATUS_NUM.get(r,0)-STATUS_NUM.get(c,0))
                           for c in vc] for r in vr], dtype=float)
    text_mat  = [[str(int(heat_pivot.loc[r,c])) if heat_pivot.loc[r,c]>0 else ""
                  for c in vc] for r in vr]

    colorscale = [
        [0.00, "rgba(46,139,87,0.25)"],
        [0.20, "rgba(255,220,50,0.35)"],
        [0.45, "rgba(230,120,0,0.50)"],
        [0.70, "rgba(211,47,47,0.60)"],
        [1.00, "rgba(139,0,0,0.75)"],
    ]
    fig = go.Figure(go.Heatmap(
        z=z_arr, x=vc, y=vr,
        text=text_mat, texttemplate="%{text}",
        textfont=dict(size=13, color="black"),
        colorscale=colorscale, zmin=0, zmax=4,
        showscale=False, xgap=2, ygap=2,
    ))
    fig.update_layout(
        margin=dict(t=20,b=50,l=10,r=10),
        xaxis_title="Status Verifikator",
        yaxis_title="Status KimFis",
        template="plotly_white", height=400,
        yaxis=dict(autorange="reversed"),
    )
    fig.add_annotation(
        text="🟢 Match  🟡 Gap 1  🟠 Gap 2  🔴 Gap 3  ■ Gap 4+",
        xref="paper", yref="paper", x=0, y=-0.14,
        showarrow=False, font=dict(size=10, color="#555"), align="left",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_gap_breakdown(df_mm: pd.DataFrame, total_mm: int) -> None:
    """Tabel breakdown gap per kategori."""
    st.markdown("**Gap Breakdown per Kategori**")
    gap_rows = [
        {"Kategori": classify_gap(r["KF_Status"], r["Verif_Status"]),
         "Gap Type": r.get("Gap_Type","")}
        for _, r in df_mm.iterrows()
        if classify_gap(r["KF_Status"], r["Verif_Status"])
    ]
    if not gap_rows:
        return

    gdf  = pd.DataFrame(gap_rows)
    cats = gdf.groupby("Kategori").size().reset_index(name="Jumlah")
    cats["% Mismatch"] = (cats["Jumlah"]/total_mm*100).round(1)
    detail = (gdf.groupby(["Kategori","Gap Type"]).size()
              .reset_index(name="Jumlah"))
    detail["% Mismatch"] = (detail["Jumlah"]/total_mm*100).round(1)

    CAT_ORDER = ["Beda Intensitas","Beda Arah","Melibatkan TP 3"]
    CAT_ICONS = {
        "Beda Intensitas": "🟠",
        "Beda Arah":       "🔄",
        "Melibatkan TP 3": "🔴",
    }
    CAT_DESC  = {
        "Beda Intensitas": "Sama arah atau via Pass, berapapun jaraknya — Pass→TP 1-, TP 1-→TP 2-, Pass→TP 2-",
        "Beda Arah":       "Berlawanan arah — satu kurang (-), satu lebih (+) — TP 1-→TP 1+, TP 2-→TP 1+",
        "Melibatkan TP 3": "Off taste (TP 3 tidak punya arah +/-) — Pass→TP 3, TP 1-→TP 3",
    }
    cats["_ord"] = cats["Kategori"].map({c:i for i,c in enumerate(CAT_ORDER)})
    cats = cats.sort_values("_ord").drop(columns="_ord")

    st.caption(f"Total terklasifikasi: **{len(gap_rows):,}** dari {total_mm:,} mismatch")
    for _, row in cats.iterrows():
        cat = row["Kategori"]
        with st.expander(
            f"{CAT_ICONS.get(cat,'•')} **{cat}** — "
            f"{row['Jumlah']:,} ({row['% Mismatch']}%)"
        ):
            st.caption(CAT_DESC.get(cat,""))
            sub = detail[detail["Kategori"]==cat][["Gap Type","Jumlah","% Mismatch"]]
            sub = sub.reset_index(drop=True)
            sub.index += 1
            st.dataframe(sub, use_container_width=True)


def _render_sankey(df: pd.DataFrame) -> None:
    """Sankey diagram aliran status."""
    st.subheader("Aliran Gap — Sankey Diagram")
    sdf = (df[df["Comparison"].isin(["MATCH","MISMATCH"])]
           .groupby(["KF_Status","Verif_Status"]).size().reset_index(name="Jumlah"))
    kf_nodes = [f"KF: {s}"    for s in STATUS_ORDER if s in sdf["KF_Status"].values]
    vf_nodes = [f"Verif: {s}" for s in STATUS_ORDER if s in sdf["Verif_Status"].values]
    all_nodes   = kf_nodes + vf_nodes
    node_colors = [STATUS_COLORS.get(n.split(": ",1)[1],"#aaa") for n in all_nodes]

    src, tgt, val, lc = [], [], [], []
    for _, r in sdf.iterrows():
        s = f"KF: {r['KF_Status']}"; t = f"Verif: {r['Verif_Status']}"
        if s in all_nodes and t in all_nodes:
            src.append(all_nodes.index(s)); tgt.append(all_nodes.index(t))
            val.append(r["Jumlah"])
            lc.append("rgba(46,139,87,0.3)" if r["KF_Status"]==r["Verif_Status"]
                       else "rgba(211,47,47,0.25)")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(pad=20, thickness=25, line=dict(color="white",width=0.5),
                  label=all_nodes, color=node_colors),
        link=dict(source=src, target=tgt, value=val, color=lc),
    ))
    fig.update_layout(height=420, margin=dict(t=20,b=20,l=20,r=20),
                      template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)


def _render_trend(df: pd.DataFrame) -> None:
    st.subheader("Trend Gap per Waktu")
    mode = st.radio("Granularitas:", ["Harian","Mingguan"],
                    horizontal=True, key="trend_mode")
    dft = df[df["Comparison"].isin(["MATCH","MISMATCH"])].copy()
    dft["Periode"] = (dft["Date"].dt.strftime("%Y-%m-%d") if mode=="Harian"
                      else dft["Date"].dt.strftime("%Y-W%W"))
    trend = dft.groupby(["Periode","Comparison"]).size().reset_index(name="Jumlah")
    fig = px.bar(trend, x="Periode", y="Jumlah", color="Comparison", barmode="stack",
                 color_discrete_map={"MATCH":"#2E8B57","MISMATCH":"#D32F2F"},
                 template="plotly_white", height=380,
                 labels={"Periode":"","Jumlah":"Jumlah Sampel"})
    fig.update_layout(legend=dict(orientation="h", y=1.1),
                      margin=dict(t=20,b=40,l=10,r=10), xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)


def _render_breakdown_produk(df_mm: pd.DataFrame) -> None:
    st.subheader("Breakdown Gap per Produk")
    tpg = df_mm.groupby(["Product_Name","Gap_Type"]).size().reset_index(name="Jumlah")
    top10 = (tpg.groupby("Product_Name")["Jumlah"].sum()
             .nlargest(10).index.tolist())
    tpg = tpg[tpg["Product_Name"].isin(top10)]
    fig = px.bar(tpg, x="Jumlah", y="Product_Name", color="Gap_Type",
                 orientation="h", barmode="stack",
                 template="plotly_white", height=380,
                 labels={"Product_Name":"Produk","Jumlah":"Jumlah Mismatch"})
    fig.update_layout(legend=dict(orientation="h", y=-0.25),
                      yaxis={"categoryorder":"total ascending"},
                      margin=dict(t=20,b=80,l=10,r=10))
    st.plotly_chart(fig, use_container_width=True)
