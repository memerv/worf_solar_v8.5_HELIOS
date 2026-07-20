"""
โมดูล Quant — คิดเลขให้ฉลาดขึ้นบนข้อมูลเดิม (ไม่ต้องถามลูกค้าเพิ่ม)

4 ความสามารถหลัก:
  1) estimate_growth()      — ประเมินแนวโน้มการใช้ไฟโตขึ้น/ลดลง จากข้อมูลที่ลูกค้ามีจริง
                              (ไม่ต้องถามลูกค้าว่าจะขยายกิจการไหม — ลูกค้ามักตอบไม่ได้)
                              พร้อมบอก "ระดับความเชื่อมั่น" ตามปริมาณข้อมูลที่มี
  2) size_sweep()           — ไล่คำนวณ "ทุกขนาด" ที่มีขาย (รวมติดหลายชุด) แล้วเทียบผลตอบแทน
                              เพื่อหา "ขนาดที่คุ้มสุด" ไม่ใช่แค่ขนาดที่ใกล้โหลดสุด
  3) monte_carlo_payback()  — สุ่มสมมติฐาน (แดด/ค่าไฟ/เสื่อมสภาพ) หลายรอบ
                              สรุปเป็นช่วงคืนทุน P10-P90 แทนตัวเลขเป๊ะที่โดนแย้งง่าย
  4) score_lead()           — ให้คะแนนลูกค้าว่า "น่าจะคุ้มโซลาร์แค่ไหน" (เกรด A/B/C)
                              เอาไปรันกับฐานมิเตอร์ทั้งพื้นที่เพื่อหาลูกค้าเชิงรุกได้

หลักคิดสำคัญของการหา "ขนาดขั้นต่ำที่สมเหตุสมผล" (min_sensible_kwp):
  โซลาร์คุ้มที่สุดเมื่อไฟที่ผลิตถูก "ใช้เองหมด" ไม่เหลือทิ้ง
  -> ขนาดขั้นต่ำที่ควรเสนอ = ขนาดที่ผลิตพอดีกับ "โหลดฐานตอนกลางวัน" (baseload)
     ซึ่งลูกค้าใช้อยู่แล้วแน่ๆ ทุกวัน = ไฟไม่มีทางเหลือทิ้ง = คืนทุนเร็วที่สุด
  ไม่ใช่ "แพ็กเล็กสุดที่มีในสต็อก" (เช่นเสนอ 3 kWp ให้ลูกค้าที่ใช้ 120 kWp = ไม่สมเหตุผล)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from finance import simple_payback, npv, irr


# ---------------------------------------------------------------------------
# 1) ประเมินแนวโน้มการใช้ไฟจากข้อมูลที่มีจริง (ไม่ต้องถามลูกค้า)
# ---------------------------------------------------------------------------

def estimate_growth(monthly_kwh, dates=None) -> dict:
    """ประเมินอัตราการเติบโตของการใช้ไฟต่อปี จากข้อมูลรายเดือนที่ลูกค้ามี

    ปรับตามความเป็นจริง: ลูกค้าบางรายมีบิลเดือนเดียว บางรายมี 6 เดือน บางราย 1-2 ปี
    ระบบจึงเลือกวิธีที่เหมาะกับ "ข้อมูลที่มีจริง" และบอกความเชื่อมั่นตรงๆ

      >= 24 เดือน : เทียบ 12 เดือนล่าสุด vs 12 เดือนก่อนหน้า — ตัดผลฤดูกาลออกได้ = เชื่อมั่นสูง
      13-23 เดือน : เทียบ "เดือนเดียวกันของคนละปี" เฉพาะเดือนที่มีข้อมูลทั้งสองปี
                     (เช่น มี.ค.68 vs มี.ค.67) — ตัดผลฤดูกาลออกได้ = เชื่อมั่นปานกลาง
      <= 12 เดือน : **ประเมินแนวโน้มไม่ได้** เพราะแยก "โตขึ้นจริง" ออกจาก "ผลฤดูกาล" ไม่ได้
                     (ไทยร้อนสุด เม.ย. หนาวสุด ธ.ค. ถ้าลากเส้นตรงจะได้แนวโน้มลบทั้งที่
                      การใช้ไฟไม่ได้ลดลงจริง) -> ใช้ 0%/ปี ซึ่งปลอดภัยกว่าการเดา

    รับได้ทั้ง list ธรรมดา และ pd.Series ที่ index เป็น Period รายเดือน
    (ถ้าเป็น Series จะทำ YoY แบบจับคู่เดือนได้แม่นกว่า)

    คืน dict: growth_rate (ทศนิยม/ปี), confidence ('high'|'medium'|'low'|'none'),
              method (คำอธิบายไทย), n_months
    """
    if isinstance(monthly_kwh, pd.Series):
        s = monthly_kwh.dropna()
        s = s[s > 0]
    else:
        s = pd.Series(list(monthly_kwh), dtype="float64").dropna()
        s = s[s > 0]
    n = len(s)

    if n < 3:
        return {"growth_rate": 0.0, "confidence": "none", "n_months": n,
                "method": (f"มีข้อมูลเพียง {n} เดือน — ประเมินแนวโน้มไม่ได้ "
                           "ใช้สมมติฐานคงที่ (โต 0%/ปี) แนะนำขอบิลย้อนหลัง 12-24 เดือน")}

    has_periods = isinstance(s.index, pd.PeriodIndex)

    if n >= 24:
        recent = float(s.iloc[-12:].sum())
        prior = float(s.iloc[-24:-12].sum())
        rate = (recent / prior - 1.0) if prior > 0 else 0.0
        conf = "high"
        method = "เทียบ 12 เดือนล่าสุด กับ 12 เดือนก่อนหน้า — ตัดผลฤดูกาลออกแล้ว"
    elif n >= 13 and has_periods:
        # จับคู่ "เดือนเดียวกันคนละปี" เพื่อตัดผลฤดูกาลออก
        tmp = pd.DataFrame({"kwh": s.values, "m": s.index.month, "y": s.index.year})
        pairs = []
        for m, g in tmp.groupby("m"):
            if g["y"].nunique() >= 2:
                g2 = g.sort_values("y")
                old, new = float(g2["kwh"].iloc[0]), float(g2["kwh"].iloc[-1])
                yr_gap = int(g2["y"].iloc[-1] - g2["y"].iloc[0])
                if old > 0 and yr_gap > 0:
                    pairs.append((new / old) ** (1.0 / yr_gap) - 1.0)
        if pairs:
            rate = float(np.mean(pairs))
            conf = "medium"
            method = (f"เทียบเดือนเดียวกันของคนละปี {len(pairs)} คู่ "
                      "(เช่น มี.ค. ปีนี้ vs มี.ค. ปีก่อน) — ตัดผลฤดูกาลออกแล้ว")
        else:
            rate, conf = 0.0, "low"
            method = f"มีข้อมูล {n} เดือน แต่จับคู่เดือนเดียวกันคนละปีไม่ได้ — ใช้ 0%/ปี"
    else:
        # <= 12 เดือน (หรือไม่มี index เดือน): แยกแนวโน้มออกจากฤดูกาลไม่ได้
        rate, conf = 0.0, "low"
        method = (f"มีข้อมูล {n} เดือน (ไม่ถึง 2 ปี) — แยก 'การใช้ไฟโตขึ้นจริง' "
                  "ออกจาก 'ผลฤดูกาล' ไม่ได้ จึงใช้ 0%/ปี (ไม่เดา) "
                  "หากต้องการเผื่ออนาคต แนะนำขอบิลย้อนหลัง 24 เดือน")

    rate = float(np.clip(rate, -0.30, 0.30))  # กันค่าเพี้ยนจากข้อมูลผิดปกติ
    return {"growth_rate": rate, "confidence": conf, "n_months": n, "method": method}


def project_future_kwh(avg_kwh_month: float, growth_rate: float,
                       years_ahead: float = 2.5) -> float:
    """ฉายภาพการใช้ไฟเฉลี่ยไปข้างหน้า (ดีฟอลต์กลางอายุการตัดสินใจ ~2-3 ปี)
    ใช้ปรับ 'เป้าหมายขนาดระบบ' ให้เผื่ออนาคต โดยไม่ต้องถามลูกค้าว่าจะขยายไหม
    """
    return float(avg_kwh_month) * ((1.0 + growth_rate) ** years_ahead)


# ---------------------------------------------------------------------------
# โมเดลผลประหยัดแบบเร็ว (ใช้โปรไฟล์รายชั่วโมง) — หัวใจของ sweep และ Monte Carlo
# ---------------------------------------------------------------------------

def build_hourly_profiles(interval_df: pd.DataFrame) -> dict:
    """สร้างโปรไฟล์โหลดเฉลี่ยรายชั่วโมง (24 จุด) แยกตามเดือน + น้ำหนักจำนวนวัน
    คืน dict {'profiles': {month_period: np.array(24)}, 'days': {month: n_days},
              'weekday_share': สัดส่วนวันธรรมดา}
    ใช้เป็นฐานคำนวณซ้ำหลายพันรอบได้เร็ว (แทนการ dispatch ราย 15 นาทีทุกรอบ)
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"])
    if not len(df):
        return {"profiles": {}, "days": {}, "weekday_share": 5 / 7}

    df["month"] = df["timestamp"].dt.to_period("M")
    df["hour"] = df["timestamp"].dt.hour
    profiles, days = {}, {}
    for m, g in df.groupby("month"):
        prof = g.groupby("hour")["load_kw"].mean().reindex(range(24))
        prof = prof.interpolate().bfill().ffill()
        profiles[m] = prof.values.astype(float)
        days[m] = int(g["timestamp"].dt.date.nunique())

    wk = df["timestamp"].dt.dayofweek
    weekday_share = float((wk < 5).mean()) if len(wk) else 5 / 7
    return {"profiles": profiles, "days": days, "weekday_share": weekday_share}


def _pv_bell(kwp: float, specific_yield: float) -> np.ndarray:
    """โปรไฟล์ PV รายชั่วโมง (24 จุด, kW) พลังงานรวม/วัน = kwp * specific_yield"""
    hours = np.arange(24, dtype=float)
    bell = np.clip(np.sin(np.pi * (hours - 6) / 12.0), 0, None)
    bell = np.where((hours >= 6) & (hours <= 18), bell, 0.0)
    total = bell.sum()
    return bell * (kwp * specific_yield / total) if total > 0 else bell


def fast_annual_savings(prof_data: dict, kwp: float, batt_kwh: float,
                        tariff, *, specific_yield: float = 4.0,
                        batt_efficiency: float = 0.90,
                        batt_dod: float = 0.80) -> dict:
    """ประเมินผลประหยัดต่อปี (บาท) แบบเร็วจากโปรไฟล์รายชั่วโมง

    ตรรกะต่อ 1 ชั่วโมง:
      - PV ใช้ชนกับโหลดก่อน (self-consumption) -> ประหยัดที่ราคาช่วงเวลานั้น
      - PV เหลือ -> ชาร์จแบต (จำกัดด้วยความจุใช้งานจริง = kWh x DoD)
      - โหลดเกิน PV ตอนไม่มีแดด -> ดึงแบตมาใช้ (คูณ efficiency) ประหยัดที่ราคาช่วงนั้น
      - PV เหลือหลังแบตเต็ม = ไฟทิ้ง (ไม่คิดเป็นเงิน — ไม่สมมติว่าขายคืนได้)

    คืน dict: saving_year, self_consumed_kwh, waste_kwh, self_consumption_ratio
    """
    profiles, days = prof_data["profiles"], prof_data["days"]
    if not profiles or kwp <= 0:
        return {"saving_year": 0.0, "self_consumed_kwh": 0.0,
                "waste_kwh": 0.0, "self_consumption_ratio": 0.0}

    pv = _pv_bell(kwp, specific_yield)
    usable_batt = max(0.0, float(batt_kwh) * batt_dod)

    # ราคาต่อหน่วยรายชั่วโมง (ใช้วันธรรมดาเป็นตัวแทน — โซลาร์ผลิตทุกวันอยู่แล้ว)
    ref_day = pd.Timestamp("2025-06-16")  # จันทร์
    price_h = np.array([tariff.energy_price(ref_day + pd.Timedelta(hours=int(h)))
                        for h in range(24)], dtype=float)

    total_saving = total_self = total_waste = total_gen = 0.0
    for m, load in profiles.items():
        nd = days.get(m, 30)
        soc = 0.0
        day_saving = day_self = day_waste = 0.0
        for h in range(24):
            gen, ld = pv[h], float(load[h])
            direct = min(gen, ld)                    # ใช้ชนโหลดตรงๆ
            day_saving += direct * price_h[h]
            day_self += direct
            surplus = gen - direct
            deficit = ld - direct
            if surplus > 0 and usable_batt > 0:      # เก็บส่วนเกินเข้าแบต
                charge = min(surplus, usable_batt - soc)
                soc += charge
                surplus -= charge
            if surplus > 0:
                day_waste += surplus                 # เหลือทิ้ง (ไม่คิดเป็นรายได้)
            if deficit > 0 and soc > 0:              # ดึงแบตมาใช้แทนซื้อไฟ
                use = min(deficit * (1 / batt_efficiency), soc)
                delivered = use * batt_efficiency
                soc -= use
                day_saving += delivered * price_h[h]
                day_self += delivered
        total_saving += day_saving * nd
        total_self += day_self * nd
        total_waste += day_waste * nd
        total_gen += pv.sum() * nd

    # normalize เป็น "ต่อปี" (ข้อมูลอาจไม่ครบ 12 เดือน)
    n_days_total = sum(days.values()) or 1
    scale = 365.0 / n_days_total
    gen_y = total_gen * scale
    return {
        "saving_year": total_saving * scale,
        "self_consumed_kwh": total_self * scale,
        "waste_kwh": total_waste * scale,
        "self_consumption_ratio": (total_self * scale / gen_y) if gen_y > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# ขนาดขั้นต่ำที่ "สมเหตุสมผล" — ตอบโจทย์: ทำไมไม่เสนอ 3 kWp ให้คนใช้ 120 kWp
# ---------------------------------------------------------------------------

def min_sensible_kwp(prof_data: dict, specific_yield: float = 4.0,
                     percentile: float = 25.0) -> dict:
    """หาขนาดโซลาร์ขั้นต่ำที่ 'สมเหตุสมผล' กับพฤติกรรมลูกค้า

    หลักคิด: ขนาดที่เล็กที่สุดที่ยัง 'คุ้มค่าจริง' คือขนาดที่ผลิตไฟไม่เกิน
    'โหลดฐานตอนกลางวัน' (daytime baseload) ที่ลูกค้าใช้อยู่แล้วทุกวัน
    -> ไฟที่ผลิตถูกใช้เองหมด 100% ไม่มีทิ้ง = คืนทุนเร็วที่สุดต่อบาทที่ลงทุน
    เล็กกว่านี้ = ลงทุนน้อยจริง แต่ประหยัดน้อยตามสัดส่วน ไม่ได้คุ้มขึ้น
    และไม่สมเหตุผลกับสเกลการใช้ไฟของลูกค้า (เช่นเสนอ 3 kWp ให้โรงงานใช้ 120 kWp)

    วิธี: ดูโหลดช่วงมีแดด (9-15น. ซึ่ง PV ผลิตแรง) เอา percentile ต่ำ (ดีฟอลต์ P25)
    เป็น 'โหลดฐานที่มั่นใจว่ามีเกือบทุกวัน' แล้วแปลงเป็น kWp

    คืน dict: kwp, baseload_kw, method
    """
    profiles = prof_data.get("profiles", {})
    if not profiles:
        return {"kwp": 0.0, "baseload_kw": 0.0, "method": "ไม่มีข้อมูลโหลด"}

    core = range(9, 16)  # ช่วงที่ PV ผลิตได้แรงจริง
    vals = [float(load[h]) for load in profiles.values() for h in core]
    if not vals:
        return {"kwp": 0.0, "baseload_kw": 0.0, "method": "ไม่มีข้อมูลช่วงกลางวัน"}

    baseload = float(np.percentile(vals, percentile))
    # PV ที่ชั่วโมงกลางวันแรงสุด ~ (kwp*specific_yield)/pv_bell_sum * bell_peak
    bell = _pv_bell(1.0, specific_yield)
    peak_per_kwp = float(bell[12])          # กำลังผลิตต่อ 1 kWp ณ เที่ยง
    kwp = baseload / peak_per_kwp if peak_per_kwp > 0 else 0.0
    return {
        "kwp": round(kwp, 1),
        "baseload_kw": round(baseload, 1),
        "method": (f"โหลดฐานกลางวัน (P{percentile:.0f} ของช่วง 9-15น.) = {baseload:,.1f} kW "
                   f"-> ขนาดที่ผลิตพอดีไม่เหลือทิ้ง ≈ {kwp:,.1f} kWp"),
    }


# ---------------------------------------------------------------------------
# 2) Size sweep — ไล่ทุกขนาดที่ขายได้จริง (รวมติดหลายชุด) หา "ขนาดคุ้มสุด"
# ---------------------------------------------------------------------------

def size_sweep(catalog: pd.DataFrame, prof_data: dict, tariff, *,
               want_battery: bool = True, specific_yield: float = 4.0,
               horizon_years: int = 25, discount_rate: float = 0.07,
               escalation: float = 0.03, max_units: int = 4,
               avail_area_sqm: float | None = None) -> pd.DataFrame:
    """ไล่คำนวณผลตอบแทนของ 'ทุกขนาดที่ซื้อได้จริง' รวมกรณีติดหลายชุดขนานกัน

    ตอบโจทย์: ลูกค้าต้องการ 120 kWp แต่แพ็กใหญ่สุดมี 50 kWp
    -> ระบบจะลอง 50x1, 50x2 (=100), 50x3 (=150) ฯลฯ แล้วเทียบ NPV/คืนทุนให้เห็นชัด
    ว่าขนาดไหนคุ้มสุดจริง ไม่ใช่แค่เดาว่า 'ใกล้โหลดสุด = ดีสุด'

    คืน DataFrame ต่อ 1 ตัวเลือก: kwp_total, n_units, package_code, capex,
    saving_year, payback_years, npv, irr, self_consumption_ratio, waste_kwh
    """
    df = catalog.copy()
    if want_battery and "battery_total_kwh" in df.columns:
        df = df[df["battery_total_kwh"].fillna(0) > 0]
    elif "battery_total_kwh" in df.columns:
        df = df[df["battery_total_kwh"].fillna(0) == 0]
    for c in ("panel_total_wp", "catalog_price"):
        if c not in df.columns:
            return pd.DataFrame()
        df = df.dropna(subset=[c])
    df = df[(df["panel_total_wp"] > 0) & (df["catalog_price"] > 0)]
    # กันราคาผิดปกติในแคตตาล็อก (พิมพ์ตกหลัก) ไม่ให้ชนะการจัดอันดับ
    ppw = df["catalog_price"] / df["panel_total_wp"]
    df = df[(ppw >= 10) & (ppw <= 120)]
    if not len(df):
        return pd.DataFrame()

    # แต่ละขนาดเลือกตัวแทน "ถูกสุดต่อวัตต์" (ตัวเลือกที่ดีที่สุดของขนาดนั้น)
    df = df.assign(_ppw=ppw)
    reps = (df.sort_values("_ppw").groupby("panel_total_wp", as_index=False).first())

    rows = []
    for _, r in reps.iterrows():
        unit_wp = float(r["panel_total_wp"])
        unit_price = float(r["catalog_price"])
        unit_batt = float(r.get("battery_total_kwh") or 0.0)
        unit_area = float(r.get("install_area_sqm") or 0.0)
        for n in range(1, int(max_units) + 1):
            kwp = unit_wp * n / 1000.0
            area = unit_area * n
            if avail_area_sqm and unit_area > 0 and area > float(avail_area_sqm):
                break  # ใหญ่เกินพื้นที่ที่มี
            res = fast_annual_savings(prof_data, kwp, unit_batt * n, tariff,
                                      specific_yield=specific_yield)
            sy = res["saving_year"]
            capex = unit_price * n
            if sy <= 0:
                continue
            rows.append({
                "package_code": r.get("package_code") or r.get("pack_id"),
                "n_units": n,
                "kwp_total": round(kwp, 2),
                "battery_kwh_total": round(unit_batt * n, 2),
                "capex": capex,
                "saving_year": sy,
                "saving_month": sy / 12.0,
                "payback_years": simple_payback(capex, sy),
                "npv": npv(capex, sy, horizon_years, discount_rate, escalation),
                "irr": irr(capex, sy, horizon_years, escalation),
                "self_consumption_ratio": res["self_consumption_ratio"],
                "waste_kwh": res["waste_kwh"],
                "area_sqm": area if unit_area > 0 else None,
                "inverter_brand": r.get("inverter_brand"),
                "battery_brand": r.get("battery_brand"),
            })
    out = pd.DataFrame(rows)
    return out.sort_values("kwp_total").reset_index(drop=True) if len(out) else out


def pick_sweep_options(sweep: pd.DataFrame, min_kwp: float,
                       target_kwp: float) -> dict:
    """เลือก 3 ตัวเลือกจากผล sweep ให้ทีมขายเสนอ:
      floor  : ขนาดขั้นต่ำที่สมเหตุสมผล (>= min_kwp จากโหลดฐานกลางวัน) ที่คืนทุนเร็วสุด
      best   : ขนาดที่ 'คุ้มสุด' = NPV สูงสุด (ตอบโจทย์ข้อ 3 โดยตรง)
      target : ขนาดที่ใกล้เป้าหมายการใช้ไฟจริงที่สุด
    """
    if not len(sweep):
        return {}
    out = {}
    floor_pool = sweep[sweep["kwp_total"] >= max(0.0, min_kwp * 0.9)]
    if len(floor_pool):
        out["floor"] = floor_pool.sort_values("payback_years").iloc[0]
    else:
        out["floor"] = sweep.sort_values("kwp_total").iloc[-1]
    out["best"] = sweep.sort_values("npv", ascending=False).iloc[0]
    if target_kwp and target_kwp > 0:
        idx = (sweep["kwp_total"] - target_kwp).abs().idxmin()
        out["target"] = sweep.loc[idx]
    return out


# ---------------------------------------------------------------------------
# 3) Monte Carlo — บอกเป็นช่วงที่น่าเชื่อถือ แทนตัวเลขเป๊ะ
# ---------------------------------------------------------------------------

def monte_carlo_payback(prof_data: dict, kwp: float, batt_kwh: float,
                        capex: float, tariff, *, specific_yield: float = 4.0,
                        n_draws: int = 400, horizon_years: int = 25,
                        discount_rate: float = 0.07, escalation_mean: float = 0.03,
                        growth_rate: float = 0.0, seed: int = 42) -> dict:
    """สุ่มสมมติฐานหลายรอบ แล้วสรุปคืนทุนเป็นช่วง P10-P90

    ตัวแปรที่สุ่ม (อิงความไม่แน่นอนจริงของงานโซลาร์):
      - specific yield  : แดดแต่ละปีไม่เท่ากัน (+/-10%) และทิศ/องศา/เงา/ฝุ่นหน้างาน
      - tariff escalation: ค่าไฟขึ้นปีละกี่ % (ไม่แน่นอน)
      - degradation      : แผงเสื่อม 0.4-0.8%/ปี
      - performance ratio: สูญเสียในระบบจริง (สายไฟ/อินเวอร์เตอร์/ฝุ่น) 78-88%
      - ค่าดูแลรักษา (O&M): 0.5-1.5% ของเงินลงทุนต่อปี (ล้างแผง/ตรวจระบบ/ประกัน)

    หมายเหตุ: ยังไม่รวมค่าเปลี่ยนแบตเตอรี่กลางอายุโครงการ (ตัดออกตามสเปคเดิม)
    ถ้าอายุโครงการยาวกว่าอายุแบต ตัวเลขจะดูดีกว่าความจริง

    คืน dict: payback_p10/p50/p90, npv_p10/p50/p90, prob_payback_under (dict),
              n_draws
    """
    rng = np.random.default_rng(seed)
    if kwp <= 0 or capex <= 0:
        return {}

    paybacks, npvs = [], []
    for _ in range(int(n_draws)):
        sy_draw = specific_yield * rng.normal(1.0, 0.10)      # แดดปีนี้ดี/แย่
        sy_draw = float(np.clip(sy_draw, specific_yield * 0.7, specific_yield * 1.3))
        pr = float(rng.uniform(0.78, 0.88))                   # performance ratio จริง
        esc = float(np.clip(rng.normal(escalation_mean, 0.015), -0.01, 0.08))
        degr = float(rng.uniform(0.004, 0.008))               # เสื่อม %/ปี
        om_rate = float(rng.uniform(0.005, 0.015))            # ค่าดูแลรักษา/ปี

        res = fast_annual_savings(prof_data, kwp, batt_kwh, tariff,
                                  specific_yield=sy_draw * pr / 0.83)
        base_saving = res["saving_year"]
        if base_saving <= 0:
            continue
        # เผื่อการใช้ไฟโตขึ้น (ทำให้ self-consumption ดีขึ้นเล็กน้อย) แบบอนุรักษ์นิยม
        base_saving *= (1.0 + min(growth_rate, 0.10) * 0.5)

        # กระแสเงินสด: ผลประหยัดโตตามค่าไฟ ลดตามแผงเสื่อม แล้วหักค่าดูแลรักษา
        flows, cum, pay = [-capex], -capex, float("inf")
        for t in range(1, horizon_years + 1):
            gross = base_saving * ((1 + esc) ** (t - 1)) * ((1 - degr) ** (t - 1))
            om = capex * om_rate * ((1 + esc) ** (t - 1))
            net = gross - om
            flows.append(net)
            if pay == float("inf") and net > 0:
                if cum + net >= 0:
                    pay = (t - 1) + (-cum / net)
                cum += net
        paybacks.append(pay)
        npvs.append(sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(flows)))

    if not paybacks:
        return {}
    pb = np.array([p for p in paybacks if np.isfinite(p)])
    if not len(pb):
        return {}
    nv = np.array(npvs)
    return {
        "payback_p10": float(np.percentile(pb, 10)),
        "payback_p50": float(np.percentile(pb, 50)),
        "payback_p90": float(np.percentile(pb, 90)),
        "npv_p10": float(np.percentile(nv, 10)),
        "npv_p50": float(np.percentile(nv, 50)),
        "npv_p90": float(np.percentile(nv, 90)),
        "prob_npv_positive": float((nv > 0).mean()),
        "prob_payback_under": {y: float((pb <= y).mean()) for y in (5, 7, 10)},
        "n_draws": int(len(pb)),
    }


# ---------------------------------------------------------------------------
# 4) Lead scoring — หาลูกค้าเชิงรุกจากฐานมิเตอร์ที่ PEA มีอยู่แล้ว
# ---------------------------------------------------------------------------

def score_lead(prof_data: dict, avg_kwh_month: float, avg_cost_month: float = 0.0,
               growth_rate: float = 0.0) -> dict:
    """ให้คะแนน 0-100 ว่าลูกค้ารายนี้ 'น่าจะคุ้มโซลาร์' แค่ไหน + เกรด A/B/C

    ใช้เฉพาะข้อมูลที่ PEA มีอยู่แล้ว (โหลดโปรไฟล์จากมิเตอร์) จึงรันกับฐานลูกค้า
    ทั้งพื้นที่ได้เลย ไม่ต้องรอลูกค้าเดินมาหา

    องค์ประกอบคะแนน (รวม 100):
      40 : สัดส่วนการใช้ไฟกลางวัน (9-15น.) — โซลาร์ช่วยได้เฉพาะตอนมีแดด
      25 : ขนาดการใช้ไฟ (ยิ่งใช้เยอะ ยิ่งประหยัดได้เยอะ คุ้มค่าติดตั้ง)
      20 : ความสม่ำเสมอของโหลดกลางวัน (ยิ่งนิ่ง ยิ่งใช้ไฟโซลาร์ได้เต็ม ไม่ทิ้ง)
      10 : ใช้ไฟวันธรรมดา/เสาร์อาทิตย์ใกล้เคียงกัน (โรงงานเดินเครื่อง 7 วัน = คุ้มกว่า)
       5 : แนวโน้มการใช้ไฟโตขึ้น
    """
    profiles = prof_data.get("profiles", {})
    if not profiles or avg_kwh_month <= 0:
        return {"score": 0, "grade": "-", "reasons": ["ข้อมูลไม่พอประเมิน"]}

    all_prof = np.vstack(list(profiles.values()))
    mean_prof = all_prof.mean(axis=0)
    day_core = mean_prof[9:16]
    total_day = float(mean_prof.sum())

    reasons = []
    # 1) สัดส่วนใช้ไฟกลางวัน (6-18น.)
    day_share = float(mean_prof[6:18].sum() / total_day) if total_day > 0 else 0
    s1 = float(np.clip((day_share - 0.30) / 0.40, 0, 1)) * 40
    reasons.append(f"ใช้ไฟช่วงกลางวัน {day_share:.0%} ของทั้งวัน")

    # 2) ขนาดการใช้ไฟ (log scale: 1,000 -> 100,000 kWh/เดือน)
    s2 = float(np.clip((np.log10(max(avg_kwh_month, 1)) - 3.0) / 2.0, 0, 1)) * 25
    reasons.append(f"ใช้ไฟเฉลี่ย {avg_kwh_month:,.0f} kWh/เดือน")

    # 3) ความสม่ำเสมอกลางวัน (CV ต่ำ = นิ่ง = ดี)
    cv = float(day_core.std() / day_core.mean()) if day_core.mean() > 0 else 1.0
    s3 = float(np.clip(1.0 - cv / 0.5, 0, 1)) * 20
    reasons.append(f"โหลดกลางวันสม่ำเสมอ (ผันผวน {cv:.0%})")

    # 4) ใช้ไฟทุกวันหรือเฉพาะวันธรรมดา
    wshare = prof_data.get("weekday_share", 5 / 7)
    s4 = float(np.clip(1.0 - abs(wshare - 5 / 7) / 0.3, 0, 1)) * 10

    # 5) แนวโน้มโต
    s5 = float(np.clip(growth_rate / 0.10, 0, 1)) * 5
    if growth_rate > 0.02:
        reasons.append(f"การใช้ไฟมีแนวโน้มโต {growth_rate:.1%}/ปี")

    score = s1 + s2 + s3 + s4 + s5
    grade = "A" if score >= 70 else ("B" if score >= 50 else "C")
    return {
        "score": round(score, 1), "grade": grade,
        "day_share": day_share, "daytime_cv": cv,
        "avg_kwh_month": avg_kwh_month, "avg_cost_month": avg_cost_month,
        "reasons": reasons,
    }


def score_lead_batch(customers: dict, tariff=None) -> pd.DataFrame:
    """ให้คะแนนลูกค้าหลายรายพร้อมกัน แล้วเรียงลำดับความน่าสนใจ (A -> C)

    customers: dict {ชื่อลูกค้า: interval_df}
    ใช้กับฐานข้อมูลมิเตอร์ทั้งพื้นที่เพื่อสร้าง 'ลิสต์ลูกค้าที่ควรเข้าไปคุยก่อน'
    """
    rows = []
    for name, df in customers.items():
        try:
            pd_ = build_hourly_profiles(df)
            avg_kwh = float(df["load_kw"].mean()) * 24 * 30
            mk = monthly_total_kwh_simple(df)
            g = estimate_growth(mk)["growth_rate"] if len(mk) >= 3 else 0.0
            sc = score_lead(pd_, avg_kwh, growth_rate=g)
            rows.append({"customer": name, "grade": sc["grade"], "score": sc["score"],
                         "avg_kwh_month": avg_kwh, "day_share": sc.get("day_share"),
                         "growth_rate": g})
        except Exception as e:  # ข้ามลูกค้าที่ข้อมูลพัง ไม่ให้ล้มทั้ง batch
            rows.append({"customer": name, "grade": "-", "score": 0,
                         "avg_kwh_month": None, "day_share": None,
                         "growth_rate": None, "error": str(e)[:60]})
    out = pd.DataFrame(rows)
    return out.sort_values("score", ascending=False).reset_index(drop=True) if len(out) else out


def monthly_total_kwh_simple(interval_df: pd.DataFrame) -> pd.Series:
    """พลังงานรายเดือน (kWh, ปรับเป็นฐาน 30 วัน) ใช้ป้อน estimate_growth

    คืน pd.Series ที่ index เป็น Period รายเดือน เพื่อให้ estimate_growth
    จับคู่ 'เดือนเดียวกันคนละปี' ตัดผลฤดูกาลออกได้

    ปรับให้ทำงานกับข้อมูลที่ไม่ครบเดือนได้ (เช่นไฟล์ตัวอย่าง 1 วัน/เดือน หรือ
    มิเตอร์ที่บันทึกขาดบางวัน) โดย normalize เป็น 'ต่อวันเฉลี่ย x 30'
    แทนการทิ้งเดือนนั้นไปเลย — ไม่งั้นจะได้ 0 เดือนแล้วประเมินแนวโน้มไม่ได้
    """
    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp", "load_kw"]).sort_values("timestamp")
    if len(df) < 2:
        return pd.Series(dtype="float64")
    deltas = df["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
    dt = float(deltas[deltas > 0].mode().iloc[0]) if (deltas > 0).any() else 0.25
    vals, idx = [], []
    for m, gg in df.groupby(df["timestamp"].dt.to_period("M")):
        nd = gg["timestamp"].dt.date.nunique()
        if len(gg) < 12 or nd < 1:
            continue                       # ข้อมูลน้อยเกินจนไม่เป็นตัวแทนเดือนนั้น
        kwh = float(gg["load_kw"].sum()) * dt
        vals.append(kwh / nd * 30.0)       # ปรับเป็นฐาน 30 วัน เทียบกันได้ทุกเดือน
        idx.append(m)
    return pd.Series(vals, index=pd.PeriodIndex(idx, freq="M"), dtype="float64")
