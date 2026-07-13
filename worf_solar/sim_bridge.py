"""
สะพานเชื่อม data ลูกค้าจริง -> simulator เพื่อคำนวณ "ผลประหยัดจริงต่อแพ็ก"
แก้ #1: เดิม app.py ใช้ claimed_saving_month (ตัวเลขที่ vendor เคลมในไฟล์ catalog)
ตรงๆ โดยไม่แตะข้อมูลการใช้ไฟจริงของลูกค้าเลย โมดูลนี้ทำให้ตัวเลขที่โชว์
มาจากการจำลองบนโหลดจริงของลูกค้า เทียบกับ spec ของแต่ละแพ็ก

ข้อจำกัด (ต้องแจ้งผู้ใช้เสมอ — สอดคล้องกับคำเตือนใน finance.py):
- โปรไฟล์ PV เป็นการ "ประมาณ" จาก panel_total_wp + specific yield (kWh/kWp/วัน)
  ไม่ใช่ผลวัดจริงหน้างาน (ขึ้นกับทิศ/องศา/เงา/ฝุ่น)
- ใช้ rule-based dispatch เป็นค่าเริ่มต้น (เร็ว/ทำซ้ำได้) ส่วน MILP (perfect-foresight)
  เปิดได้แต่ช้าและให้ตัวเลข "เพดานบน" ที่มองโลกในแง่ดีเกินจริง
- ต้องมีข้อมูล interval (รายช่วง) ของลูกค้าจริงเท่านั้น ถ้ามีแค่บิลรายเดือน
  จะประเมินผลประหยัดแบบนี้ไม่ได้ (คืน None ให้ app fallback ไปใช้ค่าเคลม)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from battery import Battery
from optimizer import rule_based_dispatch, _infer_dt_hours


def _inject_solar(df: pd.DataFrame, panel_total_wp: float,
                  specific_yield: float) -> pd.DataFrame:
    """ใส่โปรไฟล์ PV (solar_kw) ลงใน interval data ของลูกค้า
    สเกลให้พลังงานรายวัน = kWp * specific_yield (kWh/kWp/วัน) เสมอ ไม่ว่า dt เท่าไร
    """
    kwp = float(panel_total_wp or 0.0) / 1000.0
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    hours = out["timestamp"].dt.hour + out["timestamp"].dt.minute / 60.0
    bell = np.clip(np.sin(np.pi * (hours - 6) / 12.0), 0, None)
    bell = np.where((hours >= 6) & (hours <= 18), bell, 0.0)
    out["_bell"] = bell
    out["date"] = out["timestamp"].dt.date
    dt = _infer_dt_hours(out)

    solar = pd.Series(0.0, index=out.index)
    for _, g in out.groupby("date"):
        integral = float((g["_bell"] * dt).sum())      # พื้นที่ใต้ระฆังต่อ 1 kW peak
        daily_target = kwp * specific_yield              # kWh ที่ควรผลิตวันนั้น
        scale = daily_target / integral if integral > 0 else 0.0
        solar.loc[g.index] = g["_bell"] * scale
    out["solar_kw"] = solar
    return out[["timestamp", "solar_kw", "load_kw"]]


def _monthly_bill(ts_list, grid_kwh_per_step, tariff, dt: float, n_days: int) -> float:
    """คิดบิลรวม/เดือน จาก series พลังงานที่ซื้อจาก grid (kWh ต่อช่วง)
    normalize เป็น 'ต่อเดือน' = ค่าพลังงานเฉลี่ยต่อวัน*30 + demand charge (พีคที่สังเกตได้) + service
    """
    energy_cost = sum(tariff.energy_price(t) * e for t, e in zip(ts_list, grid_kwh_per_step))
    daily_energy_cost = energy_cost / max(1, n_days)
    monthly_energy_cost = daily_energy_cost * 30.0

    on_peak_kw = [e / dt for t, e in zip(ts_list, grid_kwh_per_step) if tariff.is_on_peak(t)]
    peak_demand = max(on_peak_kw) if on_peak_kw else 0.0
    return tariff.monthly_bill(monthly_energy_cost, peak_demand)


def simulate_package_savings(interval_df: pd.DataFrame, package: pd.Series, tariff, *,
                             specific_yield: float = 4.0,
                             has_battery: bool = True,
                             max_days: int = 45) -> dict | None:
    """คำนวณผลประหยัด/เดือนของ 'แพ็กนี้' บนโหลดจริงของลูกค้า

    คืน dict: {saving_month, baseline_month, with_system_month, note}
    หรือ None ถ้าคำนวณไม่ได้ (ไม่มี interval data / ไม่มีขนาดแผง)
    """
    if interval_df is None or not len(interval_df):
        return None
    panel_wp = package.get("panel_total_wp")
    if not panel_wp or pd.isna(panel_wp) or panel_wp <= 0:
        return None

    df = interval_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    # จำกัดจำนวนวันเพื่อความเร็ว (จำลองบนช่วงตัวแทนแล้ว normalize เป็นต่อเดือน)
    cutoff = df["timestamp"].iloc[0] + pd.Timedelta(days=max_days)
    df = df[df["timestamp"] < cutoff].reset_index(drop=True)
    if not len(df):
        return None

    dt = _infer_dt_hours(df)
    n_days = max(1, df["timestamp"].dt.date.nunique())

    sim = _inject_solar(df, panel_wp, specific_yield)
    ts = list(sim["timestamp"])

    # ---- baseline: ไม่มีระบบเลย ซื้อไฟทั้งหมดจาก grid ----
    baseline_grid = (sim["load_kw"] * dt).tolist()
    baseline_bill = _monthly_bill(ts, baseline_grid, tariff, dt, n_days)

    # ---- with system ----
    batt_kwh = package.get("battery_total_kwh")
    use_batt = bool(has_battery and batt_kwh and not pd.isna(batt_kwh) and batt_kwh > 0)

    if not use_batt:
        # โซลาร์อย่างเดียว: grid = (load - solar) ที่เหลือ
        solaronly_grid = ((sim["load_kw"] - sim["solar_kw"]).clip(lower=0) * dt).tolist()
        system_bill = _monthly_bill(ts, solaronly_grid, tariff, dt, n_days)
        note = "จำลองโซลาร์อย่างเดียวบนโหลดจริง (rule-based)"
    else:
        inv_kw = package.get("inverter_total_kw")
        inv_kw = float(inv_kw) if inv_kw and not pd.isna(inv_kw) else 5.0
        battery = Battery(capacity_kwh=float(batt_kwh),
                          max_charge_kw=inv_kw, max_discharge_kw=inv_kw)
        grid_series = []
        for _, day in sim.groupby(sim["timestamp"].dt.date):
            disp = rule_based_dispatch(day.sort_values("timestamp"), battery, tariff)
            grid_series.append(disp[["timestamp", "p_grid_buy"]])
        gs = pd.concat(grid_series).sort_values("timestamp")
        system_bill = _monthly_bill(list(gs["timestamp"]), gs["p_grid_buy"].tolist(),
                                    tariff, dt, n_days)
        note = "จำลองโซลาร์+แบต บนโหลดจริง (rule-based dispatch)"

    saving = baseline_bill - system_bill
    return {
        "saving_month": round(saving, 2),
        "baseline_month": round(baseline_bill, 2),
        "with_system_month": round(system_bill, 2),
        "n_days": n_days,
        "note": note,
    }
