"""
load_data.py
============
Load dan clean data sensory dari file Excel bulanan.

Business rules:
- Baca sheet "Sensory", header=2
- 3 analyst per mix/IBC → majority vote → 1 baris konsensus (KF_Status)
- Remark hanya di baris analyst 1 → propagate ke analyst 2-3
- Verificator: ada 1-2 baris per mix/IBC → ambil baris pertama
- Infer arah status (TP 1- / TP 1+) dari remark
- Final decision = Verif_Status (lebih diutamakan dari KF_Status)
- Comparison: MATCH / MISMATCH / NO_VERIFICATION
- Gap_Type: format "KF_Status → Verif_Status" untuk MISMATCH
"""

import re
import pandas as pd
from pathlib import Path


# ── CONFIG ──────────────────────────────────────────────────────
# Path otomatis relatif terhadap lokasi file ini
_HERE      = Path(__file__).parent
RAW_FOLDER = _HERE.parent / "raw_data" / "sensory_bulanan"
CACHE_FILE = _HERE.parent / "cache" / "data_cache.parquet"

PARAM_COLS       = ["Odor","Coffee_Aroma","Creamy","Milky","Mouthfeel","Sweet","Taste_Profile"]
VERIF_PARAM_COLS = [f"V_{p}" for p in PARAM_COLS]
STATUS_ORDER     = ["TP 2-","TP 1-","Pass","TP 1+","TP 2+","TP 3"]
VALID_STATUS     = set(STATUS_ORDER)

RENAME = {
    "Verification Date Shift": "Date",
    "Shift":                   "Shift_Code",
    "No. Lot":                 "Batch_No",
    "Mixing/IBC":              "Mix_Code",
    "Product":                 "Product_Name",
    "No":                      "Analyst_No",
    "Analyst Name":            "Analyst_Name",
    "Odor":           "Odor",
    "Coffee Aroma":   "Coffee_Aroma",
    "Creamy":         "Creamy",
    "Milky":          "Milky",
    "Mouthfeel":      "Mouthfeel",
    "Sweet":          "Sweet",
    "Taste Profile":  "Taste_Profile",
    "Analyst status":     "Analyst_Status",
    "Remark":             "Remark_Analyst",
    "Remark_Analyst":     "Remark_Analyst",
    "Verification Date":  "Verif_Date",
    "Verificator Name":   "Verif_Name",
    "Odor.1":             "V_Odor",
    "Coffee Aroma.1":     "V_Coffee_Aroma",
    "Creamy.1":           "V_Creamy",
    "Milky.1":            "V_Milky",
    "Mouthfeel.1":        "V_Mouthfeel",
    "Sweet.1":            "V_Sweet",
    "Taste Profile.1":    "V_Taste_Profile",
    "Verificator status": "Verif_Status",
    "Unnamed: 32":        "Remark_Verif",
    "Remark_Verificator": "Remark_Verif",
}

REQUIRED_RAW = [
    "Date","Shift_Code","Batch_No","Mix_Code","Product_Name",
    "Analyst_No","Analyst_Name",
    "Odor","Coffee_Aroma","Creamy","Milky","Mouthfeel","Sweet","Taste_Profile",
    "Analyst_Status","Remark_Analyst",
    "Verif_Date","Verif_Name",
    "V_Odor","V_Coffee_Aroma","V_Creamy","V_Milky","V_Mouthfeel","V_Sweet","V_Taste_Profile",
    "Verif_Status","Remark_Verif",
]

SKOR_STATUS_MAP = {
    (0,""):"Pass",(1,"-"):"TP 1-",(1,"+"):"TP 1+",(1,""):"TP 1",
    (2,"-"):"TP 2-",(2,"+"):"TP 2+",(2,""):"TP 2",(3,""):"TP 3",
}

PARAM_KEYWORDS = {
    "Odor":["odor"],"Coffee_Aroma":["coffee aroma","coffee","aroma"],
    "Creamy":["creamy"],"Milky":["milky"],
    "Mouthfeel":["mouthfeel","mouth feel"],
    "Sweet":["sweet"],"Taste_Profile":["taste profile","taste"],
}


# ── HELPERS ─────────────────────────────────────────────────────

def get_plant(batch_no):
    if pd.isna(batch_no): return "Unknown"
    s = str(batch_no).strip().upper()
    if s.endswith("AA"):   return "Plant 1"
    if s.endswith("AC") or s.endswith("AE"): return "Plant 2"
    if s.endswith("AB") or s.endswith("BB"): return "Blending"
    return "Unknown"


def norm_analyst_no(val):
    try:
        return int(float(str(val).strip()))
    except:
        return None


def standardize_status(val):
    if pd.isna(val) or str(val).strip() in ("", "nan", "None", "0"):
        return None
    s = re.sub(r"\s+", " ", str(val).strip().upper())
    mapping = {
        "PASS":"Pass",
        "TP1":"TP 1",  "TP 1":"TP 1",
        "TP2":"TP 2",  "TP 2":"TP 2",
        "TP3":"TP 3",  "TP 3":"TP 3",
        "TP1-":"TP 1-","TP 1-":"TP 1-","TP 1 -":"TP 1-",
        "TP1+":"TP 1+","TP 1+":"TP 1+","TP 1 +":"TP 1+",
        "TP2-":"TP 2-","TP 2-":"TP 2-","TP 2 -":"TP 2-",
        "TP2+":"TP 2+","TP 2+":"TP 2+","TP 2 +":"TP 2+",
        "TP  2-":"TP 2-","TP  1-":"TP 1-",
    }
    return mapping.get(s, s)


def infer_direction(status, remark):
    if pd.isna(status): return status
    s = str(status).strip()
    if s not in ("TP 1", "TP 2"): return s
    if pd.isna(remark) or str(remark).strip() in ("", "nan", "None", "0"):
        return s
    r = re.sub(r"[^\w\s]", "", str(remark).lower().strip())
    if re.search(r"kurang", r): return s + "-"
    if re.search(r"lebih",  r): return s + "+"
    return s


def parse_remark_directions(remark):
    if not remark or str(remark).strip() in ("","nan","None","0"): return {}
    r = str(remark).lower().strip()
    tokens = re.split(r"[\s,]+", r)
    result = {}; current_dir = None; i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "kurang": current_dir = "-"
        elif token == "lebih": current_dir = "+"
        elif token == "agak" and i+1 < len(tokens):
            nxt = tokens[i+1]
            if nxt == "kurang": current_dir = "-"; i += 1
            elif nxt == "lebih": current_dir = "+"; i += 1
        for param, keywords in PARAM_KEYWORDS.items():
            for kw in keywords:
                kw_tokens = kw.split()
                if i+len(kw_tokens) <= len(tokens):
                    phrase = " ".join(tokens[i:i+len(kw_tokens)])
                    if phrase == kw and current_dir and param not in result:
                        result[param] = current_dir; break
        i += 1
    return result


def safe_float(v):
    try: return float(v)
    except: return None


def calc_param_status(skor_raw, arah):
    try: skor = int(round(float(str(skor_raw).replace("+","").replace("-",""))))
    except: return None
    if skor == 0: return "Pass"
    if skor == 3: return "TP 3"
    return SKOR_STATUS_MAP.get((skor, arah), SKOR_STATUS_MAP.get((skor,""), None))


# ── STEP 1: BACA FILE ───────────────────────────────────────────

def read_excel_files(raw_folder=RAW_FOLDER):
    folder = Path(raw_folder)
    files  = sorted(folder.glob("**/*.xlsx"))
    if not files:
        raise ValueError(f"Tidak ada file .xlsx di {folder.resolve()}")

    all_dfs = []
    for f in files:
        try:
            df = pd.read_excel(f, sheet_name="Sensory", header=2, dtype=str)
            df = df.rename(columns=RENAME)
            for col in REQUIRED_RAW:
                if col not in df.columns:
                    df[col] = None
            df = df[REQUIRED_RAW].copy()
            df["Source_File"] = f.name
            df["Source_Year"] = f.parent.name
            df = df[
                df["Batch_No"].notna() &
                (df["Batch_No"].astype(str).str.strip().isin(["", "0", "nan"]) == False) &
                df["Product_Name"].notna() &
                df["Analyst_Name"].notna()
            ]
            all_dfs.append(df)
        except Exception as e:
            print(f"  ⚠ Skip {f.name}: {e}")

    if not all_dfs:
        raise ValueError("Tidak ada data berhasil dibaca")

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"Raw  : {len(combined):,} baris dari {len(files)} file")
    return combined


# ── STEP 2: CLEAN ───────────────────────────────────────────────

def clean_data(df):
    df["Date"]       = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df["Verif_Date"] = pd.to_datetime(df["Verif_Date"], errors="coerce").dt.normalize()
    df["Product_Name"] = df["Product_Name"].astype(str).str.strip().str.upper()
    df["Analyst_Name"] = df["Analyst_Name"].astype(str).str.strip().str.lower()
    df["Verif_Name"]   = df["Verif_Name"].astype(str).str.strip().str.lower()
    df["Batch_No"]   = df["Batch_No"].astype(str).str.strip()
    df["Mix_Code"]   = df["Mix_Code"].astype(str).str.strip()
    df["Shift_Code"] = df["Shift_Code"].astype(str).str.strip()
    df["Analyst_Status"] = df["Analyst_Status"].apply(standardize_status)
    df["Verif_Status"]   = df["Verif_Status"].apply(standardize_status)
    for col in ["Remark_Analyst", "Remark_Verif"]:
        df[col] = df[col].apply(
            lambda x: str(x).strip().capitalize()
            if pd.notna(x) and str(x).strip() not in ("", "nan", "None", "0")
            else None
        )
    df["Analyst_No"] = df["Analyst_No"].apply(norm_analyst_no)
    df["Plant"]      = df["Batch_No"].apply(get_plant)
    df["Sample_ID"]  = df["Batch_No"] + "_" + df["Mix_Code"]
    df = df.sort_values(["Date","Batch_No","Mix_Code","Analyst_No"]).reset_index(drop=True)
    before = len(df)
    df = df.drop_duplicates(
        subset=["Batch_No","Mix_Code","Analyst_No","Analyst_Name"], keep="last"
    )
    print(f"Clean: {len(df):,} baris (drop {before-len(df)} duplikat)")
    return df


# ── STEP 3: INFER ARAH ──────────────────────────────────────────

def apply_direction(df):
    mask_a1 = df["Analyst_No"] == 1
    df.loc[mask_a1, "Analyst_Status"] = df[mask_a1].apply(
        lambda r: infer_direction(r["Analyst_Status"], r["Remark_Analyst"]), axis=1
    )
    a1_dir = (
        df[mask_a1][["Batch_No","Mix_Code","Analyst_Status"]]
        .drop_duplicates(subset=["Batch_No","Mix_Code"])
        .rename(columns={"Analyst_Status":"A1_Status"})
    )
    df = df.merge(a1_dir, on=["Batch_No","Mix_Code"], how="left")
    def copy_dir(row):
        s = str(row["Analyst_Status"] or "").strip()
        if s not in ("TP 1","TP 2") or row["Analyst_No"] == 1:
            return row["Analyst_Status"]
        a1 = str(row["A1_Status"] or "").strip()
        if a1.endswith("-"): return s + "-"
        if a1.endswith("+"): return s + "+"
        return row["Analyst_Status"]
    mask_no_dir = (df["Analyst_No"] != 1) & (df["Analyst_Status"].isin(["TP 1","TP 2"]))
    if mask_no_dir.any():
        df.loc[mask_no_dir, "Analyst_Status"] = df[mask_no_dir].apply(copy_dir, axis=1)
    df = df.drop(columns=["A1_Status"], errors="ignore")
    df["Verif_Status"] = df.apply(
        lambda r: infer_direction(r["Verif_Status"], r["Remark_Verif"]), axis=1
    )
    tp_left_a = df["Analyst_Status"].isin(["TP 1","TP 2"]).sum()
    tp_left_v = df["Verif_Status"].isin(["TP 1","TP 2"]).sum()
    print(f"Dir  : sisa {tp_left_a} analyst + {tp_left_v} verif tanpa arah")
    return df


# ── STEP 4: KONSENSUS ───────────────────────────────────────────

def build_consensus(df):
    results = []
    for (batch, mix), grp in df.groupby(["Batch_No","Mix_Code"], sort=False):
        a1   = grp[grp["Analyst_No"] == 1]
        base = a1.iloc[0] if not a1.empty else grp.iloc[0]
        statuses = grp["Analyst_Status"].dropna().tolist()
        if statuses:
            mode = pd.Series(statuses).mode()
            if len(mode) == 1:
                kf_status = mode[0]
            else:
                tp_vals = [s for s in statuses if s != "Pass"]
                kf_status = tp_vals[0] if tp_vals else statuses[0]
        else:
            kf_status = None

        analyst_vals = {}
        for _, row in grp.sort_values("Analyst_No").iterrows():
            no = row["Analyst_No"]
            if no in (1, 2, 3):
                no = int(no)
                analyst_vals[f"A{no}_Name"]   = row["Analyst_Name"]
                analyst_vals[f"A{no}_Status"] = row["Analyst_Status"]

        param_consensus = {}
        for p in PARAM_COLS:
            if p in grp.columns:
                vals = pd.to_numeric(grp[p], errors="coerce").dropna().tolist()
                param_consensus[f"KF_{p}"] = round(sum(vals)/len(vals), 2) if vals else None

        # Per-parameter status (KF)
        remark_a1  = base.get("Remark_Analyst")
        directions = parse_remark_directions(remark_a1)
        batch_dir  = ""
        if kf_status and kf_status.endswith("-"): batch_dir = "-"
        elif kf_status and kf_status.endswith("+"): batch_dir = "+"
        for p in PARAM_COLS:
            skor_raw = base.get(p)
            if pd.isna(skor_raw) or str(skor_raw).strip() in ("","nan","None"):
                param_consensus[f"KF_{p}_Status"] = None
            else:
                arah = directions.get(p, batch_dir)
                param_consensus[f"KF_{p}_Status"] = calc_param_status(skor_raw, arah)

        results.append({
            "Date":          base["Date"],
            "Batch_No":      batch,
            "Mix_Code":      mix,
            "Sample_ID":     base["Sample_ID"],
            "Product_Name":  base["Product_Name"],
            "Plant":         base["Plant"],
            "Shift_Code":    base["Shift_Code"],
            "KF_Status":     kf_status,
            "Remark_Analyst":base["Remark_Analyst"],
            "Source_File":   base["Source_File"],
            "Source_Year":   base.get("Source_Year"),
            **analyst_vals,
            **param_consensus,
        })

    consensus_df = pd.DataFrame(results)
    print(f"KF   : {len(consensus_df):,} mix/IBC unik")
    return consensus_df


# ── STEP 5: MERGE VERIFIKATOR ────────────────────────────────────

def merge_verifier(df_raw, df_consensus):
    verif_valid = df_raw[df_raw["Verif_Status"].notna()].copy()
    verif_first = (
        verif_valid
        .sort_values(["Batch_No","Mix_Code","Analyst_No"])
        .drop_duplicates(subset=["Batch_No","Mix_Code"], keep="first")
    )
    verif_cols = (
        ["Batch_No","Mix_Code","Verif_Name","Verif_Date","Verif_Status","Remark_Verif"] +
        [c for c in VERIF_PARAM_COLS if c in verif_first.columns]
    )
    verif_first = verif_first[[c for c in verif_cols if c in verif_first.columns]]
    merged = df_consensus.merge(verif_first, on=["Batch_No","Mix_Code"], how="left")

    # Per-parameter status (Verif)
    for p in PARAM_COLS:
        vc = f"V_{p}"
        if vc in merged.columns:
            def _calc_v(row, _p=p, _vc=vc):
                skor_raw = row.get(_vc)
                if pd.isna(skor_raw) or str(skor_raw).strip() in ("","nan","None"):
                    return None
                remark = row.get("Remark_Verif")
                dirs   = parse_remark_directions(remark)
                vbatch = ""
                vs = str(row.get("Verif_Status") or "").strip()
                if vs.endswith("-"): vbatch = "-"
                elif vs.endswith("+"): vbatch = "+"
                arah = dirs.get(_p, vbatch)
                return calc_param_status(skor_raw, arah)
            merged[f"V_{p}_Status"] = merged.apply(_calc_v, axis=1)

    merged["Final_Status"] = merged["Verif_Status"].where(
        merged["Verif_Status"].notna(), merged["KF_Status"]
    )

    def compare(row):
        if pd.isna(row["Verif_Status"]): return "NO_VERIFICATION"
        if row["KF_Status"] == row["Verif_Status"]: return "MATCH"
        return "MISMATCH"

    merged["Comparison"] = merged.apply(compare, axis=1)

    # ── Gap_Type ──────────────────────────────────────────────────
    merged["Gap_Type"] = merged.apply(
        lambda r: f"{r['KF_Status']} → {r['Verif_Status']}"
        if r["Comparison"] == "MISMATCH" else None,
        axis=1
    )

    n_match    = (merged["Comparison"] == "MATCH").sum()
    n_mismatch = (merged["Comparison"] == "MISMATCH").sum()
    n_noverif  = (merged["Comparison"] == "NO_VERIFICATION").sum()
    n_verif    = n_match + n_mismatch
    coverage   = n_verif / len(merged) * 100 if len(merged) else 0
    print(f"Verif: {n_verif:,} terverif | MATCH={n_match} | MISMATCH={n_mismatch} | NO_VERIF={n_noverif}")
    print(f"Coverage: {coverage:.1f}%")
    return merged


# ── MAIN ────────────────────────────────────────────────────────

def load_all(raw_folder=RAW_FOLDER):
    print("\n" + "="*50)
    print("  LOADING DATA")
    print("="*50)
    raw       = read_excel_files(raw_folder)
    cleaned   = clean_data(raw)
    directed  = apply_direction(cleaned)
    consensus = build_consensus(directed)
    final     = merge_verifier(directed, consensus)
    print("="*50)
    print(f"  DONE: {len(final):,} sample siap")
    print("="*50 + "\n")
    return final


# ── CACHE ────────────────────────────────────────────────────────

def load_with_cache(raw_folder=RAW_FOLDER, force_reload=False):
    CACHE_FILE.parent.mkdir(exist_ok=True)

    def cache_stale():
        if not CACHE_FILE.exists(): return True
        cache_t = CACHE_FILE.stat().st_mtime
        excels  = list(Path(raw_folder).glob("**/*.xlsx"))
        return max((f.stat().st_mtime for f in excels), default=0) > cache_t

    if force_reload or cache_stale():
        print("📥 Membaca dari Excel...")
        df = load_all(raw_folder)
        df.to_parquet(CACHE_FILE, index=False)
        print(f"✅ Cache disimpan: {CACHE_FILE}")
    else:
        print("⚡ Membaca dari cache...")
        df = pd.read_parquet(CACHE_FILE)
        print(f"✅ {len(df):,} baris dari cache")
    return df


if __name__ == "__main__":
    df = load_all()
    print(df[["Date","Product_Name","Plant","KF_Status","Verif_Status",
              "Final_Status","Comparison","Gap_Type"]].head(10).to_string())
    print("\nComparison dist:")
    print(df["Comparison"].value_counts())
    print("\nGap_Type top 10:")
    print(df["Gap_Type"].value_counts().head(10))
