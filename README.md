# 🧪 QC Sensory Dashboard

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-Visualization-3F4F75?style=flat&logo=plotly&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=flat&logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-30%20passed-2E8B57?style=flat&logo=pytest&logoColor=white)
[![GitHub](https://img.shields.io/badge/GitHub-marioevanri-181717?style=flat&logo=github)](https://github.com/marioevanri)

Dashboard interaktif untuk analisis data evaluasi sensory produk krimer & susu di lingkungan manufaktur.  
Dirancang untuk audience luas — QC, R&D, Produksi, Manager, hingga orang awam.

 **Data:** ~6,286 mix/IBC · Jan–Des 2025 · 2 Plant · 7 parameter sensory

---

##  Latar Belakang

Di industri manufaktur produk susu dan krimer, setiap batch produksi dievaluasi secara sensory oleh **3 analis lab Kimia-Fisika (KimFis)** yang kemudian hasilnya diverifikasi oleh **Verifikator** (ground truth). Proses ini menghasilkan data yang perlu dimonitor secara sistematis untuk:

- Memastikan konsistensi kualitas produk antar batch dan shift
- Mendeteksi gap (perbedaan) antara penilaian KimFis dan Verifikator
- Menganalisis performa dan kecenderungan bias tiap analis
- Mengidentifikasi parameter dan produk yang paling sering menyimpang dari standar
- Menghasilkan laporan harian yang siap digunakan sebagai referensi keputusan release

**KPI Utama:**
- 🔴 **0 complaint** dari customer
- 🔵 **100% approval** untuk sampel preshipment/eksport

---

##  Memahami Status Sensory

Sebelum masuk ke fitur dashboard, ini istilah kunci yang dipakai berulang di seluruh dokumen ini — biar nggak perlu nebak-nebak pas baca bagian selanjutnya.

Tiap sampel dinilai pakai skala 6 tingkat, dari yang paling "kurang dari standar" sampai paling "lebih dari standar":

```
TP 2-  ←  TP 1-  ←  Pass  →  TP 1+  →  TP 2+       (TP 3 = kategori terpisah, off-taste)
```

| Status | Artinya | Konsekuensi |
|---|---|---|
| **Pass** | Sesuai standar | Aman direlease |
| **TP 1- / TP 1+** | Sedikit di bawah (-) atau di atas (+) standar | Masih boleh direlease, dengan catatan |
| **TP 2- / TP 2+** | Cukup jauh dari standar | Ditahan sementara, wajib Triangle Test dulu sebelum diputuskan release atau blok |
| **TP 3** | Off-taste — rasa/aroma menyimpang jauh dari standar | Langsung ditahan/blok |

**Soal arah (-/+):** dua-duanya sama-sama dianggap penyimpangan dari standar, cuma beda arah — "-" berarti parameternya kurang kuat/kurang terasa dari yang seharusnya, "+" berarti kelewat kuat/berlebih dari yang seharusnya. Contoh: "TP 1-" pada parameter Creamy berarti rasa creamy-nya kurang, "TP 1+" berarti creamy-nya kelewat kuat.

**Khusus produk preshipment (mau diekspor):** aturannya lebih ketat — wajib 100% Pass, TP 1 sekalipun tidak diizinkan lolos.

**Dua penilai, satu keputusan:** tiap sampel dinilai 2 kali — oleh tim **KimFis** (3 analis, hasil digabung jadi 1 lewat suara terbanyak) dan oleh **Verifikator** (yang mengambil sampel ulang dan jadi acuan akhir/ground truth). Dashboard ini fokus ke seberapa sering dua penilaian itu beda (disebut "gap") dan pola di baliknya.

---

##  Arsitektur ETL Pipeline

```
📂 Excel Bulanan (raw data)
        │
        ▼
┌───────────────────┐
│   load_data.py    │  Extract + Transform
│                   │  • Baca semua .xlsx dari subfolder
│  ┌─────────────┐  │  • Standardisasi kolom & status
│  │   Extract   │  │  • Infer arah TP (kurang/lebih dari remark)
│  │  Transform  │  │  • Majority vote 3 analis → konsensus KimFis
│  │    Load     │  │  • Merge data Verifikator
│  └─────────────┘  │  • Klasifikasi Gap (Beda Tingkatan/Gap Signifikan/Arah/TP3)
└────────┬──────────┘
         │
         ├──────────────────────────────────────┐
         ▼                                      ▼
┌─────────────────┐                   ┌──────────────────┐
│  cache/*.parquet│                   │  qc_sensory.db   │
│  (dashboard)    │                   │  (SQLite)        │
└────────┬────────┘                   └──────────────────┘
         │
         ▼
┌─────────────────┐
│    app.py       │  Streamlit Dashboard
│  5 Tab Layout   │
└─────────────────┘
```

---

##  5 Pertanyaan Bisnis & Struktur Tab

Dashboard dirancang sebagai drill-down dari big picture ke action level:

```
Tab 1: Apa yang terjadi?       → KPI, distribusi kualitas, gap rate
Tab 2: Di mana & tipe apa?    → Klasifikasi gap, trend, produk & shift
Tab 3: Parameter & produk?    → Root cause parameter, kualitas per produk
Tab 4: Siapa & kapan?         → Performa analis, bias sistematis, shift
Tab 5: Action per batch?      → Detail harian, export data, keputusan release
```

---

##  Fitur Dashboard (5 Tab)

### Tab 1 — 📊 Overview
- Executive Summary 2 box: distribusi kualitas (dari Verif, ground truth) + gap KimFis vs Verif
- KPI baseline selalu tampil: **0 complaint** · **100% approval preshipment**
- KPI Cards: Total sampel · Terverifikasi · Match · Gap
- Top 10 produk (3 mode: TP Rate / Jumlah Absolut / Composite Score)
- Trend MoM — hanya tampil kalau filter = 1 bulan
- Drill-down per produk: distribusi status + parameter penyebab TP

### Tab 2 — 📈 Gap Analysis
- Distribusi tipe gap: Beda Tingkatan / Gap Signifikan / Beda Arah / Melibatkan TP 3
- Interpretasi otomatis dari kategori dominan
- Heatmap KimFis × Verifikator (warna = jarak gap)
- Trend gap **rate %** bulanan (bukan volume) + metric bulan terburuk/terbaik
- Breakdown per produk (composite stacked) + per shift (summary)
- **Apakah CORAK gap beda per shift?** — chi-square test of independence (bukan cuma rate-nya yang dicek, tapi pola jenis gap-nya) dengan fallback otomatis ke kategori yang lebih sederhana kalau data per kategori terlalu tipis untuk diuji valid
- 🚨 Gap Berbahaya: melibatkan TP 3, melibatkan TP 2, atau Beda Arah TP 1

### Tab 3 — 🔬 Parameter & Kualitas Produk
**Subtab A — Gap per Parameter (untuk QC):**
- Gap rate % per parameter: Creamy dominan (27.6%)
- TP rate % per parameter: Creamy tertinggi (36.6%)
- Interpretasi otomatis: "Creamy adalah parameter paling kritis"
- Detail per parameter: distribusi status + trend TP rate + top gap type
- Trend sparse otomatis disembunyikan (threshold TP rate < 0.5%)

**Subtab B — Kualitas per Produk (untuk R&D & Produksi):**
- Top 10 produk (3 mode: TP Rate / Jumlah Absolut / Composite)
- Pass Rate terendah — produk prioritas evaluasi
- Drill-down per produk: insight otomatis (deteksi all-TP1) + distribusi status Verif + trend Pass Rate + tabel parameter penyebab TP dari Verifikator dengan arah dominan
- Rekomendasi otomatis diframe sebagai "layak diserahkan ke Produksi/R&D" — bukan diagnosis akar penyebab produksi, sesuai disiplin scope QC

### Tab 4 — 🏭 Shift & Performa Analis
- Gap rate per shift (1 chart bersih, merah = tertinggi) — lensa PROSES
- **Pass Rate per shift (by Verifikator)** — lensa OUTCOME, ditaruh bersebelahan dengan gap rate biar beda maknanya kelihatan jelas (gap tinggi ≠ kualitas jelek)
- Performa analis: mismatch rate, gradient warna, min 20 sampel
- **Pass Rate per analis (by Verifikator)** — sama, lensa outcome di samping lensa proses
- Kecenderungan bias: Match / Terlalu Longgar / Terlalu Ketat
  - Terlalu Longgar = analis nilai lebih baik dari Verif → ⚠️ lebih berisiko
  - Insight otomatis: individu terbaik/terburuk + pola dominan seluruh tim
- Alert TP 3 gap di heatmap drill-down per analis
- **Semua perbandingan lintas-grup (shift, analis) pakai omnibus test dulu** sebelum drill-down ke pasangan spesifik — lihat bagian Metodologi Statistik di bawah

## Metodologi Statistik

Setiap insight yang membandingkan banyak kelompok (shift, analis) melewati 2 tahap, bukan langsung nyari pasangan paling ekstrem lalu diuji:

1. **Omnibus test (chi-square)** — cek dulu apakah ADA beda di antara SEMUA kelompok sekaligus. Kalau tidak signifikan, berhenti di sini — tidak lanjut ke drill-down.
2. **Drill-down dengan koreksi Bonferroni** — kalau omnibus signifikan, baru boleh cari pasangan paling ekstrem, diuji pakai threshold yang sudah dikoreksi (`0.05 / jumlah pasangan`), bukan 0.05 polos.

Ini mencegah *multiple comparison problem* — nyari pasangan paling ekstrem dari banyak kelompok dulu, baru diuji, secara sistematis melebih-lebihkan seberapa "signifikan" temuannya kelihatan. Implementasi chi-square (termasuk konversi ke p-value pakai regularized incomplete gamma function) ditulis manual di `insight_engine.py`, tanpa dependency `scipy`, konsisten dengan pendekatan z-test yang sudah ada.

**Prinsip bahasa:** p-value, z-score, chi-square, dan istilah statistik lain dihitung penuh di balik layar, tapi tidak pernah ditampilkan mentah ke pengguna dashboard — semua diterjemahkan ke bahasa biasa ("cukup konsisten, bukan sekadar variasi harian biasa" / "masih tergolong wajar").


### Tab 5 — 📋 Daily Report

### Tab 6 — 📌 Case Study
- Satu produk (default LAUTAN KRIMER LK 32 AB), ditelusuri end-to-end: Latar Belakang → Temuan Data → Root Cause → Rekomendasi → Dampak yang Diharapkan
- Selectbox untuk ganti produk case study (minimal 20 sampel terverifikasi)
- Dipakai sebagai showcase utuh untuk submission Kaizen / portofolio
- Shortcut "📅 Verifikasi Terbaru" — filter otomatis ke tanggal verifikasi terbaru
- KPI mini: Pass · TP 1 · TP 2 · TP 3 + warning otomatis kalau ada Not Pass
  (TP 2 = blok sementara tunggu Triangle Test · TP 3 = blok segera)
- Chart scatter KimFis (garis) vs Verifikator (segitiga) per batch/mix
  - `!` = TP 2±/TP 3 terdeteksi | `!!` = gap terlalu jauh
  - Segitiga bolong kalau status match (KimFis tetap terlihat)
- Tabel data bersih: filter by batch, semua kolom, Title Case
- Download CSV + Excel untuk database

---

##  Schema Database (SQLite)

Unit data terkecil: **kombinasi Batch No + Mix/IBC** → Primary Key `(no_batch, mix_ibc)`.

```
┌─────────────────────────────────────────────────────────┐
│                     sensory_clean                        │
│─────────────────────────────────────────────────────────│
│  no_batch      TEXT  ┐  PRIMARY KEY                      │
│  mix_ibc       TEXT  ┘  contoh: "26010116AE" + "A"      │
│  tgl_analisa   TEXT    produk_grade  TEXT                │
│  shift         TEXT    plant         TEXT                │
│─────────────────────────────────────────────────────────│
│  a1_nama/status · a2_nama/status · a3_nama/status        │
│  status_kimfis TEXT  -- konsensus majority vote          │
│  remark_analis TEXT                                      │
│─────────────────────────────────────────────────────────│
│  tgl_verifikasi TEXT   verifikator  TEXT                 │
│  status_verif   TEXT   remark_verif TEXT                 │
│─────────────────────────────────────────────────────────│
│  comparison    TEXT  -- MATCH / MISMATCH / NO_VERIF      │
│  gap_type      TEXT  -- contoh: "Pass → TP 1-"           │
│  source_file   TEXT                                      │
└─────────────────────────────────────────────────────────┘
```

Dirancang untuk dikoneksikan dengan tabel lain via `(no_batch, mix_ibc)`:
```
sensory_clean  ──┐
kimfis_clean   ──┼──► JOIN → QC Database terintegrasi
mikro_clean    ──┤
incoming_clean ──┘
```

---

##  Struktur Folder

```
dashboard_sensory/
│
├── dashboard/
│   ├── app.py                  # Streamlit entry point
│   ├── load_data.py            # ETL pipeline → DataFrame
│   └── tabs/
│       ├── tab1_overview.py    # Executive Summary & KPI
│       ├── tab2_gap.py         # Gap Analysis
│       ├── tab3_parameter.py   # Parameter & Kualitas Produk
│       ├── tab4_shift_analyst.py  # Shift & Performa Analis
│       └── tab5_daily_report.py   # Daily Report & Export
│
├── database/
│   ├── etl_to_sqlite.py        # ETL → SQLite
│   └── verify_db.py            # Quality check database
│
├── tests/
│   └── test_load_data.py       # 30 unit tests
│
├── config.py                   # Konstanta & business rules
├── raw_data/
│   └── sensory_bulanan/        # Letakkan file Excel di sini
├── cache/                      # Auto-generated (parquet)
├── docs/screenshots/
├── requirements.txt
└── README.md
```

---

##  Cara Menjalankan

```bash
# 1. Clone
git clone https://github.com/marioevanri/dashboard_sensory.git
cd dashboard_sensory

# 2. Install dependencies
pip install -r requirements.txt

# 3. Siapkan data Excel di:
#    raw_data/sensory_bulanan/

# 4. Jalankan dashboard
streamlit run dashboard/app.py

# 5. (Opsional) Generate SQLite database
python database/etl_to_sqlite.py
python database/verify_db.py

# 6. Jalankan unit tests
pytest tests/
```

**Refresh data** jika ada file Excel baru: klik **🔄 Refresh Data** di sidebar.

---

##  Tech Stack

| Komponen | Teknologi |
|---|---|
| Dashboard | Streamlit |
| Visualisasi | Plotly |
| Data Processing | Pandas |
| Database | SQLite |
| Cache | Apache Parquet |
| Format Data Sumber | Microsoft Excel (.xlsx) |
| Testing | pytest (30 tests) |

---

##  Business Rules

| Rule | Keterangan |
|---|---|
| Ground Truth | Verif_Status — selalu lebih diprioritaskan dari KimFis |
| Konsensus KimFis | Majority vote dari 3 analis per Mix/IBC |
| Status Hierarchy | TP 2- → TP 1- → Pass → TP 1+ → TP 2+ → TP 3 |
| Release Rules | TP 1 = release dengan catatan · TP 2 = blok sementara, tunggu Triangle Test · TP 3 = Blok |
| Preshipment | Wajib 100% Pass — TP 1 tidak diizinkan |
| Infer arah TP | Remark "kurang" → TP 1-/TP 2- · "lebih" → TP 1+/TP 2+ |
| Gap Klasifikasi | Beda Tingkatan / Gap Signifikan / Beda Arah / Melibatkan TP 3 |
| Gap Berbahaya | Melibatkan TP 2, melibatkan TP 3, atau Beda Arah TP 1 |
| Plant Detection | Suffix batch: AA=Plant 1 · AC/AE=Plant 2 · AB/BB=Blending |
| Satuan | Mix/IBC (bukan "batch") |
| Minimum Sample | Analis min 20 sampel · Produk min 10 sampel |

---

## Author

**Mario Evanri** — QC Verificator Sensory  
Industri manufaktur produk krimer & susu · PT Lautan Natural Krimerindo

[![GitHub](https://img.shields.io/badge/GitHub-marioevanri-181717?style=flat&logo=github)](https://github.com/marioevanri)

---

## Lisensi

Project ini dibuat untuk keperluan internal QC dan portofolio pribadi.  
Data sensory tidak disertakan dalam repository ini.