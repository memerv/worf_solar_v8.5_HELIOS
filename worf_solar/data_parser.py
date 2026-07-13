"""
โมดูลอ่านและแปลงข้อมูลจาก Excel ของแต่ละแบรนด์ ให้อยู่ในรูปแบบมาตรฐานเดียวกัน
(Abstraction Layer — เพิ่มแบรนด์ใหม่ได้โดยแก้แค่ COLUMN_ALIASES ไม่ต้องแตะโค้ดส่วนอื่น)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

STANDARD_COLUMNS = ["timestamp", "solar_kw", "load_kw"]

# อักขระซ่อนที่มักหลุดมากับไฟล์ Excel/CSV จริง (zero-width, BOM, non-breaking space)
# แก้ #9: ถ้าไม่ลบออก substring matching จะพลาดเงียบๆ -> คอลัมน์หายกลายเป็น NaN
_INVISIBLE_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0", "\u2060"]


def _strip_invisible(s: str) -> str:
    for ch in _INVISIBLE_CHARS:
        s = s.replace(ch, "")
    return s


def _read_csv_ragged(file, header=None, nrows=None):
    """อ่าน CSV แบบทนต่อแถวที่จำนวนคอลัมน์ไม่เท่ากัน (เช่นมีแถวคำอธิบายนำหน้า)
    เดิม pd.read_csv จะ error ถ้าแถวข้อมูลมีคอลัมน์มากกว่าแถวแรก
    """
    import io
    import csv as _csv
    if hasattr(file, "read"):
        raw = file.read()
        try:
            file.seek(0)
        except Exception:
            pass
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    else:
        with open(file, "r", encoding="utf-8-sig") as f:
            text = f.read()

    rows = list(_csv.reader(io.StringIO(text)))
    if not rows:
        return pd.DataFrame()
    maxc = max(len(r) for r in rows)
    rows = [r + [""] * (maxc - len(r)) for r in rows]
    df = pd.DataFrame(rows)
    if header is None:
        return df.iloc[:nrows] if nrows is not None else df
    hdr = df.iloc[header].tolist()
    body = df.iloc[header + 1:].reset_index(drop=True)
    body.columns = hdr
    return body


def _read_tabular(file, header="infer", nrows=None, sheet_name=0):
    """อ่านไฟล์ตาราง รองรับ .xlsx / .xls / .csv (แก้ #18)
    คืน DataFrame — เลือก engine ตามนามสกุลไฟล์อัตโนมัติ
    """
    name = getattr(file, "name", str(file)).lower()
    if name.endswith(".csv"):
        h = None if header in (None, "infer") else header
        return _read_csv_ragged(file, header=h, nrows=nrows)
    engine = "xlrd" if name.endswith(".xls") else "openpyxl"
    return pd.read_excel(file, header=header, nrows=nrows,
                         sheet_name=sheet_name, engine=engine)


def _excel_file(file):
    """คืน ExcelFile (xlsx/xls) หรือ None ถ้าเป็น csv (csv ไม่มีหลาย sheet)"""
    name = getattr(file, "name", str(file)).lower()
    if name.endswith(".csv"):
        return None
    engine = "xlrd" if name.endswith(".xls") else "openpyxl"
    return pd.ExcelFile(file, engine=engine)

# ชื่อคอลัมน์ที่พบได้บ่อยในไฟล์ export ของแต่ละแบรนด์ -> ชื่อมาตรฐาน
# ถ้าเจอไฟล์แบรนด์ใหม่ หรือชื่อคอลัมน์ไม่ตรง ให้เพิ่ม/แก้ mapping ตรงนี้เท่านั้น
COLUMN_ALIASES = {
    "huawei": {
        "Time": "timestamp", "time": "timestamp", "Date": "timestamp",
        "PV Power(kW)": "solar_kw", "pv power(kw)": "solar_kw", "Solar Power": "solar_kw",
        "Load Power(kW)": "load_kw", "load power(kw)": "load_kw", "Load": "load_kw",
    },
    "deye": {
        "Time": "timestamp", "DateTime": "timestamp",
        "PV Power": "solar_kw", "PV(W)": "solar_kw",
        "Load Power": "load_kw", "Load(W)": "load_kw",
    },
    "generic": {
        "timestamp": "timestamp", "solar_kw": "solar_kw", "load_kw": "load_kw",
    },
}


def parse_excel(file, brand: str = "generic") -> pd.DataFrame:
    """
    อ่านไฟล์ Excel 1 ไฟล์ แล้วคืนค่าเป็น DataFrame มาตรฐาน
    คอลัมน์ที่ได้เสมอ: timestamp (datetime), solar_kw (float), load_kw (float)
    """
    df = pd.read_excel(file, engine="openpyxl")

    aliases = COLUMN_ALIASES.get(brand.lower(), COLUMN_ALIASES["generic"])
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns})

    missing = [c for c in STANDARD_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"ไม่พบคอลัมน์ {missing} ในไฟล์ที่อัปโหลด (แบรนด์ = '{brand}')\n"
            f"คอลัมน์ที่เจอในไฟล์จริง: {list(df.columns)}\n"
            f"กรุณาเพิ่ม mapping ให้ตรงใน COLUMN_ALIASES (ไฟล์ data_parser.py)"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[STANDARD_COLUMNS].sort_values("timestamp").reset_index(drop=True)

    # data cleaning ขั้นต่ำ: กันค่าติดลบผิดปกติ และแถวที่ข้อมูลหาย
    df["solar_kw"] = df["solar_kw"].clip(lower=0)
    df["load_kw"] = df["load_kw"].clip(lower=0)
    df = df.dropna(subset=STANDARD_COLUMNS)

    return df


# ---------------------------------------------------------------------------
# Parser สำหรับไฟล์ export จากระบบ monitor (เช่น Deye Cloud / Solarman)
# คอลัมน์ตัวอย่าง: Time, Yield(kWh), Earning(THB), Full Load Hours(h),
#   Charged(kWh), Discharged(kWh), Exported(kWh), Imported(kWh),
#   Net Import(kWh), Grid Load(kWh), Backup Load(kWh), GEN(kWh),
#   Smart Load(kWh), AC Coupled(kWh)
# ---------------------------------------------------------------------------

def _norm_col(name: str) -> str:
    """normalize ชื่อคอลัมน์: ตัดอักขระซ่อน/ช่องว่าง/ขึ้นบรรทัด/วงเล็บหน่วย -> ตัวพิมพ์เล็ก"""
    s = _strip_invisible(str(name)).strip().lower()
    for ch in ["\n", "\r", "\t"]:
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    return s


# key = ชื่อมาตรฐานภายใน, value = คำที่ใช้ค้นหาในชื่อคอลัมน์ (หลัง normalize)
_MONITOR_FIELDS = {
    "timestamp":   ["time", "date"],
    "yield_kwh":   ["yield"],
    "charged":     ["charged"],
    "discharged":  ["discharged"],
    "exported":    ["exported"],
    "imported":    ["imported"],
    "grid_load":   ["grid load"],
    "backup_load": ["backup load"],
    "smart_load":  ["smart load"],
    "gen":         ["gen("],       # GEN(kWh) — กันชนกับคำอื่น
    "ac_coupled":  ["ac coupled"],
}

# สัดส่วนกระจายพลังงานรายวัน -> รายชั่วโมง (ผลรวม = 1)
# solar: ระฆังคว่ำช่วง 06:00-18:00 / load: โปรไฟล์บ้านทั่วไป เช้า+หัวค่ำพีค
_SOLAR_SHAPE = [0, 0, 0, 0, 0, 0, .01, .04, .08, .11, .13, .14,
                .14, .13, .10, .07, .04, .01, 0, 0, 0, 0, 0, 0]
_LOAD_SHAPE = [.028, .025, .024, .024, .026, .032, .045, .055, .052, .045, .042, .043,
               .044, .042, .040, .042, .048, .058, .068, .072, .068, .058, .046, .033]
# normalize ให้ผลรวม = 1 เสมอ (พลังงานรายวันหลังกระจายต้องเท่ากับค่าจริงเป๊ะ)
_SOLAR_SHAPE = [w / sum(_SOLAR_SHAPE) for w in _SOLAR_SHAPE]
_LOAD_SHAPE = [w / sum(_LOAD_SHAPE) for w in _LOAD_SHAPE]


def parse_monitor_export(file) -> pd.DataFrame:
    """
    อ่านไฟล์ export จาก monitor แล้วคืน DataFrame มาตรฐาน (timestamp, solar_kw, load_kw)

    หลักการ:
    - solar (kWh ต่อแถว) = Yield
    - load  (kWh ต่อแถว) = Grid Load + Backup Load + Smart Load (คอลัมน์ที่มี)
      ถ้าไม่มีคอลัมน์ load เลย -> คำนวณจากสมดุลพลังงาน:
      load = Yield + Discharged + Imported + GEN + AC Coupled - Charged - Exported
    - ถ้าข้อมูลเป็นรายวัน (1 แถว/วัน ซึ่งเป็นรูปแบบปกติของรายงาน monitor)
      จะกระจายเป็นรายชั่วโมงด้วยโปรไฟล์มาตรฐาน (approximation ไม่ใช่ค่าจริงราย ชม.)
    """
    df = pd.read_excel(file, engine="openpyxl")

    # จับคู่คอลัมน์จริง -> ชื่อมาตรฐาน
    colmap = {}
    for std_name, keywords in _MONITOR_FIELDS.items():
        for c in df.columns:
            nc = _norm_col(c)
            if any(kw in nc for kw in keywords) and std_name not in colmap:
                colmap[std_name] = c
                break

    if "timestamp" not in colmap or "yield_kwh" not in colmap:
        raise ValueError(
            "ไม่พบคอลัมน์ Time หรือ Yield ในไฟล์ monitor\n"
            f"คอลัมน์ที่เจอในไฟล์: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(df[colmap["timestamp"]])

    def col(name):
        return pd.to_numeric(df[colmap[name]], errors="coerce").fillna(0.0) \
            if name in colmap else pd.Series(0.0, index=df.index)

    out["solar_kwh"] = col("yield_kwh").clip(lower=0)

    load_cols = [c for c in ("grid_load", "backup_load", "smart_load") if c in colmap]
    if load_cols:
        out["load_kwh"] = sum(col(c) for c in load_cols).clip(lower=0)
    else:
        balance = (col("yield_kwh") + col("discharged") + col("imported")
                   + col("gen") + col("ac_coupled") - col("charged") - col("exported"))
        out["load_kwh"] = balance.clip(lower=0)

    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # เช็คว่าเป็นข้อมูลรายวันหรือรายช่วงสั้น
    if len(out) >= 2:
        step_hours = (out["timestamp"].iloc[1] - out["timestamp"].iloc[0]).total_seconds() / 3600
    else:
        step_hours = 24.0

    if step_hours >= 20:  # รายวัน -> กระจายเป็นรายชั่วโมง
        rows = []
        for _, r in out.iterrows():
            day_start = r["timestamp"].normalize()
            for h in range(24):
                rows.append({
                    "timestamp": day_start + pd.Timedelta(hours=h),
                    "solar_kw": r["solar_kwh"] * _SOLAR_SHAPE[h],   # kWh ใน 1 ชม. = kW เฉลี่ย
                    "load_kw": r["load_kwh"] * _LOAD_SHAPE[h],
                })
        result = pd.DataFrame(rows)
        result.attrs["disaggregated"] = True
        return result

    # รายช่วงสั้น: แปลง kWh ต่อช่วง -> kW เฉลี่ยของช่วง
    out["solar_kw"] = out["solar_kwh"] / step_hours
    out["load_kw"] = out["load_kwh"] / step_hours
    result = out[["timestamp", "solar_kw", "load_kw"]].copy()
    result.attrs["disaggregated"] = False
    return result


# ---------------------------------------------------------------------------
# Parser สำหรับไฟล์บิล/พฤติกรรมลูกค้า (เทมเพลตไทย)
# header อยู่ที่แถวใดแถวหนึ่งในไฟล์ (ไม่จำเป็นต้องแถวแรก) หาโดยมองหาคอลัมน์คีย์
# รองรับ 2 กรณี:
#   A) รายช่วงเวลา (15 นาที/รายชั่วโมง) -> มีคอลัมน์ "โหลดเฉลี่ยช่วงนี้ (kW)"
#   B) รายเดือน (บิลอย่างเดียว) -> มีแค่ "หน่วยไฟที่ใช้ (kWh)" + "ค่าไฟช่วงนี้ (บาท)"
# ---------------------------------------------------------------------------

import re as _re

# จับปี 4 หลักที่ขึ้นต้นด้วย 25 หรือ 26 (พ.ศ. 2500-2699) ในสตริงวันที่
_BE_YEAR_RE = _re.compile(r"(?<!\d)(2[56]\d{2})(?!\d)")


def _shift_be_year_in_str(s: str) -> str:
    """ลบ 543 จากปี พ.ศ. ในสตริง (ก่อนส่งให้ pandas แปลง)
    ต้องทำ 'ก่อน' pd.to_datetime เพราะ pandas 2.x รองรับปีได้ถึง 2262 เท่านั้น
    ถ้าปล่อยให้ pandas เจอปี 2568 ตรงๆ จะกลายเป็น NaT ทั้งคอลัมน์ (ต้นเหตุบั๊ก)
    """
    def _sub(m):
        return str(int(m.group(1)) - 543)
    return _BE_YEAR_RE.sub(_sub, s)


def _to_ce_datetime(ts) -> pd.Series:
    """แปลงวันที่ (สตริง พ.ศ. หรือ ค.ศ.) -> datetime อย่างทนทานทุกเวอร์ชัน pandas

    ลำดับสำคัญ: แปลงปี พ.ศ.->ค.ศ. 'ในระดับสตริงก่อน' แล้วค่อย pd.to_datetime
    (เดิมแปลงหลัง to_datetime ทำให้ pandas 2.x เจอปี 2568 > ขอบเขต Timestamp (2262)
     แล้วคืน NaT ทั้งคอลัมน์ — ข้อมูลรายช่วงถูกตัดทิ้งหมด กราฟ/kWh/ค่าไฟเลยว่าง)
    dayfirst=True: เทมเพลตไทยเขียนวันก่อนเดือน (17/01/2568)
    """
    s = pd.Series(ts).astype(str).map(_shift_be_year_in_str)
    out = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # เผื่อกรณีที่เป็น datetime อยู่แล้ว (ปี พ.ศ. ที่ pandas ใหม่ๆ ยอมรับ) แล้วยังเกิน 2400
    if getattr(out, "notna", None) is not None and out.notna().any():
        try:
            be = out.dt.year > 2400
            if be.any():
                out = out.where(~be, out - pd.DateOffset(years=543))
        except Exception:
            pass
    return out


def _find_header_row(raw: pd.DataFrame, max_scan: int = 15) -> int:
    """หาแถวที่เป็น header จริง โดยมองหาแถวที่มีคำคีย์หลายคำ"""
    for i in range(min(max_scan, len(raw))):
        row_text = " ".join(str(v) for v in raw.iloc[i].tolist())
        hits = sum(1 for kw in ["ประเภทข้อมูล", "หน่วยไฟ", "ค่าไฟ", "โหลด", "เวลา"]
                   if kw in row_text)
        if hits >= 3:
            return i
    return 0


def parse_customer_bill(file) -> dict:
    """
    อ่านไฟล์บิล/พฤติกรรมลูกค้า (เทมเพลตไทย) รองรับ .xlsx/.xls/.csv คืน dict:
      {"mode": "interval"|"monthly", "data": df|None, "monthly": df|None,
       "meta": {...}, "warnings": [str, ...]}

    warnings: รายการคำเตือนที่ควรโชว์ให้ผู้ใช้เห็น (แก้ #6 — เดิม fallback เงียบๆ)
    """
    warnings: list[str] = []
    xl = _excel_file(file)

    if xl is None:  # ไฟล์ CSV: sheet เดียว
        raw = _read_tabular(file, header=None)
        hrow = _find_header_row(raw)
        df = _read_tabular(file, header=hrow)
    else:
        # เลือก sheet ที่น่าจะเป็นเทมเพลตข้อมูลจริง (มีคำคีย์มากสุด)
        best_sheet, best_score = xl.sheet_names[0], -1
        for sh in xl.sheet_names:
            probe = pd.read_excel(xl, sheet_name=sh, header=None, nrows=12)
            txt = _strip_invisible(" ".join(str(v) for v in probe.values.flatten()))
            score = sum(kw in txt for kw in
                        ["ประเภทข้อมูล", "หน่วยไฟ", "โหลดเฉลี่ย", "ค่าไฟช่วง", "เวลาเริ่ม"])
            if score > best_score:
                best_sheet, best_score = sh, score

        raw = pd.read_excel(xl, sheet_name=best_sheet, header=None)
        hrow = _find_header_row(raw)
        df = pd.read_excel(xl, sheet_name=best_sheet, header=hrow)

    # normalize header: ตัดอักขระซ่อน + ขึ้นบรรทัด + ช่องว่างซ้ำ (แก้ #9)
    df.columns = [" ".join(_strip_invisible(str(c)).replace("\n", " ").split())
                  for c in df.columns]

    def find_col(*keywords):
        for c in df.columns:
            if all(kw in c for kw in keywords):
                return c
        return None

    col_rowtype = find_col("ประเภทข้อมูล")
    col_date = find_col("วันที่") or find_col("เดือน")
    col_time = find_col("เวลาเริ่ม") or find_col("เวลา")
    col_load = find_col("โหลด")
    col_kwh = find_col("หน่วยไฟ")
    col_cost = find_col("ค่าไฟ")
    col_biz = find_col("ประเภทธุรกิจ")
    col_meter = find_col("ประเภทมิเตอร์")
    col_demand = find_col("Demand") or find_col("demand")

    def clean_num(series):
        return pd.to_numeric(
            series.astype(str).str.replace(",", "", regex=False)
            .replace({"-": None, "": None, "nan": None, "None": None}),
            errors="coerce")

    if col_rowtype:
        mask = df[col_rowtype].astype(str).str.contains("รายช่วง|รายเดือน", na=False)
        work = df[mask].copy()
    else:
        work = df.copy()

    meta = {}
    for key, col in [("business_type", col_biz), ("meter_type", col_meter)]:
        if col and col in work.columns:
            vals = work[col].dropna().astype(str)
            vals = vals[~vals.isin(["-", "nan", "None"])]
            meta[key] = vals.iloc[0] if len(vals) else None

    is_interval = False
    if col_rowtype:
        is_interval = work[col_rowtype].astype(str).str.contains("รายช่วง", na=False).any()

    if is_interval and col_load:
        iv = work[work[col_rowtype].astype(str).str.contains("รายช่วง", na=False)].copy()
        # แก้ #6: ถ้าหาคอลัมน์วันที่/เวลาไม่เจอ ต้องเตือนผู้ใช้ ไม่ใช่ fallback เงียบๆ
        if not col_date:
            warnings.append("⚠️ หาคอลัมน์ 'วันที่' ไม่เจอ — ใช้วันที่สมมติ (2025-01-01) "
                            "ทุกแถว กราฟตามเวลาและ On/Off-Peak อาจไม่ถูกต้อง")
        if not col_time:
            warnings.append("⚠️ หาคอลัมน์ 'เวลาเริ่มช่วง' ไม่เจอ — ใช้เวลา 00:00 ทุกแถว "
                            "โปรไฟล์รายชั่วโมงจะไม่ถูกต้อง")
        date_str = iv[col_date].astype(str) if col_date else "2025-01-01"
        time_str = iv[col_time].astype(str) if col_time else "00:00"
        ts = _to_ce_datetime(date_str + " " + time_str)
        if ts.isna().any():
            n_bad = int(ts.isna().sum())
            warnings.append(f"⚠️ มี {n_bad:,} แถวที่แปลงวันที่/เวลาไม่สำเร็จ ถูกตัดออกจากการคำนวณ")
        out = pd.DataFrame({
            "timestamp": ts,
            "solar_kw": 0.0,
            "load_kw": clean_num(iv[col_load]),
        }).dropna(subset=["timestamp", "load_kw"]).sort_values("timestamp").reset_index(drop=True)
        return {"mode": "interval", "data": out, "monthly": None,
                "meta": meta, "warnings": warnings}

    # โหมดรายเดือน — เตือนถ้าหาคอลัมน์สำคัญไม่เจอ (แก้ #6)
    if not col_kwh:
        warnings.append("⚠️ หาคอลัมน์ 'หน่วยไฟที่ใช้ (kWh)' ไม่เจอ — ค่าหน่วยไฟจะว่าง")
    if not col_cost:
        warnings.append("⚠️ หาคอลัมน์ 'ค่าไฟช่วงนี้ (บาท)' ไม่เจอ — ค่าไฟจะแสดงเป็น 'ไม่ระบุ'")

    mo = work.copy()
    if col_rowtype:
        mo = work[work[col_rowtype].astype(str).str.contains("รายเดือน", na=False)].copy()
    monthly = pd.DataFrame({
        "month": mo[col_date].astype(str) if col_date else range(len(mo)),
        "kwh": clean_num(mo[col_kwh]) if col_kwh else pd.Series(dtype=float),
        "cost": clean_num(mo[col_cost]) if col_cost else pd.Series(dtype=float),
        # ค่า Demand จากบิล (ถ้ามี) — ใช้ประกอบการประเมิน แต่ไม่บังคับ
        "demand_kw": clean_num(mo[col_demand]) if col_demand else pd.Series(dtype=float),
    }).reset_index(drop=True)
    monthly = monthly[monthly["kwh"].notna() | monthly["cost"].notna()].reset_index(drop=True)
    return {"mode": "monthly", "data": None, "monthly": monthly,
            "meta": meta, "warnings": warnings}


def generate_sample_data(days: int = 3, seed: int = 42) -> pd.DataFrame:
    """สร้างข้อมูลจำลอง สำหรับทดลองใช้งานตอนยังไม่มีไฟล์จริง หรือไฟล์ยังไม่พร้อม"""
    rng = np.random.default_rng(seed)
    rows = []
    start = datetime(2026, 1, 1, 0, 0)

    for d in range(days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            solar = max(0.0, 5 * np.sin(np.pi * (h - 6) / 12)) if 6 <= h <= 18 else 0.0
            solar *= rng.uniform(0.7, 1.0)
            load = 1.5 + 2.0 * np.exp(-((h - 8) ** 2) / 8) + 3.0 * np.exp(-((h - 19) ** 2) / 6)
            load *= rng.uniform(0.9, 1.1)
            rows.append({
                "timestamp": ts,
                "solar_kw": round(float(solar), 2),
                "load_kw": round(float(load), 2),
            })

    return pd.DataFrame(rows)
