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
    st.caption("Garis = KimFis (semua mix) | Segitiga = Verifikator (sampling) | "
               "! = TP 2±/TP 3 terdeteksi (Not Pass) | !! = Gap terlalu jauh (beda arah / >1 level)")

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
            "Pilih Batch No (bisa lebih dari 1)",
            batch_dr_pool,
            placeholder="Pilih batch...",
            key="dr_batch"
        )

    # Mode tampilkan data
    dr_mode = st.radio(
        "Tampilkan data",
        ["Semua mix di batch ini", "Filter per tanggal verifikasi"],
        horizontal=True,
        key="dr_mode"
    )

    # Date range hanya muncul kalau mode filter verif dipilih
    dr_date_range = None
    if dr_mode == "Filter per tanggal verifikasi":
        vd_all = df_all["Verif_Date"].dropna()
        vd_min = vd_all.min().date()
        vd_max = vd_all.max().date()
        dr_date_range = st.date_input(
            "Rentang tanggal verifikasi",
            value=(vd_max, vd_max),
            min_value=vd_min,
            max_value=vd_max,
            key="dr_date"
        )

    st.divider()

    # ── BUILD DATA ────────────────────────────────────────────────
    if not dr_batches:
        st.info("Pilih minimal 1 Batch No untuk menampilkan chart.")
    else:
        # Ambil SEMUA mix dari batch yang dipilih (tidak filter verif)
        rpt_all = df_all.copy()
        if dr_prod != "Semua":
            rpt_all = rpt_all[rpt_all["Product_Name"] == dr_prod]
        rpt_all = rpt_all[rpt_all["Batch_No"].isin(dr_batches)]

        # Kalau mode filter verif: tentukan mix mana yang verif-nya
        # masuk range tanggal, tapi tetap tampilkan SEMUA mix di chart
        verif_mix_set = set()
        if dr_mode == "Filter per tanggal verifikasi" and dr_date_range and len(dr_date_range) == 2:
            vd1, vd2 = dr_date_range
            verif_mask = (
                rpt_all["Verif_Date"].notna() &
                (rpt_all["Verif_Date"].dt.date >= vd1) &
                (rpt_all["Verif_Date"].dt.date <= vd2)
            )
            verif_mix_set = set(
                rpt_all[verif_mask]["Sample_ID"].tolist()
            )

        if rpt_all.empty:
            st.info("Tidak ada data untuk filter yang dipilih.")
        else:
            groups = rpt_all.groupby(["Batch_No","Product_Name"], sort=False)

            for (batch_no, prod_name), grp in groups:
                # Sort Mix_Code sebagai angka bukan string (hindari 1,10,11,2,...)
                grp = grp.copy()
                grp["_mix_sort"] = pd.to_numeric(grp["Mix_Code"], errors="coerce").fillna(0)
                grp = grp.sort_values("_mix_sort").drop(columns="_mix_sort").reset_index(drop=True)

                # Kalau mode filter verif → hanya tampilkan mix yang
                # Sample_ID-nya ada di verif_mix_set, PLUS semua mix KimFis
                # untuk garis KimFis tetap lengkap.
                # KimFis selalu semua; verif hanya yang dalam range.
                mix_codes  = grp["Mix_Code"].tolist()
                sample_ids = grp["Sample_ID"].tolist()
                kf_status  = grp["KF_Status"].tolist()
                verif_status_raw = grp["Verif_Status"].tolist()
                comparison_raw   = grp["Comparison"].tolist()

                # Jika mode filter verif: hapus verif di mix yang bukan dalam range
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

                n_mix = len(mix_codes)

                # ── Ukuran chart ──────────────────────────────────
                chart_w = max(350, min(950, 180 + n_mix * 80))
                chart_h = 340

                # ── Judul proporsional, bagi 2 baris kalau panjang ──
                # Estimasi maks karakter per baris berdasarkan lebar chart
                chars_per_line = max(25, chart_w // 9)
                full_title = f"{prod_name} — Batch {batch_no}"

                if len(full_title) <= chars_per_line:
                    # Muat 1 baris
                    title_text = full_title
                else:
                    # Potong di " — Batch" supaya rapi
                    split_marker = " — Batch "
                    if split_marker in full_title:
                        part1 = prod_name
                        part2 = f"Batch {batch_no}"
                        # Kalau part1 masih terlalu panjang, potong dengan …
                        if len(part1) > chars_per_line:
                            part1 = part1[:chars_per_line - 1] + "…"
                        title_text = f"{part1}<br>{part2}"
                    else:
                        # Fallback: potong manual
                        title_text = (full_title[:chars_per_line] + "<br>"
                                      + full_title[chars_per_line:chars_per_line*2])

                title_size = 11 if n_mix <= 2 else 13
                # Kalau judul 2 baris, naikkan margin atas chart supaya tidak terpotong
                title_lines = title_text.count("<br>") + 1
                margin_top  = 50 + (title_lines - 1) * 18

                fig = go.Figure()

                # Garis referensi Pass
                fig.add_hline(y=0, line_dash="dash",
                              line_color="#2E8B57", line_width=1.5, opacity=0.55)

                # ── KimFis: garis + titik biru (semua mix) ───────
                kf_y = [STATUS_Y.get(s) for s in kf_status]
                kf_x_plot = [mix_codes[i] for i, y in enumerate(kf_y) if y is not None]
                kf_y_plot = [y for y in kf_y if y is not None]
                kf_s_plot = [kf_status[i] for i, y in enumerate(kf_y) if y is not None]

                if kf_x_plot:
                    fig.add_trace(go.Scatter(
                        x=kf_x_plot, y=kf_y_plot,
                        mode="lines+markers",
                        name="Kim-Fis",
                        line=dict(color="#4DA6FF", width=2),
                        marker=dict(symbol="circle", size=9,
                                    color="#4DA6FF",
                                    line=dict(color="#185FA5", width=1.5)),
                        hovertemplate="<b>Mix %{x}</b><br>KimFis: %{customdata}<extra></extra>",
                        customdata=kf_s_plot,
                    ))

                # ── Verifikator: segitiga merah (hanya yang sampling) ──
                # 1 mix/IBC total di chart → open triangle; lainnya solid
                vf_symbol = "triangle-up-open" if n_mix == 1 else "triangle-up"
                vf_x_plot = [mix_codes[i] for i, v in enumerate(vf_status) if v is not None]
                vf_y_plot = [STATUS_Y.get(v) for v in vf_status if v is not None]
                vf_s_plot = [v for v in vf_status if v is not None]

                if vf_x_plot:
                    fig.add_trace(go.Scatter(
                        x=vf_x_plot, y=vf_y_plot,
                        mode="markers",
                        name="Verifikator",
                        marker=dict(symbol=vf_symbol, size=14,
                                    color="#D32F2F",
                                    line=dict(color="#8B0000", width=2)),
                        hovertemplate="<b>Mix %{x}</b><br>Verif: %{customdata}<extra></extra>",
                        customdata=vf_s_plot,
                    ))

                # ── Anotasi per mix ───────────────────────────────
                legend_critical = False
                legend_far_gap  = False

                for i, mx in enumerate(mix_codes):
                    kf = kf_status[i]
                    vf = vf_status[i]
                    ky = STATUS_Y.get(kf)
                    vy = STATUS_Y.get(vf) if vf else None
                    # Gunakan index numerik untuk category axis
                    # supaya posisi anotasi tepat di atas titiknya
                    x_idx = i

                    # Cek apakah ada kondisi CRITICAL di mix ini
                    has_critical = (kf in CRITICAL) or (vf in CRITICAL)

                    # 1. TP 2±/TP 3 di KimFis → tanda ! merah di atas titik KF
                    if kf in CRITICAL and ky is not None:
                        fig.add_annotation(
                            x=x_idx, y=ky + 0.45,
                            text="<b>!</b>",
                            showarrow=False,
                            font=dict(size=13, color="#D32F2F"),
                            bgcolor="rgba(211,47,47,0.12)",
                            bordercolor="#D32F2F",
                            borderwidth=1,
                            borderpad=2,
                        )
                        legend_critical = True

                    # 2. TP 2±/TP 3 di Verif → tanda ! merah di atas titik Verif
                    #    Tapi hanya kalau posisinya beda dengan KF (hindari duplikat)
                    if vf in CRITICAL and vy is not None and ky != vy:
                        fig.add_annotation(
                            x=x_idx, y=vy + 0.45,
                            text="<b>!</b>",
                            showarrow=False,
                            font=dict(size=13, color="#D32F2F"),
                            bgcolor="rgba(211,47,47,0.12)",
                            bordercolor="#D32F2F",
                            borderwidth=1,
                            borderpad=2,
                        )
                        legend_critical = True

                    # 3. Gap terlalu jauh → tanda !! oranye
                    #    Hanya tampil kalau TIDAK ada kondisi CRITICAL di mix ini
                    #    Karena ! lebih prioritas dari !!
                    if (vf and is_far_gap(kf, vf)
                            and ky is not None and vy is not None
                            and not has_critical):
                        fig.add_annotation(
                            x=x_idx, y=vy + 0.45,
                            text="<b>!!</b>",
                            showarrow=False,
                            font=dict(size=11, color="#E65100"),
                            bgcolor="rgba(230,81,0,0.15)",
                            bordercolor="#E65100",
                            borderwidth=1.5,
                            borderpad=3,
                        )
                        legend_far_gap = True

                # Keterangan singkat di bawah chart
                notes = []
                if legend_critical:
                    notes.append("**!** = TP 2± / TP 3 terdeteksi — Not Pass, perlu Triangle Test")
                if legend_far_gap:
                    notes.append("**!!** = Gap terlalu jauh — beda >1 level atau beda arah")
                if notes:
                    st.caption("  |  ".join(notes))

                # ── Layout ────────────────────────────────────────
                fig.update_layout(
                    title=dict(text=title_text, font=dict(size=title_size),
                               x=0, xanchor="left"),
                    width=chart_w,
                    height=chart_h,
                    template="plotly_white",
                    legend=dict(orientation="h", y=1.18, x=0.5,
                                xanchor="center", font=dict(size=11)),
                    margin=dict(t=margin_top + 20, b=50, l=60, r=20),
                    xaxis=dict(
                        title="Mix / IBC",
                        type="category",
                        tickmode="array",
                        tickvals=mix_codes,
                        ticktext=[str(m) for m in mix_codes],
                        range=[-0.6, n_mix - 0.4],
                    ),
                    yaxis=dict(
                        title="Status",
                        tickmode="array",
                        tickvals=list(STATUS_Y.values()),
                        ticktext=list(STATUS_Y_LABEL.values()),
                        range=[-2.8, 3.8],
                        gridcolor="rgba(180,180,180,0.25)",
                        gridwidth=1,
                        zeroline=False,
                    ),
                )
                st.plotly_chart(fig, use_container_width=False)

    # ── Tabel Data Bersih — selalu tampil, tidak tergantung filter batch ──
    st.divider()
    st.subheader("📋 Data Bersih — Semua Data")
    st.caption("Diurutkan berdasarkan tanggal verifikasi terlama → terbaru. "
               "Yang belum diverifikasi muncul di bawah.")

    # Helper cari kolom analis
    def _get_col(df, no, suffix):
        for c in [f"A{no}_{suffix}", f"A{int(no)}_{suffix}", f"A{no}.0_{suffix}"]:
            if c in df.columns: return c
        return None

    # Sumber: df_all — semua data tanpa filter apapun (termasuk yg belum diverif)
    tbl_src = df_all.copy()
    # Tidak ada filter — semua mix/IBC ditampilkan

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
    # Semua baris tampil (termasuk yg belum diverif)
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
    total_verif   = (tbl_clean["Tgl Verifikasi"] != "").sum()
    total_mismatch= (tbl_clean["Comparison"] == "MISMATCH").sum()
    total_noverif = total_rows - total_verif

    st.caption(
        f"{total_rows:,} total mix/IBC  ·  "
        f"{total_verif:,} terverifikasi  ·  "
        f"{total_noverif:,} belum diverif  ·  "
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
