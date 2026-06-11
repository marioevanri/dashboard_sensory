"""tab4_shift_analyst.py — Tab 4 QC Sensory Dashboard."""

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
    """Render Tab 4."""
    st.subheader("Shift & Performa Analis")

    def norm_shift(v):
        s = str(v).strip()
        try:
            f = float(s)
            if f == int(f): return str(int(f))
        except: pass
        return s

    def get_analyst_col(dataframe, no, suffix):
        for candidate in [f"A{no}_{suffix}", f"A{int(no)}_{suffix}",
                           f"A{float(no)}_{suffix}", f"A{no}.0_{suffix}"]:
            if candidate in dataframe.columns:
                return candidate
        return None

    SHIFT_ORDER = ["1","1-2","2","2-3","3"]
    df_s = df.copy()
    df_s["Shift_Label"] = df_s["Shift_Code"].apply(norm_shift)
    df_s["Month"]       = pd.to_datetime(df_s["Date"]).dt.to_period("M").astype(str)

    st.divider()

    # Section 1
    st.subheader("Mismatch Rate per Shift")
    col_a, col_b = st.columns([1,1])
    with col_a:
        shift_grp = (
            df_s[df_s["Comparison"].isin(["MATCH","MISMATCH"])]
            .groupby("Shift_Label")["Comparison"]
            .value_counts().unstack(fill_value=0).reset_index()
        )
        for c in ["MATCH","MISMATCH"]:
            if c not in shift_grp.columns: shift_grp[c] = 0
        shift_grp["Total"]  = shift_grp["MATCH"] + shift_grp["MISMATCH"]
        shift_grp["Rate %"] = (shift_grp["MISMATCH"] / shift_grp["Total"] * 100).round(1)
        shift_grp["Label"]  = shift_grp.apply(
            lambda r: f"{r['Rate %']}%  |  {r['MISMATCH']} dari {r['Total']}", axis=1)
        shift_grp["Shift_Label"] = pd.Categorical(
            shift_grp["Shift_Label"], SHIFT_ORDER, ordered=True)
        shift_grp = shift_grp.sort_values("Shift_Label")
        fig_shift = px.bar(
            shift_grp, x="Rate %", y="Shift_Label", orientation="h",
            text="Label", color="Rate %",
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=320,
            labels={"Shift_Label":"Shift","Rate %":"Mismatch Rate (%)"},
        )
        fig_shift.update_traces(textposition="inside", insidetextanchor="middle")
        fig_shift.update_coloraxes(showscale=False)
        fig_shift.update_layout(
            yaxis={"categoryorder":"array","categoryarray":SHIFT_ORDER},
            margin=dict(t=20, b=20, l=10, r=10),
        )
        st.plotly_chart(fig_shift, use_container_width=True)
    with col_b:
        shift_stack = shift_grp.melt(
            id_vars="Shift_Label", value_vars=["MATCH","MISMATCH"],
            var_name="Comparison", value_name="Jumlah")
        fig_stack = px.bar(
            shift_stack, x="Shift_Label", y="Jumlah", color="Comparison",
            barmode="stack", text_auto=True,
            color_discrete_map={"MATCH":"#2E8B57","MISMATCH":"#D32F2F"},
            category_orders={"Shift_Label":SHIFT_ORDER},
            template="plotly_white", height=320,
            labels={"Shift_Label":"Shift","Jumlah":"Jumlah Sampel"},
        )
        fig_stack.update_layout(
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=40, b=20, l=10, r=10),
        )
        st.plotly_chart(fig_stack, use_container_width=True)

    st.divider()

    # Section 2
    st.subheader("Distribusi Status Parameter per Shift")
    sel_param_shift = st.selectbox(
        "Pilih Parameter:", PARAM_COLS,
        format_func=lambda x: PARAM_LABELS[x], key="shift_param")
    kc_shift = f"KF_{sel_param_shift}_Status"
    vc_shift = f"V_{sel_param_shift}_Status"
    sumber_shift = st.radio(
        "Tampilkan:", ["KimFis","Verifikator","Keduanya"],
        horizontal=True, key="shift_sumber")

    shift_param_rows = []
    for _, row in df_s.iterrows():
        shift = row["Shift_Label"]
        if kc_shift in df_s.columns and sumber_shift in ("KimFis","Keduanya"):
            s = row.get(kc_shift)
            if pd.notna(s) and s in STATUS_ORDER:
                shift_param_rows.append({"Status":s,"Shift":shift,"Sumber":"KimFis"})
        if vc_shift in df_s.columns and sumber_shift in ("Verifikator","Keduanya"):
            s = row.get(vc_shift)
            if pd.notna(s) and s in STATUS_ORDER:
                shift_param_rows.append({"Status":s,"Shift":shift,"Sumber":"Verifikator"})

    if shift_param_rows:
        sp_df = pd.DataFrame(shift_param_rows)
        sp_df["Status"] = pd.Categorical(sp_df["Status"], STATUS_ORDER, ordered=True)
        sp_df["Shift"]  = pd.Categorical(sp_df["Shift"],  SHIFT_ORDER,  ordered=True)
        sp_agg = (sp_df.groupby(["Status","Shift","Sumber"]).size()
                  .reset_index(name="Jumlah").sort_values(["Shift","Status"]))
        fig_sp = px.bar(
            sp_agg, x="Shift", y="Jumlah", color="Status", barmode="group",
            facet_row="Sumber" if sumber_shift=="Keduanya" else None,
            text_auto=True,
            color_discrete_map=STATUS_COLORS,
            category_orders={"Status":STATUS_ORDER,"Shift":SHIFT_ORDER},
            template="plotly_white",
            height=420 if sumber_shift!="Keduanya" else 650,
            labels={"Jumlah":"Jumlah Mix/IBC","Shift":"Shift"},
        )
        fig_sp.update_traces(textposition="outside")
        fig_sp.update_layout(
            legend=dict(orientation="h", y=1.08),
            margin=dict(t=60, b=20, l=10, r=10),
            xaxis_title="Shift", yaxis_title="Jumlah Mix/IBC",
        )
        if sumber_shift == "Keduanya":
            fig_sp.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        st.plotly_chart(fig_sp, use_container_width=True)

    st.divider()

    # Section 3 — Performa Analis
    st.subheader("Performa Analis vs Verifikator")

    analyst_rows = []
    for _, row in df_s[df_s["Verif_Status"].notna()].iterrows():
        verif_st = row["Verif_Status"]
        for no in [1,2,3]:
            name_col   = get_analyst_col(df_s, no, "Name")
            status_col = get_analyst_col(df_s, no, "Status")
            if not name_col or not status_col: continue
            aname = row.get(name_col)
            ast   = row.get(status_col)
            if pd.isna(aname) or pd.isna(ast): continue
            aname = str(aname).strip()
            if aname in ("","nan"): continue
            analyst_rows.append({
                "Analyst":      aname.title(),
                "A_Status":     ast,
                "Verif_Status": verif_st,
                "Match":        ast == verif_st,
                "Shift":        row["Shift_Label"],
                "Month":        row["Month"],
            })

    if analyst_rows:
        an_df = pd.DataFrame(analyst_rows)

        # 3A — Mismatch rate
        an_summary = (
            an_df.groupby("Analyst")
            .agg(Total=("Match","count"), Match=("Match","sum"))
            .reset_index()
        )
        an_summary["Mismatch"] = an_summary["Total"] - an_summary["Match"]
        an_summary["Rate %"]   = (an_summary["Mismatch"] / an_summary["Total"] * 100).round(1)
        an_summary["Label"]    = an_summary.apply(
            lambda r: f"{r['Rate %']}%  |  {r['Mismatch']} dari {r['Total']}", axis=1)
        an_summary = an_summary.sort_values("Rate %", ascending=True)
        fig_an = px.bar(
            an_summary, x="Rate %", y="Analyst", orientation="h",
            text="Label", color="Rate %",
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=max(350, len(an_summary)*38),
            labels={"Analyst":"Analis","Rate %":"Mismatch Rate (%)"},
        )
        fig_an.update_traces(textposition="inside", insidetextanchor="middle")
        fig_an.update_coloraxes(showscale=False)
        fig_an.update_layout(
            yaxis={"categoryorder":"total ascending"},
            margin=dict(t=20, b=20, l=10, r=10),
        )
        st.plotly_chart(fig_an, use_container_width=True)

        st.divider()

        # 3B — Proporsi status
        st.subheader("Proporsi Status tiap Analis")
        an_status = an_df.groupby(["Analyst","A_Status"]).size().reset_index(name="Jumlah")
        an_status = an_status[an_status["A_Status"].isin(STATUS_ORDER)]
        an_status["A_Status"] = pd.Categorical(an_status["A_Status"], STATUS_ORDER, ordered=True)
        an_total = an_status.groupby("Analyst")["Jumlah"].transform("sum")
        an_status["Persen"]     = (an_status["Jumlah"] / an_total * 100).round(1)
        an_status["Label_Text"] = an_status["Persen"].apply(
            lambda x: f"{x:.0f}%" if x >= 5 else "")
        analyst_order = an_summary.sort_values("Rate %", ascending=False)["Analyst"].tolist()
        fig_prop = px.bar(
            an_status.sort_values("A_Status"),
            x="Analyst", y="Persen", color="A_Status",
            barmode="stack", text="Label_Text",
            color_discrete_map=STATUS_COLORS,
            category_orders={"A_Status":STATUS_ORDER,"Analyst":analyst_order},
            template="plotly_white", height=420,
            labels={"Analyst":"Analis","Persen":"Proporsi (%)","A_Status":"Status"},
        )
        fig_prop.update_traces(textposition="inside", insidetextanchor="middle")
        fig_prop.update_layout(
            legend=dict(orientation="h", y=1.08),
            margin=dict(t=60, b=40, l=10, r=10),
            xaxis_tickangle=-45, yaxis_title="Proporsi (%)", xaxis_title="",
        )
        st.plotly_chart(fig_prop, use_container_width=True)

        st.divider()

        # 3C — Kecenderungan Analis vs Verifikator
        st.subheader("Kecenderungan Pilihan Analis vs Verifikator")

        tendency_rows = []
        for analyst, grp in an_df.groupby("Analyst"):
            total     = len(grp)
            match_n   = (grp["A_Status"] == grp["Verif_Status"]).sum()
            longgar_n = ((grp["A_Status"] == "Pass") & (grp["Verif_Status"] != "Pass")).sum()
            ketat_n   = ((grp["A_Status"] != "Pass") & (grp["Verif_Status"] == "Pass")).sum()
            beda_n    = (
                (grp["A_Status"] != grp["Verif_Status"]) &
                (grp["A_Status"] != "Pass") &
                (grp["Verif_Status"] != "Pass")
            ).sum()
            tendency_rows.append({
                "Analyst":        analyst,
                "Match":          int(match_n),
                "Terlalu Longgar":int(longgar_n),
                "Terlalu Ketat":  int(ketat_n),
                "Beda Deviasi":   int(beda_n),
                "Total":          total,
            })

        tend_df = pd.DataFrame(tendency_rows)
        for col in ["Match","Terlalu Longgar","Terlalu Ketat","Beda Deviasi"]:
            tend_df[f"{col} %"] = (tend_df[col] / tend_df["Total"] * 100).round(1)

        tend_melt = tend_df.melt(
            id_vars="Analyst",
            value_vars=["Match %","Terlalu Longgar %","Terlalu Ketat %","Beda Deviasi %"],
            var_name="Kategori", value_name="Persen"
        )
        tend_melt["Kategori"] = tend_melt["Kategori"].str.replace(" %","")
        tend_melt["Label"] = tend_melt["Persen"].apply(
            lambda x: f"{x:.0f}%" if x >= 5 else "")

        kat_order  = ["Match","Terlalu Longgar","Terlalu Ketat","Beda Deviasi"]
        kat_colors = {
            "Match":          "#2E8B57",
            "Terlalu Longgar":"#4DA6FF",
            "Terlalu Ketat":  "#D32F2F",
            "Beda Deviasi":   "#F5A623",
        }

        fig_tend = px.bar(
            tend_melt,
            x="Persen", y="Analyst",
            color="Kategori", barmode="stack",
            text="Label", orientation="h",
            color_discrete_map=kat_colors,
            category_orders={"Kategori": kat_order, "Analyst": analyst_order},
            template="plotly_white",
            height=max(400, len(tend_df)*38),
            labels={"Analyst":"Analis","Persen":"Proporsi (%)"},
        )
        fig_tend.update_traces(textposition="inside", insidetextanchor="middle")
        fig_tend.update_layout(
            legend=dict(orientation="h", y=1.08),
            margin=dict(t=60, b=20, l=10, r=10),
            xaxis_title="Proporsi (%)", yaxis_title="",
            xaxis=dict(range=[0,100]),
        )
        st.plotly_chart(fig_tend, use_container_width=True)

        st.divider()

        # ── Drill down: Heatmap per analis ─────────────────────
        st.subheader("Detail Kecenderungan — Heatmap per Analis")

        sel_analyst = st.selectbox(
            "Pilih Analis:",
            sorted(an_df["Analyst"].unique()),
            key="analyst_heatmap"
        )

        an_heat = an_df[an_df["Analyst"] == sel_analyst][["A_Status","Verif_Status"]].copy()
        an_heat = an_heat[
            an_heat["A_Status"].isin(STATUS_ORDER) &
            an_heat["Verif_Status"].isin(STATUS_ORDER)
        ]

        if not an_heat.empty:
            an_pivot = (
                an_heat.groupby(["A_Status","Verif_Status"])
                .size().reset_index(name="Jumlah")
                .pivot_table(index="A_Status", columns="Verif_Status",
                             values="Jumlah", fill_value=0)
            )
            vr = [s for s in STATUS_ORDER if s in an_pivot.index]
            vc = [s for s in STATUS_ORDER if s in an_pivot.columns]
            an_pivot = an_pivot.loc[vr, vc]

            # ── FIXED: angka absolut di sel, sel 0 dikosongkan ──
            text_matrix = []
            for row_s in vr:
                row_text = []
                for col_s in vc:
                    val = int(an_pivot.loc[row_s, col_s])
                    row_text.append(str(val) if val > 0 else "")
                text_matrix.append(row_text)

            fig_an_heat = px.imshow(
                an_pivot,
                color_continuous_scale=["#ffffff","#185FA5"],
                aspect="auto", template="plotly_white", height=400,
                labels={
                    "x": "Status Verifikator (Ground Truth)",
                    "y": "Status Analis",
                    "color": "Jumlah Batch"
                },
            )
            fig_an_heat.update_traces(
                text=text_matrix,
                texttemplate="%{text}",
                textfont=dict(size=13),
            )
            # Highlight diagonal
            for i, status in enumerate(vr):
                if status in vc:
                    j = vc.index(status)
                    fig_an_heat.add_shape(
                        type="rect",
                        x0=j-0.5, x1=j+0.5, y0=i-0.5, y1=i+0.5,
                        line=dict(color="#2E8B57", width=2.5),
                        fillcolor="rgba(0,0,0,0)",
                    )
            fig_an_heat.update_layout(
                margin=dict(t=50, b=20, l=10, r=60),
                xaxis_title="Status Verifikator (Ground Truth)",
                yaxis_title="Status Analis",
                coloraxis_showscale=True,
                coloraxis_colorbar=dict(title="Jumlah"),
                title=f"{sel_analyst} — Jumlah batch: analis (baris) vs verifikator (kolom)",
            )
            st.plotly_chart(fig_an_heat, use_container_width=True)

    else:
        st.info("Data analis tidak tersedia — pastikan sudah Refresh Data setelah update load_data.py.")


    # ══════════════════════════════════════════════════════════════════
