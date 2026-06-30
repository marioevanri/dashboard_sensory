"""tab5_daily_report.py — Tab 5 QC Sensory Dashboard."""

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
import io


def render(df: pd.DataFrame, df_all: pd.DataFrame, all_prods: list) -> None:
    """Render Tab 5."""
    st.subheader("Daily Report — Status KimFis vs Verifikator")

    # ── Pengantar storytelling dari Tab 4 ────────────────────────
    n_verif   = df["Verif_Status"].notna().sum()
    n_pass    = (df["Verif_Status"] == "Pass").sum()
    n_tp1     = df["Verif_Status"].isin(["TP 1-","TP 1+"]).sum()
    n_tp2     = df["Verif_Status"].isin(["TP 2-","TP 2+"]).sum()
    n_tp3     = (df["Verif_Status"] == "TP 3").sum()
    n_not_pass = n_tp2 + n_tp3

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:12px;
                    font-size:14px; color:#1a1a1a; line-height:1.8;">
        Di Tab Shift & Analis terlihat pola bias analis dan shift dengan gap tertinggi.
        &nbsp; Tab ini menyajikan <b>detail per batch</b> untuk keputusan release harian
        dan ekspor data ke database.
        <br>
        <span style="font-size:12px; color:#888;">
        Chart bisa di-screenshot untuk dilampirkan ke email laporan harian.
        &nbsp;·&nbsp; Tabel data bersih siap di-export ke CSV / Excel untuk database.
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI Mini — distribusi status periode filter ───────────────
    if n_verif > 0:
        pct_pass = round(n_pass / n_verif * 100, 1)
        pct_tp1  = round(n_tp1  / n_verif * 100, 1)
        pct_tp2  = round(n_tp2  / n_verif * 100, 1)
        pct_tp3  = round(n_tp3  / n_verif * 100, 1)

        # KPI pakai HTML supaya keterangan tidak terpotong
        kpi_items = [
            ("Total Terverif", f"{n_verif:,}", "", "#185FA5"),
            ("✅ Pass",         f"{n_pass:,}",  f"{pct_pass}%", "#2E8B57"),
            ("🟡 TP 1",         f"{n_tp1:,}",   f"{pct_tp1}% — masih release", "#D85A30"),
            ("🟠 TP 2",         f"{n_tp2:,}",   f"{pct_tp2}% — blok sementara, tunggu Triangle Test", "#E65100"),
            ("🔴 TP 3",         f"{n_tp3:,}",   f"{pct_tp3}% — BLOK segera", "#D32F2F"),
        ]
        cols = st.columns(5)
        for col, (label, value, note, color) in zip(cols, kpi_items):
            note_html = (
                f'<div style="font-size:10.5px; color:#666; margin-top:3px; '
                f'line-height:1.3; word-break:break-word;">{note}</div>'
            ) if note else ""
            with col:
                st.markdown(
                    f"""
                    <div style="background:#f8f9fa; border-radius:8px;
                                padding:10px 12px; border-top:3px solid {color};">
                        <div style="font-size:11px; color:#888; margin-bottom:2px;">
                            {label}
                        </div>
                        <div style="font-size:22px; font-weight:700; color:{color};">
                            {value}
                        </div>
                        {note_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if n_not_pass > 0:
            st.warning(
                f"⚠️ **{n_not_pass} sampel Not Pass** (TP 2: {n_tp2} · TP 3: {n_tp3}) "
                f"pada periode yang dipilih. "
                f"Untuk batch **preshipment/eksport**: semua mix wajib Pass — "
                f"TP 1 sekalipun tidak diizinkan."
            )
        else:
            st.success(
                f"✅ Semua {n_verif:,} sampel terverifikasi dalam periode ini "
                f"berstatus TP 1 atau Pass — tidak ada Not Pass."
            )

    st.caption(
        "Garis = KimFis (semua mix) | Segitiga = Verifikator (sampling) | "
        "! = TP 2±/TP 3 terdeteksi (Not Pass) | !! = Gap terlalu jauh (beda arah / >1 level)"
    )

    # ── HELPERS ──────────────────────────────────────────────────
    STATUS_Y = {
        "TP 2-": -2, "TP 1-": -1,
        "Pass":   0,
        "TP 1+":  1, "TP 2+":  2, "TP 3": 3
    }
    STATUS_Y_LABEL = {-2:"TP 2-", -1:"TP 1-", 0:"Pass",
                      1:"TP 1+", 2:"TP 2+", 3:"TP 3"}
    CRITICAL = {"TP 2-","TP 2+","TP 3"}

    def is_far_gap(kf, vf):
        """Gap terlalu jauh: beda >1 level ATAU beda arah (satu +, satu -)."""
        if not kf or not vf or kf == vf: return False
        ky = STATUS_Y.get(kf, 0)
        vy = STATUS_Y.get(vf, 0)
        # Beda arah: satu negatif satu positif (bukan Pass)
        if ky * vy < 0 and kf != "Pass" and vf != "Pass":
            return True
        # Beda lebih dari 1 level di skala ordinal
        if abs(ky - vy) > 1:
            return True
        return False

    # ── FILTER ───────────────────────────────────────────────────
    import datetime as _dt

    # Shortcut "Verifikasi Hari Ini"
    vd_all_dates = df_all["Verif_Date"].dropna()
    latest_verif = vd_all_dates.max().date() if not vd_all_dates.empty else None

    sc1, sc2, sc3 = st.columns([1, 1, 2])
    with sc1:
        today_btn = st.button(
            "📅 Verifikasi Terbaru",
            help=f"Filter otomatis ke tanggal verifikasi terbaru ({latest_verif})",
            use_container_width=True,
            key="btn_today",
        )
    with sc2:
        st.caption(
            f"Tanggal verif terbaru: **{latest_verif}**"
            if latest_verif else "Tidak ada data verifikasi"
        )

    # Kalau tombol ditekan, set session state ke mode filter verif + tanggal terbaru
    if today_btn:
        st.session_state["dr_mode"]      = "Filter per tanggal verifikasi"
        st.session_state["_today_quick"] = True

    st.markdown("")
    dr1, dr2 = st.columns([1, 1])

    with dr1:
        dr_prod = st.selectbox(
            "Pilih Produk",
            ["Semua"] + all_prods,
            key="dr_prod"
        )

    with dr2:
        if dr_prod != "Semua":
            batch_dr_pool = sorted(
                df_all[df_all["Product_Name"] == dr_prod]["Batch_No"]
                .dropna().unique()
            )
        else:
            batch_dr_pool = sorted(df_all["Batch_No"].dropna().unique())

        dr_batches = st.multiselect(
            "Pilih Batch No (opsional — kosongkan untuk lihat semua batch di tanggal)",
            batch_dr_pool,
            placeholder="Pilih batch... (opsional)",
            key="dr_batch"
        )

    # Mode tampilkan data
    dr_mode = st.radio(
        "Tampilkan data",
        ["Semua mix di batch ini", "Filter per tanggal verifikasi"],
        horizontal=True,
        key="dr_mode"
    )

    # Date range
    dr_date_range = None
    if dr_mode == "Filter per tanggal verifikasi":
        vd_min = vd_all_dates.min().date() if not vd_all_dates.empty else _dt.date.today()
        vd_max = vd_all_dates.max().date() if not vd_all_dates.empty else _dt.date.today()
        # Default ke tanggal terbaru (atau quick filter)
        default_date = (vd_max, vd_max)
        dr_date_range = st.date_input(
            "Rentang tanggal verifikasi",
            value=default_date,
            min_value=vd_min,
            max_value=vd_max,
            key="dr_date"
        )

    st.divider()

    # ── BUILD DATA ────────────────────────────────────────────────
    # Mode tanggal: tidak perlu pilih batch — langsung filter by verif date
    if dr_mode == "Filter per tanggal verifikasi" and dr_date_range and len(dr_date_range) == 2:
        vd1, vd2 = dr_date_range
        rpt_date = df_all.copy()
        if dr_prod != "Semua":
            rpt_date = rpt_date[rpt_date["Product_Name"] == dr_prod]
        if dr_batches:
            rpt_date = rpt_date[rpt_date["Batch_No"].isin(dr_batches)]

        # Tampilkan semua mix dari batch yang punya verifikasi di range tsb
        verif_mask = (
            rpt_date["Verif_Date"].notna() &
            (rpt_date["Verif_Date"].dt.date >= vd1) &
            (rpt_date["Verif_Date"].dt.date <= vd2)
        )
        batches_in_range = rpt_date[verif_mask]["Batch_No"].unique()

        if len(batches_in_range) == 0:
            st.info(f"Tidak ada verifikasi pada {vd1} s/d {vd2}.")
        else:
            rpt_all = rpt_date[rpt_date["Batch_No"].isin(batches_in_range)]
            verif_mix_set = set(rpt_date[verif_mask]["Sample_ID"].tolist())
            st.caption(
                f"📅 {vd1} s/d {vd2} — "
                f"**{len(batches_in_range)} batch** ditemukan dengan "
                f"**{verif_mask.sum()} mix/IBC** terverifikasi."
            )
            _render_charts(
                rpt_all, verif_mix_set,
                dr_mode, STATUS_Y, STATUS_Y_LABEL, CRITICAL, is_far_gap
            )

    elif dr_batches:
        rpt_all = df_all.copy()
        if dr_prod != "Semua":
            rpt_all = rpt_all[rpt_all["Product_Name"] == dr_prod]
        rpt_all = rpt_all[rpt_all["Batch_No"].isin(dr_batches)]

        if rpt_all.empty:
            st.info("Tidak ada data untuk filter yang dipilih.")
        else:
            _render_charts(
                rpt_all, set(),
                "Semua mix di batch ini", STATUS_Y, STATUS_Y_LABEL, CRITICAL, is_far_gap
            )
    else:
        st.info(
            "💡 Pilih batch di atas, atau gunakan **Filter per tanggal verifikasi** "
            "untuk melihat chart verifikasi tanpa harus pilih batch manual."
        )

    # ── Tabel Data Bersih ─────────────────────────────────────────
    st.divider()
    st.subheader("📋 Data Bersih")

    # Helper cari kolom analis
    def _get_col(df, no, suffix):
        for c in [f"A{no}_{suffix}", f"A{int(no)}_{suffix}", f"A{no}.0_{suffix}"]:
            if c in df.columns: return c
        return None

    # Sumber: filter by batch kalau ada, fallback ke df_all
    if dr_batches:
        tbl_src = df_all[df_all["Batch_No"].isin(dr_batches)].copy()
        st.caption(
            f"Menampilkan data untuk batch yang dipilih: "
            f"**{', '.join(dr_batches)}**  ·  "
            f"Hapus pilihan batch untuk lihat semua data."
        )
    else:
        tbl_src = df_all.copy()
        st.caption(
            "Menampilkan semua data. Pilih batch di atas untuk filter lebih spesifik."
        )

    clean_rows = []
    for _, r in tbl_src.iterrows():
        clean_rows.append({
            "Tgl Analisa":   r.get("Date"),
            "Produk/Grade":  r.get("Product_Name"),
            "No Batch":      r.get("Batch_No"),
            "Mix/IBC":       r.get("Mix_Code"),
            "Shift":         r.get("Shift_Code"),
            "Plant":         r.get("Plant"),
            "A1 - Nama":     str(r.get(_get_col(tbl_src,1,"Name") or "","") or "").strip().title() or None,
            "A1 - Status":   r.get(_get_col(tbl_src,1,"Status") or "", None),
            "A2 - Nama":     str(r.get(_get_col(tbl_src,2,"Name") or "","") or "").strip().title() or None,
            "A2 - Status":   r.get(_get_col(tbl_src,2,"Status") or "", None),
            "A3 - Nama":     str(r.get(_get_col(tbl_src,3,"Name") or "","") or "").strip().title() or None,
            "A3 - Status":   r.get(_get_col(tbl_src,3,"Status") or "", None),
            "Status KimFis": r.get("KF_Status"),
            "Remark Analis": r.get("Remark_Analyst"),
            "Tgl Verifikasi":r.get("Verif_Date"),
            "Verifikator":   str(r.get("Verif_Name","") or "").strip().title() or None,
            "Status Verif":  r.get("Verif_Status"),
            "Remark Verif":  r.get("Remark_Verif"),
            "Comparison":    r.get("Comparison"),
            "Gap":           r.get("Gap_Type"),
        })

    tbl_clean = pd.DataFrame(clean_rows)

    # Bersihkan nilai "nan" string
    for col in tbl_clean.columns:
        tbl_clean[col] = tbl_clean[col].apply(
            lambda x: None if str(x).strip().lower() in ("nan","none","") else x
        )

    # Sort: Tgl Analisa ascending → Batch → Mix/IBC sebagai angka
    # Semua baris tampil (termasuk yg tidak diverifikasi)
    tbl_clean["_date_sort"] = pd.to_datetime(tbl_clean["Tgl Analisa"], errors="coerce")
    tbl_clean["_mix_sort"]  = pd.to_numeric(tbl_clean["Mix/IBC"], errors="coerce").fillna(0)
    tbl_clean = tbl_clean.sort_values(
        ["_date_sort", "No Batch", "_mix_sort"],
        ascending=[True, True, True],
        na_position="last"
    ).drop(columns=["_date_sort","_mix_sort"]).reset_index(drop=True)

    # Format tanggal ke string setelah sort
    for dc in ["Tgl Analisa","Tgl Verifikasi"]:
        if dc in tbl_clean.columns:
            tbl_clean[dc] = pd.to_datetime(
                tbl_clean[dc], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            # Ganti "NaT" string jadi kosong supaya rapi di tabel
            tbl_clean[dc] = tbl_clean[dc].where(tbl_clean[dc] != "NaT", "")

    total_rows    = len(tbl_clean)
    total_verif   = tbl_clean["Status Verif"].notna().sum()
    total_mismatch= (tbl_clean["Comparison"] == "MISMATCH").sum()
    total_noverif = total_rows - total_verif

    st.caption(
        f"{total_rows:,} total mix/IBC  ·  "
        f"{total_verif:,} terverifikasi  ·  "
        f"{total_noverif:,} tidak diverifikasi  ·  "
        f"{total_mismatch:,} mismatch"
    )

    st.dataframe(tbl_clean, use_container_width=True, hide_index=True, height=500)

    st.markdown("**Download data bersih:**")
    _dl1, _dl2 = st.columns(2)
    with _dl1:
        st.download_button(
            "⬇️ CSV", tbl_clean.to_csv(index=False),
            "sensory_clean.csv", "text/csv",
            use_container_width=True,
        )
    with _dl2:
        try:
            import io as _io
            _buf = _io.BytesIO()
            tbl_clean.to_excel(_buf, index=False, engine="openpyxl")
            st.download_button(
                "⬇️ Excel", _buf.getvalue(),
                "sensory_clean.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except:
            pass

def _render_charts(rpt_all, verif_mix_set, dr_mode,
                   STATUS_Y, STATUS_Y_LABEL, CRITICAL, is_far_gap):
    """Render scatter chart KimFis vs Verif per batch."""
    import plotly.graph_objects as go

    STATUS_Y_COLORS = {
        "TP 2-":"#8B0000","TP 1-":"#D85A30",
        "Pass":"#2E8B57",
        "TP 1+":"#4DA6FF","TP 2+":"#1565C0","TP 3":"#0D0D5C",
    }

    groups = rpt_all.groupby(["Batch_No","Product_Name"], sort=False)

    for (batch_no, prod_name), grp in groups:
        grp = grp.copy()
        grp["_mix_sort"] = pd.to_numeric(grp["Mix_Code"], errors="coerce").fillna(0)
        grp = grp.sort_values("_mix_sort").drop(columns="_mix_sort").reset_index(drop=True)

        mix_codes        = grp["Mix_Code"].tolist()
        sample_ids       = grp["Sample_ID"].tolist()
        kf_status        = grp["KF_Status"].tolist()
        verif_status_raw = grp["Verif_Status"].tolist()
        comparison_raw   = grp["Comparison"].tolist()

        if dr_mode == "Filter per tanggal verifikasi" and verif_mix_set:
            vf_status  = [
                v if sid in verif_mix_set else None
                for v, sid in zip(verif_status_raw, sample_ids)
            ]
            comparison = [
                c if sid in verif_mix_set else "NO_VERIFICATION"
                for c, sid in zip(comparison_raw, sample_ids)
            ]
        else:
            vf_status  = verif_status_raw
            comparison = comparison_raw

        n_mix    = len(mix_codes)
        chart_w  = max(350, min(950, 180 + n_mix * 80))
        chart_h  = 340

        chars_per_line = max(25, chart_w // 9)
        full_title     = f"{prod_name} — Batch {batch_no}"
        if len(full_title) <= chars_per_line:
            title_text = full_title
        else:
            part1 = prod_name
            if len(part1) > chars_per_line:
                part1 = part1[:chars_per_line-1] + "…"
            title_text = f"{part1}<br>Batch {batch_no}"

        title_lines = title_text.count("<br>") + 1
        margin_top  = 50 + (title_lines - 1) * 18

        fig = go.Figure()

        # KimFis line
        ky_vals = [STATUS_Y.get(k) for k in kf_status]
        kf_colors = [STATUS_Y_COLORS.get(k,"#aaa") for k in kf_status]
        fig.add_trace(go.Scatter(
            x=mix_codes, y=ky_vals, mode="lines+markers",
            name="KimFis", line=dict(color="#185FA5", width=1.5, dash="dot"),
            marker=dict(size=8, color=kf_colors, line=dict(color="#185FA5",width=1.5)),
            text=[f"KF: {k}" for k in kf_status],
            hovertemplate="%{text}<extra></extra>",
        ))

        # Verif markers
        vf_y       = []
        vf_colors  = []
        vf_text    = []
        vf_symbols = []
        for x_idx, (vf, cmp, kf) in enumerate(zip(vf_status, comparison, kf_status)):
            vy = STATUS_Y.get(vf) if vf else None
            vf_y.append(vy)
            vf_colors.append(STATUS_Y_COLORS.get(vf,"#aaa") if vf else "rgba(0,0,0,0)")
            vf_text.append(f"Verif: {vf} ({cmp})" if vf else "Belum diverif")
            # Pakai segitiga bolong kalau: hanya 1 mix ATAU status sama dengan KimFis
            # supaya titik KimFis di bawahnya tetap terlihat
            use_open = (n_mix == 1) or (vf == kf)
            vf_symbols.append("triangle-up-open" if use_open else "triangle-up")

        fig.add_trace(go.Scatter(
            x=mix_codes, y=vf_y, mode="markers",
            name="Verifikator",
            marker=dict(
                symbol=vf_symbols, size=14,
                color=vf_colors,
                line=dict(color="#EF9F27", width=2),
            ),
            text=vf_text,
            hovertemplate="%{text}<extra></extra>",
        ))

        # Anotasi ! dan !!
        legend_critical = False
        legend_far_gap  = False
        for x_idx, (kf, vf, cmp) in enumerate(zip(kf_status, vf_status, comparison)):
            ky = STATUS_Y.get(kf)
            vy = STATUS_Y.get(vf) if vf else None
            has_critical = (kf in CRITICAL) or (vf in CRITICAL if vf else False)

            if kf in CRITICAL and ky is not None:
                fig.add_annotation(
                    x=mix_codes[x_idx], y=ky+0.45, text="<b>!</b>",
                    showarrow=False, font=dict(size=13,color="#D32F2F"),
                    bgcolor="rgba(211,47,47,0.12)", bordercolor="#D32F2F",
                    borderwidth=1, borderpad=2,
                )
                legend_critical = True
            if vf in CRITICAL and vy is not None and ky != vy:
                fig.add_annotation(
                    x=mix_codes[x_idx], y=vy+0.45, text="<b>!</b>",
                    showarrow=False, font=dict(size=13,color="#D32F2F"),
                    bgcolor="rgba(211,47,47,0.12)", bordercolor="#D32F2F",
                    borderwidth=1, borderpad=2,
                )
                legend_critical = True
            if vf and is_far_gap(kf, vf) and ky is not None and vy is not None and not has_critical:
                fig.add_annotation(
                    x=mix_codes[x_idx], y=vy+0.45, text="<b>!!</b>",
                    showarrow=False, font=dict(size=11,color="#E65100"),
                    bgcolor="rgba(230,81,0,0.15)", bordercolor="#E65100",
                    borderwidth=1.5, borderpad=3,
                )
                legend_far_gap = True

        notes = []
        if legend_critical: notes.append("**!** = TP 2± / TP 3 terdeteksi — Not Pass")
        if legend_far_gap:  notes.append("**!!** = Gap terlalu jauh — beda >1 level atau beda arah")
        if notes: st.caption("  |  ".join(notes))

        fig.update_layout(
            title=dict(text=title_text, font=dict(size=13 if n_mix > 2 else 11), x=0, xanchor="left"),
            width=chart_w, height=chart_h,
            template="plotly_white",
            legend=dict(orientation="h", y=1.18, x=0.5, xanchor="center", font=dict(size=11)),
            margin=dict(t=margin_top+20, b=50, l=60, r=20),
            xaxis=dict(title="Mix / IBC", type="category",
                       tickmode="array", tickvals=mix_codes,
                       ticktext=[str(m) for m in mix_codes],
                       range=[-0.6, n_mix-0.4]),
            yaxis=dict(title="Status", tickmode="array",
                       tickvals=list(STATUS_Y.values()),
                       ticktext=list(STATUS_Y_LABEL.values()),
                       range=[-2.8,3.8],
                       gridcolor="rgba(180,180,180,0.25)", zeroline=False),
        )
        st.plotly_chart(fig, use_container_width=False)