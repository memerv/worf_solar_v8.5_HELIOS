"""
Simulation engine: รันทั้ง 2 อัลกอริทึม (rule-based, smart optimizer) เทียบกับ
กรณีไม่มีแบตเลย แล้วสรุปเป็นตารางเปรียบเทียบ

การแก้ไขในเวอร์ชันนี้:
- รองรับ Δt (ราย 15/30/60 นาที) โดยคำนวณจากระยะห่าง timestamp
- p_charge / p_discharge / p_grid_buy ในตาราง dispatch ทุกวิธี = "พลังงาน (kWh) ต่อช่วง"
  (ตรงกันหมดทั้ง no-batt / rule / smart) ทำให้ energy cost = ราคา * kWh ตรงไปตรงมา
- Peak demand คิดเป็น "กำลัง (kW)" = พลังงานต่อช่วง / dt แล้วหา max ข้ามทั้งเดือน
- ส่ง known_peak (พีค On-Peak สะสม) เข้า optimizer ทีละวัน เพื่อให้ MILP คิด
  demand charge แบบทั้งเดือน ไม่ใช่รายวันแยกกัน (แก้ bug เดิม)
"""
import pandas as pd
from optimizer import rule_based_dispatch, optimize_dispatch, _infer_dt_hours


def _cost_from_dispatch(dispatch_df: pd.DataFrame, tariff, dt: float) -> dict:
    # energy_cost: p_grid_buy เป็น kWh ต่อช่วงอยู่แล้ว -> ราคา(บาท/kWh) * kWh
    energy_cost = sum(
        tariff.energy_price(row["timestamp"]) * row["p_grid_buy"]
        for _, row in dispatch_df.iterrows()
    )

    # peak demand (kW) = พลังงานต่อช่วง (kWh) / dt ; คิดเฉพาะช่วง On-Peak
    on_peak_mask = dispatch_df["timestamp"].apply(tariff.is_on_peak)
    peak_energy = dispatch_df.loc[on_peak_mask, "p_grid_buy"]
    peak_demand = float(peak_energy.max() / dt) if len(peak_energy) else 0.0

    total_bill = tariff.monthly_bill(energy_cost, peak_demand)
    battery_throughput = float(dispatch_df["p_charge"].sum() + dispatch_df["p_discharge"].sum())

    return {
        "ค่าพลังงาน (บาท)": round(energy_cost, 2),
        "Peak Demand (kW)": round(peak_demand, 2),
        "Battery Throughput (kWh)": round(battery_throughput, 2),
        "total_bill": round(total_bill, 2),
    }


def run_full_simulation(data: pd.DataFrame, battery, tariff) -> dict:
    """
    data: DataFrame มาตรฐานทั้งชุด (หลายวัน) คอลัมน์ timestamp, solar_kw, load_kw
    คืนค่า: dict ที่มี DataFrame ผลลัพธ์รายช่วงของแต่ละวิธี + ตารางสรุปเปรียบเทียบ

    แก้ #7: running_peak (พีค On-Peak สะสม) รีเซ็ตทุกต้นเดือน — เดิมสะสมข้ามเดือน
    ทำให้ demand charge ของเดือนที่ 2 เป็นต้นไปคำนวณเกินจริง นอกจากนี้ยังคืน
    ตารางสรุป "เฉลี่ยต่อเดือน" (หารด้วยจำนวนเดือนจริง) ไม่ใช่ผลรวมทั้งช่วงที่ติดป้ายว่าต่อเดือน
    """
    data = data.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["date"] = data["timestamp"].dt.date
    data["_month"] = data["timestamp"].dt.to_period("M")
    dt = _infer_dt_hours(data)

    no_batt_records, rule_records, smart_records = [], [], []
    soc_smart = battery.soc_min

    # วนทีละเดือน -> รีเซ็ต running_peak และ SOC เริ่มต้นทุกต้นเดือน
    for _month, month_df in data.groupby("_month"):
        running_peak = 0.0  # พีค On-Peak สะสม "ภายในเดือนนี้เท่านั้น"
        soc_smart = battery.soc_min

        for _, day_df in month_df.groupby("date"):
            day_df = day_df.sort_values("timestamp").reset_index(drop=True)

            # ---- ไม่มีแบต ----
            no_batt = day_df[["timestamp", "solar_kw", "load_kw"]].copy()
            no_batt["p_grid_buy"] = (no_batt["load_kw"] - no_batt["solar_kw"]).clip(lower=0) * dt
            no_batt["p_charge"] = 0.0
            no_batt["p_discharge"] = 0.0
            no_batt["soc"] = 0.0
            no_batt_records.append(no_batt)

            # ---- rule-based ----
            rule_records.append(rule_based_dispatch(day_df, battery, tariff))

            # ---- smart (MILP) พร้อมส่งพีคสะสม "ของเดือนนี้" เข้าไป ----
            smart_df = optimize_dispatch(day_df, battery, tariff,
                                         initial_soc=soc_smart, known_peak=running_peak)
            soc_smart = float(smart_df.iloc[-1]["soc"])

            smart_on_peak = smart_df["timestamp"].apply(tariff.is_on_peak)
            day_peak_energy = smart_df.loc[smart_on_peak, "p_grid_buy"]
            if len(day_peak_energy):
                running_peak = max(running_peak, float(day_peak_energy.max() / dt))

            smart_records.append(smart_df)

    no_batt_all = pd.concat(no_batt_records, ignore_index=True)
    rule_all = pd.concat(rule_records, ignore_index=True)
    smart_all = pd.concat(smart_records, ignore_index=True)

    # สรุปแบบ "เฉลี่ยต่อเดือน" (คิด demand charge รายเดือนแยกกันแล้วเฉลี่ย)
    n_months = max(1, data["_month"].nunique())

    def _per_month(dispatch_all):
        agg = _cost_from_dispatch_monthly(dispatch_all, tariff, dt, data)
        return agg

    summary = pd.DataFrame([
        {"ระบบ": "ไม่มีแบตเตอรี่", **_per_month(no_batt_all)},
        {"ระบบ": "Hybrid Rule-Based", **_per_month(rule_all)},
        {"ระบบ": "Hybrid Smart (MILP)", **_per_month(smart_all)},
    ])
    summary = summary.rename(columns={"total_bill": "ค่าไฟรวม/เดือน (บาท, รวม VAT)"})

    return {
        "no_battery": no_batt_all,
        "rule_based": rule_all,
        "smart": smart_all,
        "summary": summary,
        "n_months": n_months,
    }


def _cost_from_dispatch_monthly(dispatch_df: pd.DataFrame, tariff, dt: float,
                                data_with_month: pd.DataFrame) -> dict:
    """คิดบิลรายเดือนแยกกัน (demand charge = พีคของ 'เดือนนั้น') แล้วเฉลี่ยต่อเดือน
    แก้ #7 ต่อเนื่อง: ไม่เอาพีคทั้งช่วงมาคิดครั้งเดียวแล้วติดป้ายว่า 'ต่อเดือน'
    """
    df = dispatch_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["_month"] = df["timestamp"].dt.to_period("M")

    energy_costs, peaks, bills, throughputs = [], [], [], []
    for _m, mdf in df.groupby("_month"):
        energy_cost = sum(tariff.energy_price(r["timestamp"]) * r["p_grid_buy"]
                          for _, r in mdf.iterrows())
        on_peak_mask = mdf["timestamp"].apply(tariff.is_on_peak)
        peak_energy = mdf.loc[on_peak_mask, "p_grid_buy"]
        peak_demand = float(peak_energy.max() / dt) if len(peak_energy) else 0.0
        energy_costs.append(energy_cost)
        peaks.append(peak_demand)
        bills.append(tariff.monthly_bill(energy_cost, peak_demand))
        throughputs.append(float(mdf["p_charge"].sum() + mdf["p_discharge"].sum()))

    n = max(1, len(bills))
    return {
        "ค่าพลังงาน (บาท)": round(sum(energy_costs) / n, 2),
        "Peak Demand (kW)": round(max(peaks) if peaks else 0.0, 2),
        "Battery Throughput (kWh)": round(sum(throughputs) / n, 2),
        "total_bill": round(sum(bills) / n, 2),
    }
