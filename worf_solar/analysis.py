"""
โมดูลวิเคราะห์พฤติกรรมการใช้ไฟของลูกค้า (แบบเดียวกับไฟล์วิเคราะห์ของทีม)

รองรับ 2 กรณีด้วยชุดฟังก์ชันเดียวกัน:
  A) ข้อมูลรายช่วง (15 นาที / รายชั่วโมง)  -> วิเคราะห์ได้เต็ม:
     สรุป Day/Night รายเดือน (Average / Max ต่อชั่วโมง) + เส้นแนวโน้ม (linear trend)
  B) บิลรายเดือนอย่างเดียว (PEA/MEA 6-12 เดือน) -> วิเคราะห์ได้บางส่วน:
     แนวโน้มหน่วยไฟ/ค่าไฟ + "ประมาณการ" ผลประหยัดเป็นช่วง (range) ไม่ฟันธงตัวเลขเดียว
     (ตามแนวทางแก้ข้อบกพร่องในไฟล์เทมเพลต: บิลอย่างเดียวต้องแสดงเป็นช่วง
      เพราะไม่รู้ self-consumption ratio และรูปแบบพีคจริง)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# ช่วงเวลากลางวัน/กลางคืน ตามไฟล์วิเคราะห์ของทีม
#   Day   07:00:00 - 17:59  |  Night 18:00 - 06:59
DAY_START_HOUR = 7
DAY_END_HOUR = 18   # exclusive

_TH_MONTH_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                  "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def thai_month_label(period: pd.Period) -> str:
    """'2025-01' -> 'ม.ค. 2568' (แสดงเป็น พ.ศ. ให้ตรงกับที่ทีมใช้)"""
    return f"{_TH_MONTH_ABBR[period.month - 1]} {period.year + 543}"


def day_night_monthly_summary(interval_df: pd.DataFrame,
                              day_start: int = DAY_START_HOUR,
                              day_end: int = DAY_END_HOUR) -> pd.DataFrame:
    """สรุปโหลดรายเดือน แยกกลางวัน/กลางคืน แบบเดียวกับชีต Day/Night ของทีม

    คืน DataFrame ต่อเดือน:
      month_label, day_avg_kw, day_max_kw, night_avg_kw, night_max_kw, n_points
    - Average = ค่าเฉลี่ยของโหลด (kW) ทุกช่วงในเดือนนั้น
    - Max     = ค่าสูงสุดของโหลด (kW) ที่เจอในเดือนนั้น (ฐานเดียวกับ demand peak)
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"])
    if not len(df):
        return pd.DataFrame()

    hours = df["timestamp"].dt.hour
    df["is_day"] = (hours >= day_start) & (hours < day_end)
    df["month"] = df["timestamp"].dt.to_period("M")

    rows = []
    for m, g in df.groupby("month"):
        d, n = g[g["is_day"]], g[~g["is_day"]]
        rows.append({
            "month": m,
            "month_label": thai_month_label(m),
            "day_avg_kw": round(float(d["load_kw"].mean()), 2) if len(d) else np.nan,
            "day_max_kw": round(float(d["load_kw"].max()), 2) if len(d) else np.nan,
            "night_avg_kw": round(float(n["load_kw"].mean()), 2) if len(n) else np.nan,
            "night_max_kw": round(float(n["load_kw"].max()), 2) if len(n) else np.nan,
            "n_points": int(len(g)),
        })
    return pd.DataFrame(rows).sort_values("month").reset_index(drop=True)


def monthly_total_kwh(interval_df: pd.DataFrame) -> pd.DataFrame:
    """พลังงานรวมต่อเดือน (kWh) จากข้อมูลรายช่วง = ผลรวม(kW x dt) ต่อเดือน
    ใช้หาว่าเดือนไหน 'ใช้ไฟมากสุด/น้อยสุด' เพื่อเอาโปรไฟล์ 2 เดือนนั้นมาโชว์
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"]).sort_values("timestamp")
    if len(df) < 2:
        return pd.DataFrame()
    deltas = df["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
    dt = float(deltas[deltas > 0].mode().iloc[0]) if (deltas > 0).any() else 0.25
    df["month"] = df["timestamp"].dt.to_period("M")
    df["kwh"] = df["load_kw"] * dt
    out = (df.groupby("month")
             .agg(total_kwh=("kwh", "sum"),
                  n_days=("timestamp", lambda s: s.dt.date.nunique()))
             .reset_index())
    out["month_label"] = out["month"].map(thai_month_label)
    return out


def hourly_avg_profile(interval_df: pd.DataFrame, period) -> pd.DataFrame:
    """โปรไฟล์โหลดเฉลี่ยรายชั่วโมง (24 จุด) ของเดือนที่ระบุ
    คืน DataFrame: hour (0-23), load_kw (ค่าเฉลี่ยของทุกวันในเดือนนั้น ณ ชั่วโมงนั้น)
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"])
    df = df[df["timestamp"].dt.to_period("M") == period]
    if not len(df):
        return pd.DataFrame({"hour": list(range(24)), "load_kw": [float("nan")] * 24})
    df["hour"] = df["timestamp"].dt.hour
    prof = df.groupby("hour")["load_kw"].mean().reindex(range(24))
    return pd.DataFrame({"hour": prof.index, "load_kw": prof.values})


def solar_hourly_profile(kwp: float, specific_yield: float = 4.0) -> list:
    """โปรไฟล์ PV เฉลี่ยรายชั่วโมง (24 จุด, kW) ของระบบขนาด kwp
    สเกลรูประฆังกลางวัน (06:00-18:00) ให้พลังงานรวมทั้งวัน = kwp x specific_yield (kWh/วัน)
    """
    hours = np.arange(24, dtype=float)
    bell = np.clip(np.sin(np.pi * (hours - 6) / 12.0), 0, None)
    bell = np.where((hours >= 6) & (hours <= 18), bell, 0.0)
    integral = bell.sum()
    daily_target = float(kwp) * float(specific_yield)
    scale = daily_target / integral if integral > 0 else 0.0
    return (bell * scale).tolist()


def linear_trend(y) -> list | None:
    """คืนค่าตามเส้นแนวโน้มเชิงเส้น (least squares) ของชุดข้อมูล y
    ใช้วาด 'เส้นประแนวโน้ม' แบบ Linear ในกราฟของทีม — ต้องมีจุดจริง >= 2 จุด
    """
    s = pd.to_numeric(pd.Series(y), errors="coerce")
    mask = s.notna()
    if mask.sum() < 2:
        return None
    x = np.arange(len(s), dtype=float)
    slope, intercept = np.polyfit(x[mask], s[mask], 1)
    return (slope * x + intercept).tolist()


def demand_peak_monthly(interval_df: pd.DataFrame, tariff=None) -> pd.DataFrame:
    """Demand Peak (kW) ต่อเดือน = ค่าสูงสุดของโหลด (เฉพาะช่วง On-Peak ถ้าส่ง tariff มา)"""
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"])
    if tariff is not None:
        df = df[[tariff.is_on_peak(t) for t in df["timestamp"]]]
    if not len(df):
        return pd.DataFrame()
    df["month"] = df["timestamp"].dt.to_period("M")
    out = (df.groupby("month")
             .agg(peak_kw=("load_kw", "max"),
                  peak_time=("load_kw", lambda s: df.loc[s.idxmax(), "timestamp"]))
             .reset_index())
    out["month_label"] = out["month"].map(thai_month_label)
    return out


# ---------------------------------------------------------------------------
# โปรไฟล์รายชั่วโมงเฉลี่ยต่อเดือน + เลือกเดือนใช้ไฟมากสุด/น้อยสุด
# (สำหรับกราฟเทียบโหลดจริง vs โซลาร์ 3 ขนาด)
# ---------------------------------------------------------------------------

def monthly_energy_ranking(interval_df: pd.DataFrame) -> pd.DataFrame:
    """สรุปพลังงานรวม (kWh) ต่อเดือน เรียงไว้ให้เลือกเดือนมากสุด/น้อยสุด
    ตัดเดือนที่ข้อมูลไม่ครบ (จุดน้อยผิดปกติ) ออก เพื่อไม่ให้เดือนข้อมูลพังถูกเลือกมาโชว์
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"])
    if not len(df):
        return pd.DataFrame()
    dt = _infer_dt(df)
    df["month"] = df["timestamp"].dt.to_period("M")
    g = df.groupby("month")
    out = g.agg(n_points=("load_kw", "size"),
                avg_kw=("load_kw", "mean"),
                energy_kwh=("load_kw", lambda s: float(s.sum()) * dt)).reset_index()
    # เดือนที่ "ครบพอ" = มีจุดอย่างน้อย 60% ของค่ามัธยฐานจุดต่อเดือน
    med = out["n_points"].median()
    out["is_full"] = out["n_points"] >= 0.6 * med
    out["month_label"] = out["month"].map(thai_month_label)
    return out.sort_values("energy_kwh").reset_index(drop=True)


def pv_hourly_profile(kwp: float, specific_yield: float = 4.0) -> "np.ndarray":
    """โปรไฟล์กำลังผลิตโซลาร์เฉลี่ยราย 'ชั่วโมงของวัน' (0-23) สำหรับระบบขนาด kwp
    รูประฆังกลางวัน (6-18น.) สเกลให้พลังงานรวมทั้งวัน = kwp * specific_yield (kWh/วัน)
    ใช้เทียบกับ hourly_avg_profile บนแกนเวลาเดียวกัน
    """
    hours = np.arange(24, dtype=float)
    bell = np.clip(np.sin(np.pi * (hours - 6) / 12.0), 0, None)
    bell = np.where((hours >= 6) & (hours <= 18), bell, 0.0)
    integral = bell.sum()  # dt = 1 ชม. ต่อจุด
    daily_kwh = float(kwp) * float(specific_yield)
    scale = daily_kwh / integral if integral > 0 else 0.0
    return bell * scale


def three_solar_sizes(catalog: pd.DataFrame, target_wp: float) -> dict:
    """เลือกกำลังแผง 3 ขนาดจาก catalog จริงสำหรับเส้นเทียบ:
    min (เล็กสุดที่มีขาย) · mid (กลางๆ ระหว่าง min กับ target) · near (ใกล้ target ที่สุด)
    คืน dict {label: kwp} — ใช้ค่าที่ 'มีจริงในสต็อก' ไม่ใช่ตัวเลขลอยๆ
    """
    if "panel_total_wp" not in catalog.columns:
        return {}
    wp = catalog["panel_total_wp"].dropna()
    wp = wp[wp > 0]
    if not len(wp):
        return {}
    sizes = sorted(wp.unique())
    kwp_list = [s / 1000.0 for s in sizes]
    tgt = (target_wp or 0) / 1000.0

    smin = kwp_list[0]
    # near = ค่าที่ใกล้ target ที่สุด (ถ้าไม่มี target ใช้ตัวใหญ่สุด)
    near = min(kwp_list, key=lambda k: abs(k - tgt)) if tgt > 0 else kwp_list[-1]
    # mid = ค่าที่ใกล้กึ่งกลางระหว่าง smin กับ near
    mid_target = (smin + near) / 2.0
    mid = min(kwp_list, key=lambda k: abs(k - mid_target))

    out = {}
    if smin > 0:
        out["min"] = round(smin, 2)
    if mid not in out.values():
        out["mid"] = round(mid, 2)
    if near not in out.values():
        out["near"] = round(near, 2)
    return out


def _infer_dt(df: pd.DataFrame) -> float:
    ts = pd.to_datetime(df["timestamp"]).sort_values().reset_index(drop=True)
    if len(ts) < 2:
        return 0.25
    d = (ts.iloc[1] - ts.iloc[0]).total_seconds() / 3600.0
    return d if d > 0 else 0.25


# ---------------------------------------------------------------------------
# ประมาณการผลประหยัดจาก "บิลรายเดือนอย่างเดียว" (กรณี B)
# ---------------------------------------------------------------------------

def estimate_savings_from_monthly(avg_kwh_month: float, avg_cost_month: float,
                                  package: pd.Series, tariff, *,
                                  specific_yield: float = 4.0,
                                  has_battery: bool = True,
                                  sc_low: float = 0.50,
                                  sc_high: float = 0.90) -> dict | None:
    """ประมาณผลประหยัด/เดือนของแพ็กนี้ จากบิลรายเดือน (ไม่มี interval data)

    หลักคิด (ระบุสมมติฐานชัด ไม่ฟันธง):
    - พลังงานที่โซลาร์ผลิตได้/เดือน = kWp x specific_yield x 30
    - เพราะไม่รู้โปรไฟล์รายชั่วโมง จึงไม่รู้ self-consumption ratio (สัดส่วนที่
      "ใช้เอง" แทนซื้อไฟ) -> คิดเป็นช่วง sc_low..sc_high (ดีฟอลต์ 50-90%)
    - แบตเตอรี่ช่วย "เก็บส่วนเกิน" ไปใช้ตอนไม่มีแดด -> เพิ่ม self-consumption
      ได้อีก จำกัดด้วย (ก) ส่วนเกินที่มี (ข) ความจุแบตใช้งานจริง 80% x 30 วัน
      (ค) หน่วยไฟที่ลูกค้ายังต้องซื้ออยู่
    - มูลค่าต่อหน่วย = ค่าไฟเฉลี่ยจริงต่อหน่วยจากบิล (cost/kwh) ถ้ามี
      ไม่งั้นใช้อัตรา On-Peak + Ft (โซลาร์ผลิตช่วงกลางวันซึ่งเป็น On-Peak)

    คืน dict {saving_low, saving_mid, saving_high, rate_used, note} หรือ None
    """
    kwp = float(package.get("panel_total_wp") or 0.0) / 1000.0
    if kwp <= 0 or not avg_kwh_month or avg_kwh_month <= 0:
        return None

    gen_month = kwp * float(specific_yield) * 30.0

    if avg_cost_month and avg_cost_month > 0:
        rate = float(avg_cost_month) / float(avg_kwh_month)
        rate_note = "ค่าไฟเฉลี่ยจริงต่อหน่วยจากบิล"
    else:
        rate = float(tariff.on_peak_rate) + float(tariff.ft_rate)
        rate_note = "อัตรา On-Peak + Ft (บิลไม่มียอดเงิน)"

    batt_kwh = package.get("battery_total_kwh")
    batt_kwh = float(batt_kwh) if has_battery and batt_kwh and not pd.isna(batt_kwh) else 0.0
    batt_month_cap = batt_kwh * 0.80 * 30.0   # DoD 80% x 1 รอบ/วัน

    def _saving(sc: float) -> float:
        direct = min(gen_month * sc, avg_kwh_month)          # ใช้เองตรงๆ ตอนมีแดด
        surplus = max(0.0, gen_month - direct)               # ส่วนเกินที่เหลือ
        via_batt = min(surplus, batt_month_cap,
                       max(0.0, avg_kwh_month - direct)) * 0.90  # หัก loss ไปกลับ ~10%
        return (direct + via_batt) * rate

    lo, hi = _saving(sc_low), _saving(sc_high)
    return {
        "saving_low": round(min(lo, hi), 2),
        "saving_high": round(max(lo, hi), 2),
        "saving_mid": round((lo + hi) / 2.0, 2),
        "rate_used": round(rate, 4),
        "note": (f"ประมาณการจากบิลรายเดือน (self-consumption {sc_low:.0%}-{sc_high:.0%}, "
                 f"มูลค่า/หน่วย = {rate_note})"),
    }
