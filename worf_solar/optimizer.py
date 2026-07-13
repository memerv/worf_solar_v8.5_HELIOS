"""
อัลกอริทึมตัดสินใจชาร์จ/จ่ายแบตเตอรี่ 2 แบบ สำหรับเปรียบเทียบกัน:

1. rule_based_dispatch  - เงื่อนไข IF-ELSE แบบที่ระบบทั่วไปในตลาดใช้ (baseline ที่เป็นธรรม)
2. optimize_dispatch    - MILP หาแผนที่ทำให้ค่าไฟรวมของวันนั้นต่ำสุด (ใช้ PuLP + CBC solver)

หมายเหตุสำคัญ: optimize_dispatch เวอร์ชันนี้ใช้ข้อมูลจริงของวันนั้นทั้งวัน (perfect
foresight) เพื่อ backtest ผลลัพธ์ย้อนหลัง เหมาะสำหรับพิสูจน์ concept ก่อน
ถ้าจะนำไปใช้ควบคุมแบบ real-time ต้องเปลี่ยนเป็น rolling-horizon + forecast
(ดูรายละเอียดในบลูปรินต์โปรเจค ข้อ 2 และ 4.2)

การแก้ไขในเวอร์ชันนี้ (เทียบกับเวอร์ชันแรก):
- เพิ่ม dt (Δt = ความยาวช่วงเวลาเป็นชั่วโมง) เข้าไปในสมการ energy balance, SOC dynamics
  และ objective ให้ตรงกับ blueprint ข้อ 3 — รองรับข้อมูลราย 15/30 นาทีได้ถูกต้อง
  (เดิมสมมติ Δt=1 เงียบๆ พอเปลี่ยน resolution ตัวเลขจะเพี้ยน)
- เพิ่มพารามิเตอร์ known_peak: ค่าพีค On-Peak สูงสุดที่เกิดขึ้นแล้วในเดือนนี้ (จากวันก่อนๆ)
  เพื่อให้ MILP "รู้" ว่า demand charge คิดจากพีคสะสมทั้งเดือน ไม่ใช่พีครายวันแยกกัน
  ทำให้ objective ที่ optimizer เห็น ตรงกับ metric ที่ simulator ใช้ตัดสินจริง
"""
import pandas as pd
import pulp


def _infer_dt_hours(day_df: pd.DataFrame) -> float:
    """เดา Δt (ชั่วโมง) จากระยะห่าง timestamp; ถ้าเดาไม่ได้ให้ใช้ 1.0"""
    ts = pd.to_datetime(day_df["timestamp"]).sort_values().reset_index(drop=True)
    if len(ts) < 2:
        return 1.0
    delta = (ts.iloc[1] - ts.iloc[0]).total_seconds() / 3600.0
    return delta if delta > 0 else 1.0


def rule_based_dispatch(day_df: pd.DataFrame, battery, tariff) -> pd.DataFrame:
    """
    Rule-based baseline (ปรับให้ fair ไม่ใช่ straw-man):
    - แดดมี -> จ่าย load ก่อน เหลือค่อยชาร์จแบต
    - แดดไม่พอ + On-Peak + แบตมีของ -> ดึงแบตมาใช้ก่อนซื้อไฟ
    - Off-Peak -> ชาร์จเสริมจาก grid แค่พอประมาณ (เผื่อพรุ่งนี้แดดไม่พอ) ไม่ชาร์จเต็ม 100% ทุกคืน

    หมายเหตุ: charge/discharge ในตารางผลลัพธ์เก็บเป็น "พลังงาน (kWh) ต่อช่วงเวลา"
    เพื่อให้รวม throughput ได้ตรง ส่วน grid_buy ก็เป็น kWh ต่อช่วงเวลาเช่นกัน
    """
    dt = _infer_dt_hours(day_df)
    soc = battery.soc_min
    records = []

    for _, row in day_df.iterrows():
        ts, solar, load = row["timestamp"], row["solar_kw"], row["load_kw"]
        on_peak = tariff.is_on_peak(ts)

        # แปลงกำลัง (kW) เป็นพลังงานต่อช่วง (kWh) ด้วย dt
        solar_e = solar * dt
        load_e = load * dt
        max_charge_e = battery.max_charge_kw * dt
        max_discharge_e = battery.max_discharge_kw * dt

        net = solar_e - load_e
        charge = discharge = 0.0
        grid_buy = 0.0

        if net >= 0:
            charge = min(net, max_charge_e, (battery.soc_max - soc) / battery.eta_c)
        else:
            deficit = -net
            if on_peak:
                discharge = min(deficit, max_discharge_e, (soc - battery.soc_min) * battery.eta_d)
                grid_buy = deficit - discharge
            else:
                target_soc = 0.7 * battery.soc_max
                if soc < target_soc:
                    charge = min(max_charge_e, (target_soc - soc) / battery.eta_c)
                grid_buy = deficit

        soc = soc + charge * battery.eta_c - discharge / battery.eta_d
        soc = min(max(soc, battery.soc_min), battery.soc_max)

        records.append({
            "timestamp": ts,
            "solar_kw": solar,
            "load_kw": load,
            "p_charge": charge,        # kWh ต่อช่วง
            "p_discharge": discharge,  # kWh ต่อช่วง
            "p_grid_buy": grid_buy,    # kWh ต่อช่วง
            "soc": soc,
        })

    return pd.DataFrame(records)


def optimize_dispatch(day_df: pd.DataFrame, battery, tariff, initial_soc: float,
                      known_peak: float = 0.0) -> pd.DataFrame:
    """
    Smart optimizer: แก้ MILP หาแผนชาร์จ/จ่ายที่ทำให้ (ค่าพลังงาน + demand charge +
    ต้นทุนความเสื่อมแบต) ต่ำที่สุด

    known_peak: ค่าพีค On-Peak (kW) สูงสุดที่เกิดไปแล้วในเดือนนี้จากวันก่อนหน้า
                ใช้ผูกกับ d_peak เพื่อให้ optimizer คิด demand charge แบบสะสมทั้งเดือน
                (ค่า demand charge ที่ต้องจ่ายเพิ่มของวันนี้ = พีคใหม่ที่ทะลุ known_peak เท่านั้น)

    ผลลัพธ์ p_charge/p_discharge/p_grid_buy เก็บเป็น "พลังงาน (kWh) ต่อช่วงเวลา"
    """
    n = len(day_df)
    day_df = day_df.reset_index(drop=True)
    dt = _infer_dt_hours(day_df)

    prob = pulp.LpProblem("battery_dispatch", pulp.LpMinimize)

    # ตัวแปรกำลัง (kW)
    p_charge = [pulp.LpVariable(f"charge_{t}", lowBound=0) for t in range(n)]
    p_discharge = [pulp.LpVariable(f"discharge_{t}", lowBound=0) for t in range(n)]
    p_grid_buy = [pulp.LpVariable(f"grid_{t}", lowBound=0) for t in range(n)]
    p_curtail = [pulp.LpVariable(f"curtail_{t}", lowBound=0) for t in range(n)]
    soc = [pulp.LpVariable(f"soc_{t}", lowBound=battery.soc_min, upBound=battery.soc_max) for t in range(n)]
    is_charging = [pulp.LpVariable(f"mode_{t}", cat="Binary") for t in range(n)]

    # d_peak = พีค On-Peak สะสมของทั้งเดือน (kW) ต้องไม่ต่ำกว่าพีคที่เคยเกิดแล้ว
    d_peak = pulp.LpVariable("d_peak", lowBound=known_peak)

    # ค่าพลังงาน: ราคา (บาท/kWh) * กำลัง (kW) * dt (ชม.) = บาท
    energy_cost = pulp.lpSum(
        tariff.energy_price(day_df.iloc[t]["timestamp"]) * p_grid_buy[t] * dt for t in range(n)
    )
    # demand charge คิดเฉพาะส่วนที่ "เพิ่มขึ้น" จากพีคเดิมของเดือน
    incremental_demand_cost = tariff.demand_charge_rate * (d_peak - known_peak)

    # หมายเหตุ: ตัดต้นทุนความเสื่อมแบตออกจาก objective ตามที่ผู้ใช้กำหนด
    # (ผลข้างเคียง: optimizer จะ cycle แบตอิสระขึ้น ตัวเลขประหยัดจะดูดีขึ้นเล็กน้อย
    #  แต่ไม่สะท้อนการสึกหรอของแบตในระยะยาว — ระวังตอนอ้างอิงตัวเลขเชิงพาณิชย์)
    prob += energy_cost + incremental_demand_cost

    for t in range(n):
        row = day_df.iloc[t]
        solar, load = row["solar_kw"], row["load_kw"]

        # (1) Energy balance (kW): solar + discharge + grid = load + charge + curtail
        prob += (solar + p_discharge[t] + p_grid_buy[t] == load + p_charge[t] + p_curtail[t])

        # (2) SOC dynamics (kWh): คูณ dt แปลงกำลังเป็นพลังงาน
        prev_soc = initial_soc if t == 0 else soc[t - 1]
        prob += soc[t] == prev_soc + battery.eta_c * p_charge[t] * dt - (p_discharge[t] * dt) / battery.eta_d

        # (4) ห้ามชาร์จ-จ่ายพร้อมกัน + จำกัดกำลังตาม inverter
        prob += p_charge[t] <= battery.max_charge_kw * is_charging[t]
        prob += p_discharge[t] <= battery.max_discharge_kw * (1 - is_charging[t])

        # (6) Demand charge linking เฉพาะช่วง On-Peak
        if tariff.is_on_peak(row["timestamp"]):
            prob += d_peak >= p_grid_buy[t]

    # (7) Terminal condition: กันโกงปล่อยแบตหมดตอนจบวัน
    prob += soc[n - 1] >= initial_soc * 0.9

    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)

    records = []
    for t in range(n):
        # แปลงกำลัง (kW) เป็นพลังงานต่อช่วง (kWh) ด้วย dt ให้สอดคล้องกับ rule_based
        pc = (p_charge[t].value() or 0.0) * dt
        pd_ = (p_discharge[t].value() or 0.0) * dt
        pg = (p_grid_buy[t].value() or 0.0) * dt
        records.append({
            "timestamp": day_df.iloc[t]["timestamp"],
            "solar_kw": day_df.iloc[t]["solar_kw"],
            "load_kw": day_df.iloc[t]["load_kw"],
            "p_charge": pc,
            "p_discharge": pd_,
            "p_grid_buy": pg,
            "soc": soc[t].value() or 0.0,
        })
    return pd.DataFrame(records)
