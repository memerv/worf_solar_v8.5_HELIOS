"""
โมดูลคำนวณตัวชี้วัดทางการเงินสำหรับเอกสารขาย: Payback Period, NPV, IRR

ข้อควรระวัง (ต้องแจ้งทีมขาย/ลูกค้าเสมอ):
- ตัวเลขจากที่นี่คำนวณจาก "ผลประหยัดจำลอง" ซึ่งเป็นผลลัพธ์เชิงทฤษฎี
  (Smart Optimizer เป็น perfect-foresight) ของจริงจะต่ำกว่านี้เล็กน้อย
- ไม่รวมต้นทุนเปลี่ยนแบตเตอรี่ระหว่างอายุโครงการ (ตัดออกตามที่ผู้กำหนดสเปคสั่ง)
  ถ้าอายุโครงการยาวกว่าอายุแบต ตัวเลข NPV/IRR จะดูดีกว่าความเป็นจริง
- ควรให้ทีมการเงิน sanity-check ก่อนใช้ผูกพันสัญญา
"""


def simple_payback(capex: float, annual_savings: float) -> float:
    """ระยะเวลาคืนทุนแบบง่าย (ปี) = เงินลงทุน / ผลประหยัดต่อปี"""
    if annual_savings <= 0:
        return float("inf")
    return capex / annual_savings


def cashflows(capex: float, annual_savings: float, years: int,
              escalation: float = 0.0) -> list:
    """
    กระแสเงินสดรายปี: ปี 0 = -capex, ปี 1..N = ผลประหยัด (โตปีละ escalation)
    escalation เช่น 0.03 = ค่าไฟขึ้น 3%/ปี ทำให้ผลประหยัดโตตาม
    """
    flows = [-capex]
    s = annual_savings
    for _ in range(years):
        flows.append(s)
        s *= (1 + escalation)
    return flows


def npv(capex: float, annual_savings: float, years: int,
        discount_rate: float, escalation: float = 0.0) -> float:
    """มูลค่าปัจจุบันสุทธิ (บาท)"""
    flows = cashflows(capex, annual_savings, years, escalation)
    return sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(flows))


def irr(capex: float, annual_savings: float, years: int,
        escalation: float = 0.0) -> float:
    """
    อัตราผลตอบแทนภายใน (ทศนิยม เช่น 0.12 = 12%) หาโดย bisection
    คืน float('nan') ถ้าหาไม่ได้ (เช่น ผลประหยัดติดลบ)
    """
    flows = cashflows(capex, annual_savings, years, escalation)

    def npv_at(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))

    lo, hi = -0.99, 10.0
    f_lo, f_hi = npv_at(lo), npv_at(hi)
    if f_lo * f_hi > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv_at(mid)
        if abs(f_mid) < 1e-6:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def discounted_payback(capex: float, annual_savings: float, years: int,
                       discount_rate: float, escalation: float = 0.0) -> float:
    """ระยะคืนทุนแบบคิดลด (ปี) — คืน inf ถ้าไม่คืนทุนภายใน years"""
    flows = cashflows(capex, annual_savings, years, escalation)
    cum = flows[0]
    for t in range(1, len(flows)):
        pv = flows[t] / (1 + discount_rate) ** t
        if cum + pv >= 0:
            return (t - 1) + (-cum / pv)  # interpolate ภายในปี
        cum += pv
    return float("inf")
