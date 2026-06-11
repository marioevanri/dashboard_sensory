"""tab3_parameter.py — Tab 3 QC Sensory Dashboard."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import (
    STATUS_ORDER, STATUS_COLORS, STATUS_NUM,
    PARAM_COLS, PARAM_LABELS, CRITICAL_STATUS,
    SHIFT_ORDER,
)



def render(df: pd.DataFrame) -> None:
    """Render Tab 3."""
    st.subheader("Analisis Parameter Sensory")

    sel_param = st.selectbox(
        "Parameter", PARAM_COLS,
        format_func=lambda x: PARAM_LABELS[x], key="param_detail")
    df_p  = df.copy()
    kc_s  = f"KF_{sel_param}_Status"
    vc_s  = f"V_{sel_param}_Status"
    df_p["Month"] = pd.to_datetime(df_p["Date"]).dt.to_period("M").astype(str)

    st.divider()

    # Pareto
    st.subheader("Pareto Gap per Parameter")
    pareto_rows = []
    for p in PARAM_COLS:
        kc = f"KF_{p}_Status"; vc = f"V_{p}_Status"
        if kc in df_p.columns and vc in df_p.columns:
            both  = df_p[[kc,vc]].dropna()
            total = len(both)
            if total == 0: continue
            gap = (both[kc] != both[vc]).sum()
            pareto_rows.append({
                "Parameter": PARAM_LABELS[p],
                "Gap": int(gap), "Match": int(total-gap),
                "Total": total, "Gap %": round(gap/total*100,1),
            })
    if pareto_rows:
        pareto_df = pd.DataFrame(pareto_rows).sort_values("Gap", ascending=False)
        total_gap_all = pareto_df["Gap"].sum()
        pareto_df["Kumulatif %"] = (pareto_df["Gap"].cumsum() / total_gap_all * 100).round(1)
        colors = ["#D32F2F"] + ["#185FA5"] * (len(pareto_df)-1)
        fig_pareto = go.Figure()
        fig_pareto.add_trace(go.Bar(
            x=pareto_df["Parameter"], y=pareto_df["Gap"],
            text=pareto_df["Gap"], textposition="outside",
            marker_color=colors, name="Jumlah Gap", yaxis="y1",
        ))
        fig_pareto.add_trace(go.Scatter(
            x=pareto_df["Parameter"], y=pareto_df["Kumulatif %"],
            mode="lines+markers+text",
            text=pareto_df["Kumulatif %"].astype(str)+"%",
            textposition="top center",
            textfont=dict(color="#FF6F00",size=11),
            line=dict(color="#FF6F00",width=2),
            marker=dict(size=8,color="#FF6F00"),
            name="Kumulatif %", yaxis="y2",
        ))
        fig_pareto.add_hline(y=80, line_dash="dash", line_color="#888", opacity=0.5, yref="y2")
        fig_pareto.update_layout(
            template="plotly_white", height=420,
            yaxis=dict(title="Jumlah Gap", side="left"),
            yaxis2=dict(title="Kumulatif %", side="right", overlaying="y",
                        range=[0,125], showgrid=False),
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=50, b=20, l=10, r=60), xaxis_title="",
        )
        st.plotly_chart(fig_pareto, use_container_width=True)
        st.dataframe(
            pareto_df[["Parameter","Gap","Match","Total","Gap %","Kumulatif %"]]
            .set_index("Parameter"), use_container_width=True,
        )

    st.divider()

    # Distribusi Status
    st.subheader(f"Distribusi Status — {PARAM_LABELS[sel_param]}")
    rows = []
    if kc_s in df_p.columns:
        for s, n in df_p[kc_s].dropna().value_counts().items():
            if s in STATUS_ORDER: rows.append({"Status":s,"Jumlah":n,"Sumber":"KimFis"})
    if vc_s in df_p.columns:
        for s, n in df_p[vc_s].dropna().value_counts().items():
            if s in STATUS_ORDER: rows.append({"Status":s,"Jumlah":n,"Sumber":"Verifikator"})
    if rows:
        dist_df = pd.DataFrame(rows)
        dist_df["Status"] = pd.Categorical(dist_df["Status"], STATUS_ORDER, ordered=True)
        dist_df = dist_df.sort_values("Status")
        totals  = dist_df.groupby("Sumber")["Jumlah"].transform("sum")
        dist_df["Persen"] = (dist_df["Jumlah"] / totals * 100).round(1)
        dist_df["Label"]  = dist_df.apply(lambda r: f"{r['Jumlah']} ({r['Persen']}%)", axis=1)
        fig_dist = px.bar(
            dist_df, x="Status", y="Jumlah", color="Sumber",
            barmode="group", text="Label",
            color_discrete_map={"KimFis":"#185FA5","Verifikator":"#EF9F27"},
            category_orders={"Status":STATUS_ORDER},
            template="plotly_white", height=400,
        )
        fig_dist.update_traces(textposition="outside")
        fig_dist.update_layout(
            legend=dict(orientation="h", y=1.05),
            margin=dict(t=50, b=20, l=10, r=10),
            xaxis_title="Status", yaxis_title="Jumlah Mix/IBC",
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    st.divider()

    # Heatmap parameter
    st.subheader("Heatmap KF Status × Verif Status per Parameter")
    sel_param_bias = st.selectbox(
        "Pilih Parameter untuk Heatmap:", PARAM_COLS,
        format_func=lambda x: PARAM_LABELS[x], key="bias_param")
    kc_b = f"KF_{sel_param_bias}_Status"
    vc_b = f"V_{sel_param_bias}_Status"
    if kc_b in df_p.columns and vc_b in df_p.columns:
        heat_data = df_p[[kc_b,vc_b]].dropna()
        heat_data = heat_data[
            heat_data[kc_b].isin(STATUS_ORDER) & heat_data[vc_b].isin(STATUS_ORDER)]
        heat_pivot = (
            heat_data.groupby([kc_b,vc_b]).size().reset_index(name="Jumlah")
            .pivot_table(index=kc_b, columns=vc_b, values="Jumlah", fill_value=0)
        )
        valid_rows = [s for s in STATUS_ORDER if s in heat_pivot.index]
        valid_cols = [s for s in STATUS_ORDER if s in heat_pivot.columns]
        heat_pivot = heat_pivot.loc[valid_rows, valid_cols]
        fig_heat2 = px.imshow(
            heat_pivot, text_auto=True,
            color_continuous_scale=["#ffffff","#185FA5"],
            aspect="auto", template="plotly_white", height=380,
            labels={"x":"Status Verifikator","y":"Status KimFis","color":"Jumlah"},
        )
        for i, status in enumerate(valid_rows):
            if status in valid_cols:
                j = valid_cols.index(status)
                fig_heat2.add_shape(
                    type="rect",
                    x0=j-0.5, x1=j+0.5, y0=i-0.5, y1=i+0.5,
                    line=dict(color="#2E8B57", width=2),
                    fillcolor="rgba(0,0,0,0)",
                )
        fig_heat2.update_layout(
            margin=dict(t=40,b=20,l=10,r=20),
            xaxis_title="Status Verifikator", yaxis_title="Status KimFis",
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig_heat2, use_container_width=True)

    st.divider()

    # Trend Bulanan
    st.subheader(f"Trend Bulanan — {PARAM_LABELS[sel_param]}")
    trend_toggle = st.radio(
        "Tampilkan:", ["Gap Rate per Bulan","Distribusi Status per Bulan"],
        horizontal=True, key="trend_mode_param")

    if trend_toggle == "Gap Rate per Bulan":
        trend_rows = []
        for month, grp in df_p.groupby("Month"):
            if kc_s not in grp.columns or vc_s not in grp.columns: continue
            both  = grp[[kc_s,vc_s]].dropna()
            total = len(both)
            if total == 0: continue
            gap = (both[kc_s] != both[vc_s]).sum()
            trend_rows.append({
                "Bulan": month, "Gap": int(gap),
                "Total": total, "Gap %": round(gap/total*100,1),
            })
        if trend_rows:
            trend_df = pd.DataFrame(trend_rows).sort_values("Bulan")
            fig_trend2 = go.Figure()
            fig_trend2.add_trace(go.Bar(
                x=trend_df["Bulan"], y=trend_df["Gap"], name="Gap",
                marker_color="#D32F2F", text=trend_df["Gap"],
                textposition="outside", yaxis="y1",
            ))
            fig_trend2.add_trace(go.Scatter(
                x=trend_df["Bulan"], y=trend_df["Gap %"], name="Gap %",
                mode="lines+markers",
                line=dict(color="#2E8B57", width=2.5),
                marker=dict(size=8, color="#2E8B57"), yaxis="y2",
            ))
            fig_trend2.update_layout(
                template="plotly_white", height=380,
                yaxis=dict(title="Jumlah Gap", side="left"),
                yaxis2=dict(title="Gap %", side="right", overlaying="y",
                            range=[0,110], showgrid=False),
                legend=dict(orientation="h", y=1.1),
                margin=dict(t=50, b=20, l=10, r=60),
                xaxis_title="", xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_trend2, use_container_width=True)
    else:
        trend_status_rows = []
        for month, grp in df_p.groupby("Month"):
            for s, n in grp[kc_s].dropna().value_counts().items():
                if s in STATUS_ORDER:
                    trend_status_rows.append({"Bulan":month,"Status":s,"Jumlah":n,"Sumber":"KimFis"})
            if vc_s in grp.columns:
                for s, n in grp[vc_s].dropna().value_counts().items():
                    if s in STATUS_ORDER:
                        trend_status_rows.append({"Bulan":month,"Status":s,"Jumlah":n,"Sumber":"Verifikator"})
        if trend_status_rows:
            ts_df = pd.DataFrame(trend_status_rows)
            ts_df["Status"] = pd.Categorical(ts_df["Status"], STATUS_ORDER, ordered=True)
            ts_df = ts_df.sort_values(["Bulan","Status"])
            sumber_sel = st.radio("Sumber:", ["KimFis","Verifikator","Keduanya"],
                                   horizontal=True, key="trend_sumber")
            if sumber_sel != "Keduanya":
                ts_df = ts_df[ts_df["Sumber"] == sumber_sel]
            fig_ts = px.bar(
                ts_df, x="Bulan", y="Jumlah", color="Status", barmode="stack",
                facet_row="Sumber" if sumber_sel=="Keduanya" else None,
                color_discrete_map=STATUS_COLORS,
                category_orders={"Status":STATUS_ORDER},
                template="plotly_white",
                height=420 if sumber_sel!="Keduanya" else 600,
                labels={"Jumlah":"Jumlah Mix/IBC"},
            )
            fig_ts.update_layout(
                legend=dict(orientation="h", y=1.08),
                margin=dict(t=60, b=40, l=10, r=10), xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_ts, use_container_width=True)

    st.divider()

    with st.expander("📋 Lihat Data Detail"):
        cols_show = [
            "Date","Product_Name","Plant","Batch_No","Mix_Code",
            "KF_Status",kc_s,vc_s,"Verif_Status","Comparison","Gap_Type"
        ]
        cols_show = [c for c in cols_show if c in df_p.columns]
        tbl = df_p[cols_show].rename(columns={
            "Date":"Tanggal","Product_Name":"Produk","Batch_No":"Batch","Mix_Code":"Mix",
            "KF_Status":"Status KF Final",
            kc_s:f"KF {PARAM_LABELS[sel_param]}",
            vc_s:f"Verif {PARAM_LABELS[sel_param]}",
            "Verif_Status":"Status Verif Final","Gap_Type":"Gap",
        })
        st.caption(f"{len(tbl):,} sampel")
        st.dataframe(tbl, use_container_width=True, hide_index=True, height=350)


