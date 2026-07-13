"""
นิยามระบบแบตเตอรี่และพารามิเตอร์ทางกายภาพ
"""
from dataclasses import dataclass


@dataclass
class Battery:
    capacity_kwh: float = 10.0          # ความจุแบตทั้งหมด (kWh)
    soc_min_pct: float = 0.2            # ห้ามต่ำกว่านี้ (ถนอมแบต)
    soc_max_pct: float = 1.0            # ห้ามเกินนี้
    max_charge_kw: float = 5.0          # กำลังชาร์จสูงสุด (จำกัดโดย inverter)
    max_discharge_kw: float = 5.0       # กำลังจ่ายสูงสุด (จำกัดโดย inverter)
    round_trip_efficiency: float = 0.9  # ประสิทธิภาพรวมไป-กลับ (ชาร์จเข้า 100 จ่ายออกได้ ~90)

    @property
    def soc_min(self) -> float:
        return self.soc_min_pct * self.capacity_kwh

    @property
    def soc_max(self) -> float:
        return self.soc_max_pct * self.capacity_kwh

    @property
    def eta_c(self) -> float:
        """ประสิทธิภาพขาชาร์จ (แยกจากขาจ่ายโดยประมาณ = sqrt ของ round-trip)"""
        return self.round_trip_efficiency ** 0.5

    @property
    def eta_d(self) -> float:
        """ประสิทธิภาพขาจ่าย"""
        return self.round_trip_efficiency ** 0.5
