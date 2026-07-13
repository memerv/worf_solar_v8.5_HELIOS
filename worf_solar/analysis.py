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
