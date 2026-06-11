"""tab1_overview.py — Overview KPI dan distribusi status."""

import pandas as pd
import plotly.express as px
import streamlit as st
from config import STATUS_ORDER, STATUS_COLORS, MIN_SAMPLE_FILTER


def render(df: pd.DataFrame) -> None:
    """Render Tab 1 — Overview."""
    st.subheader("Overview")

    # ── KPI ──────────────────────────────────────────────────────
    total      = len(df)
    verif      = df["Verif_Status"].notna().sum()
    match      = (df["Comparison"] == "MATCH").sum()
    mismatch   = (df["Comparison"] == "MISMATCH").sum()
    coverage   = verif  / total * 100 if total  else 0
    match_rate = match  / verif * 100 if verif  else 0
    miss_rate  = mismatch / verif * 100 if verif else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sampel",  f"{total:,}")
    c2.metric("Terverifikasi", f"{verif:,}",    f"coverage: {coverage:.1f}%")
    c3.metric("Match",         f"{match:,}",    f"dari terverif: {match_rate:.1f}%")
    c4.metric("Mismatch",      f"{mismatch:,}", f"dari terverif: {miss_rate:.1f}%",
              delta_color="inverse")

    st.divider()
    col_a, col_b = st.columns(2)

    # ── Distribusi Status ─────────────────────────────────────────
    with col_a:
        st.subheader("Distribusi Status")
        kf_dist = (df["KF_Status"].value_counts()
                   .rename_axis("Status").reset_index(name="Jumlah"))
        kf_dist["Sumber"] = "KimFis"
        vf_dist = (df["Verif_Status"].dropna().value_counts()
                   .rename_axis("Status").reset_index(name="Jumlah"))
        vf_dist["Sumber"] = "Verifikator"

        dist_df = pd.concat([kf_dist, vf_dist], ignore_index=True)
        dist_df = dist_df[dist_df["Status"].isin(STATUS_ORDER)]
        dist_df["Status"] = pd.Categorical(dist_df["Status"], STATUS_ORDER, ordered=True)

        fig = px.bar(
            dist_df.sort_values("Status"),
            x="Status", y="Jumlah", color="Sumber", barmode="group",
            color_discrete_map={"KimFis":"#185FA5","Verifikator":"#EF9F27"},
            category_orders={"Status": STATUS_ORDER},
            text_auto=True, template="plotly_white", height=380,
        )
        fig.update_layout(legend=dict(orientation="h", y=1.1),
                          margin=dict(t=30,b=20,l=10,r=10),
                          xaxis_title="", yaxis_title="Jumlah Sampel")
        st.plotly_chart(fig, use_container_width=True)

    # ── Top 10 Produk ─────────────────────────────────────────────
    with col_b:
        st.subheader("Top 10 Produk — Mismatch Tertinggi")
        mode = st.radio("Tampilkan berdasarkan:",
                        ["Persentase (%)", "Jumlah Absolut"],
                        horizontal=True, key="top10_mode")

        top_df = (
            df[df["Comparison"].isin(["MATCH","MISMATCH"])]
            .groupby("Product_Name")
            .agg(Total=("Comparison","count"),
                 Mismatch=("Comparison", lambda x: (x=="MISMATCH").sum()),
                 Match=("Comparison",   lambda x: (x=="MATCH").sum()))
            .reset_index()
        )
        top_df["Rate %"]  = (top_df["Mismatch"] / top_df["Total"] * 100).round(1)
        top_df["Match %"] = (top_df["Match"]    / top_df["Total"] * 100).round(1)
        top_df = top_df[top_df["Total"] >= MIN_SAMPLE_FILTER]

        if mode == "Persentase (%)":
            top_df = top_df.nlargest(10,"Rate %").sort_values("Rate %", ascending=False)
            y_col, y_label, color_col = "Rate %", "Mismatch Rate (%)", "Rate %"
            top_df["Label"] = top_df["Rate %"].apply(lambda x: f"{x}%")
        else:
            top_df = top_df.nlargest(10,"Mismatch").sort_values("Mismatch", ascending=False)
            y_col, y_label, color_col = "Mismatch", "Jumlah Mismatch", "Mismatch"
            top_df["Label"] = top_df["Mismatch"].apply(lambda x: str(x))


        fig2 = px.bar(
            top_df, x="Product_Name", y=y_col,
            text="Label", color=color_col,
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=380,
            labels={"Product_Name":"Produk", y_col:y_label},
            custom_data=["Product_Name","Rate %","Mismatch","Total"],
        )
        fig2.update_traces(
            textposition="outside",
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Mismatch Rate: %{customdata[1]}%<br>"
                "Mismatch: %{customdata[2]}<br>"
                "Total: %{customdata[3]}<extra></extra>"
            )
        )
        fig2.update_coloraxes(showscale=False)
        fig2.update_layout(
            xaxis=dict(categoryorder="total descending", tickangle=-45,
                        tickfont=dict(size=10)),
            margin=dict(t=30, b=80, l=10, r=10),
            xaxis_title="", yaxis_title=y_label,
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
