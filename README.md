# 🧪 QC Sensory Dashboard

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=flat&logo=sqlite&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-Visualization-3F4F75?style=flat&logo=plotly&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-30%20passed-2E8B57?style=flat&logo=pytest&logoColor=white)
[![GitHub](https://img.shields.io/badge/GitHub-marioevanri-181717?style=flat&logo=github)](https://github.com/marioevanri)

Dashboard interaktif untuk analisis data evaluasi sensory produk krimer & susu di lingkungan manufaktur. Dibangun dengan konsep **ETL Pipeline → SQLite Database → Streamlit Dashboard**.

---

## 📌 Latar Belakang

Di industri manufaktur produk susu dan krimer, setiap batch produksi dievaluasi secara sensory oleh **3 analis KimFis** yang kemudian hasilnya diverifikasi oleh **Verificator**. Proses ini menghasilkan data yang perlu dimonitor secara sistematis untuk:

- Memastikan konsistensi kualitas produk antar batch dan shift
- Mendeteksi gap (perbedaan) antara penilaian KimFis dan Verificator
- Menganalisis performa tiap analis terhadap ground truth Verificator
- Menghasilkan laporan harian yang siap digunakan sebagai referensi keputusan produksi

---

## 🔄 Arsitektur ETL Pipeline

```
📂 Excel Bulanan (raw data)
        │
        ▼
┌───────────────────┐
│   load_data.py    │  Extract + Transform
│                   │  • Baca semua .xlsx dari subfolder
│  ┌─────────────┐  │  • Standardisasi kolom & status
│  │   Extract   │  │  • Infer arah TP (kurang/lebih)
│  │  Transform  │  │  • Majority vote 3 analis → konsensus
│  │    Load     │  │  • Merge data Verificator
│  └─────────────┘  │  • Hitung Gap Type & Comparison
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

## 🗄️ Schema Database (SQLite)

Unit data terkecil adalah **kombinasi Batch No + Mix/IBC** — contoh: batch `26010116AE` mix `A` → Primary Key = `(26010116AE, A)`.

Database dirancang **flat dan simple** — 1 tabel utama `sensory_clean` yang siap dikoneksikan dengan tabel dari divisi lain (Kimfis, Mikro, Incoming, Outgoing) via `no_batch + mix_ibc` sebagai foreign key.

```
┌─────────────────────────────────────────────────────────┐
│                     sensory_clean                        │
│─────────────────────────────────────────────────────────│
│  no_batch      TEXT  ┐                                   │
│  mix_ibc       TEXT  ┘ PRIMARY KEY (no_batch, mix_ibc)  │
│                        contoh: "26010116AE" + "A"        │
│─────────────────────────────────────────────────────────│
│  tgl_analisa   TEXT    -- tanggal analisa KimFis         │
│  produk_grade  TEXT    -- nama/grade produk              │
│  shift         TEXT                                      │
│  plant         TEXT    -- Plant 1 / Plant 2 / Blending   │
│─────────────────────────────────────────────────────────│
│  a1_nama       TEXT    -- nama analis 1                  │
│  a1_status     TEXT    -- status analis 1                │
│  a2_nama       TEXT    -- nama analis 2                  │
│  a2_status     TEXT    -- status analis 2                │
│  a3_nama       TEXT    -- nama analis 3                  │
│  a3_status     TEXT    -- status analis 3                │
│  status_kimfis TEXT    -- konsensus majority vote        │
│  remark_analis TEXT                                      │
│─────────────────────────────────────────────────────────│
│  tgl_verifikasi TEXT   -- tanggal verifikasi             │
│  verifikator    TEXT   -- nama verifikator               │
│  status_verif   TEXT   -- hasil verifikator              │
│  remark_verif   TEXT                                     │
│─────────────────────────────────────────────────────────│
│  comparison    TEXT    -- MATCH / MISMATCH / NO_VERIF    │
│  gap           TEXT    -- contoh: "Pass → TP 1-"         │
│  source_file   TEXT    -- nama file Excel sumber         │
└─────────────────────────────────────────────────────────┘
```

**Koneksi ke divisi lain (rencana ke depan):**

```
sensory_clean  ──┐
kimfis_clean   ──┼──► JOIN via (no_batch + mix_ibc)
mikro_clean    ──┤        → QC Database terintegrasi
incoming_clean ──┤
outgoing_clean ──┘
```

**Views yang tersedia:**
- `v_sensory_full` — JOIN semua tabel, siap query
- `v_mismatch_summary` — hanya data MISMATCH
- `v_daily_report` — format laporan harian

---

## 📊 Fitur Dashboard (5 Tab)

### Tab 1 — Overview
- KPI cards: Total sampel, coverage verifikasi, match/mismatch rate
- Distribusi status KimFis vs Verificator
- Top 10 produk dengan mismatch tertinggi

### Tab 2 — Gap Analysis
- Top gap type (Pass→TP 1-, TP 1-→Pass, dll)
- Heatmap KimFis × Verificator
- Sankey diagram aliran status
- Trend gap harian/mingguan
- Breakdown gap per produk

### Tab 3 — Parameter
- Pareto gap per parameter sensory (Odor, Coffee Aroma, Creamy, Milky, Mouthfeel, Sweet, Taste Profile)
- Distribusi status per parameter
- Heatmap KF × Verif per parameter
- Trend bulanan

### Tab 4 — Shift & Analis
- Mismatch rate per shift
- Distribusi status per shift dan parameter
- Performa tiap analis vs Verificator
- Kecenderungan pilihan analis (stacked bar 100%)
- Heatmap detail per analis

### Tab 5 — Daily Report
- Chart status KimFis (garis) vs Verificator (segitiga) per batch
- Anotasi `!` untuk TP 2±/TP 3, `!!` untuk gap terlalu jauh
- Ukuran chart otomatis menyesuaikan jumlah Mix/IBC
- Filter per produk, batch, tanggal verifikasi
- Tabel data bersih lengkap + download CSV/Excel

---

## 🗂️ Struktur Folder

```
dashboard_sensory/
│
├── config.py                    # Konstanta bersama (STATUS_ORDER, PARAM_COLS, dll)
│
├── dashboard/
│   ├── app.py                   # Entry point — 165 baris, hanya setup & import
│   ├── load_data.py             # ETL pipeline Excel → DataFrame
│   └── tabs/                    # Modul terpisah per tab
│       ├── __init__.py
│       ├── tab1_overview.py     # Overview & KPI
│       ├── tab2_gap.py          # Gap Analysis + classify_gap()
│       ├── tab3_parameter.py    # Analisis parameter sensory
│       ├── tab4_shift_analyst.py # Shift & performa analis
│       └── tab5_daily_report.py # Daily report chart & tabel
│
├── database/
│   ├── etl_to_sqlite.py         # ETL pipeline → SQLite (jalankan manual)
│   └── verify_db.py             # Quality check database (30 checks)
│
├── tests/
│   ├── __init__.py
│   └── test_load_data.py        # Unit tests (30 test cases, semua passed)
│
├── raw_data/
│   └── sensory_bulanan/         # Letakkan file Excel di sini
│
├── cache/                       # Auto-generated (parquet cache)
├── docs/screenshots/            # Screenshot dashboard
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🚀 Cara Menjalankan

### 1. Clone repository

```bash
git clone https://github.com/username/dashboard_sensory.git
cd dashboard_sensory
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Siapkan data

Letakkan file Excel sensory bulanan di:
```
raw_data/sensory_bulanan/
```

### 4. Jalankan Dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard akan otomatis membaca semua file Excel dan membuild cache.

### 5. Jalankan Unit Tests (opsional)

```bash
pytest tests/
# Expected: 30 passed
```

### 5. Generate Database SQLite (opsional)

```bash
python database/etl_to_sqlite.py
```

File `qc_sensory.db` akan terbuat di folder `database/`. Verifikasi dengan:

```bash
python database/verify_db.py
```

### 6. Refresh data (jika ada file baru)

Klik tombol **🔄 Refresh Data** di sidebar dashboard, atau hapus cache dan restart:

```bash
del cache\data_cache.parquet   # Windows
rm cache/data_cache.parquet    # Mac/Linux
streamlit run dashboard/app.py
```

---

## 🧰 Tech Stack

| Komponen | Teknologi |
|---|---|
| Dashboard | Streamlit |
| Visualisasi | Plotly |
| Data Processing | Pandas |
| Database | SQLite |
| ETL Pipeline | Python (custom) |
| Format Data Sumber | Microsoft Excel (.xlsx) |
| Cache | Apache Parquet |

---

## 📐 Business Rules

| Rule | Keterangan |
|---|---|
| Konsensus KimFis | Majority vote dari 3 analis per Mix/IBC |
| Infer arah TP | Dari remark: "kurang" → TP 1-/TP 2-, "lebih" → TP 1+/TP 2+ |
| Status akhir | Verif_Status lebih diprioritaskan dari KF_Status |
| Comparison | MATCH / MISMATCH / NO_VERIFICATION |
| Plant detection | Suffix batch: AA=Plant 1, AC/AE=Plant 2, AB/BB=Blending |
| Pass threshold | TP 1 = masih Pass (release), TP 2/TP 3 = Not Pass |
| Gap jauh | Beda >1 level skala ordinal ATAU beda arah (+/-) |

---

## 👤 Author

**Mario Evanri** — QC Verificator Sensory  
Industri manufaktur produk krimer & susu

[![GitHub](https://img.shields.io/badge/GitHub-marioevanri-181717?style=flat&logo=github)](https://github.com/marioevanri)

---

## 📄 Lisensi

Project ini dibuat untuk keperluan internal QC dan portofolio pribadi.  
Data sensory tidak disertakan dalam repository ini.
