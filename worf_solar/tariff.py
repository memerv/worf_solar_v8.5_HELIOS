"""
โมดูลคำนวณอัตราค่าไฟฟ้าแบบ TOU ของ PEA
รวม On-Peak / Off-Peak, ค่า Ft, ค่าความต้องการพลังไฟฟ้า (Demand Charge), VAT

หมายเหตุ: ตัวเลขเริ่มต้นเป็นตัวอย่างเท่านั้น กรุณาปรับให้ตรงกับประกาศ กกพ./PEA
ฉบับล่าสุด และตามประเภทผู้ใช้ไฟฟ้าจริง (บ้านอยู่อาศัย / ธุรกิจขนาดกลาง-ใหญ่ ฯลฯ)
"""
from dataclasses import dataclass
from datetime import datetime, time


@dataclass
class TariffModel:
    on_peak_rate: float = 5.7982        # บาท/หน่วย (พลังงานล้วน ไม่รวม Ft)
    off_peak_rate: float = 2.6369       # บาท/หน่วย
    ft_rate: float = 0.0                # บาท/หน่วย (กรอกค่า Ft ปัจจุบันตามประกาศล่าสุด)
    demand_charge_rate: float = 132.93  # บาท/kW/เดือน (ตัวอย่าง TOU กิจการขนาดกลาง)
    service_charge: float = 312.24      # บาท/เดือน
    vat_rate: float = 0.07
    # ---- ช่วงเวลา On-Peak ปรับได้ (แก้ #8: เดิม hardcode 09:00-22:00 จ-ศ) ----
    on_peak_start_hour: int = 9         # ชั่วโมงเริ่ม On-Peak (0-23)
    on_peak_end_hour: int = 22          # ชั่วโมงสิ้นสุด On-Peak (exclusive, 1-24)
    on_peak_weekdays_only: bool = True  # True = TOU (จ-ศ) ; False = คิด On-Peak ทุกวัน

    def is_on_peak(self, ts: datetime) -> bool:
        """
        On-Peak ตามช่วงเวลาที่ตั้งค่าไว้ (ดีฟอลต์ จันทร์-ศุกร์ 09:00-22:00 น.)
        ปรับ on_peak_start_hour / on_peak_end_hour / on_peak_weekdays_only ได้จาก UI
        เพื่อรองรับมิเตอร์/เขตที่ช่วงเวลาต่างกัน (PEA vs MEA, TOU vs TOD)

        ข้อจำกัด: ยังไม่รวมปฏิทินวันหยุดราชการ ถ้าใช้งานจริงควรเพิ่ม holiday calendar
        (เช่นไลบรารี `holidays` หรือปฏิทิน Off-Peak ที่การไฟฟ้าประกาศทุกปี)
        """
        if self.on_peak_weekdays_only and ts.weekday() >= 5:  # เสาร์=5 อาทิตย์=6
            return False
        h = ts.hour
        start, end = self.on_peak_start_hour, self.on_peak_end_hour
        if start <= end:
            return start <= h < end
        # กรณีช่วงคร่อมเที่ยงคืน (เช่น 22-6) เผื่ออนาคต
        return h >= start or h < end

    def energy_price(self, ts: datetime) -> float:
        """ราคาพลังงานต่อหน่วย ณ เวลานั้น (รวม Ft แล้ว ยังไม่รวม VAT)"""
        base = self.on_peak_rate if self.is_on_peak(ts) else self.off_peak_rate
        return base + self.ft_rate

    def monthly_bill(self, energy_cost: float, peak_demand_kw: float) -> float:
        """
        คำนวณบิลรวม = ค่าพลังงาน + ค่าความต้องการพลังไฟฟ้า + ค่าบริการ แล้วบวก VAT
        """
        subtotal = energy_cost + (self.demand_charge_rate * peak_demand_kw) + self.service_charge
        return subtotal * (1 + self.vat_rate)
