"""
โมดูลฐานข้อมูลแพ็กเกจโซลาร์+แบตเตอรี่ (Package Catalog)

อ่านไฟล์ Excel catalog ที่มีโครงสร้างคอลัมน์แบบ:
Period, Pack ID, Package Code, Type, Phase, Solar panel (brand/Model/Wp/QTY),
Optimizer, Inverter (brand/model/kW/QTY), Battery (brand/model/kWh/QTY),
Catalog price (VAT), การรับประกันต่างๆ, ผลประหยัด, ระยะคืนทุน ฯลฯ

ชื่อคอลัมน์จริงมักมีขึ้นบรรทัด/ช่องว่าง/เครื่องหมายคำพูดปนมา
จึงใช้ fuzzy matching: normalize ชื่อคอลัมน์ก่อนแล้วค้นหาด้วย keyword
"""
import pandas as pd


# คอลัมน์ที่ "ปลอดภัยให้ลูกค้าเห็น" — Pro price / margin ไม่อยู่ในนี้ จึงไม่มีวันโผล่
CUSTOMER_SAFE_COLUMNS = [
    "package_code", "vendor", "phase",
    "panel_brand", "panel_model", "panel_total_wp", "panel_qty",
    "inverter_brand", "inverter_model", "inverter_total_kw",
    "battery_brand", "battery_model", "battery_total_kwh",
    "catalog_price",
    "warranty_panel_product", "warranty_panel_power",
    "warranty_inverter", "warranty_battery", "warranty_install",
    "fire_insurance", "maintenance", "install_area_sqm",
    "claimed_saving_month", "claimed_saving_year", "claimed_payback_years",
    "service_area",
]

# ชื่อไทยอ่านง่ายสำหรับแสดงผล/ส่งลูกค้า
COLUMN_LABELS_TH = {
    "package_code": "รหัสแพ็กเกจ",
    "vendor": "ผู้ให้บริการ",
    "phase": "ระบบไฟ",
    "panel_brand": "ยี่ห้อแผง",
    "panel_model": "รุ่นแผง",
    "panel_total_wp": "กำลังแผงรวม (Wp)",
    "panel_qty": "จำนวนแผง",
    "inverter_brand": "ยี่ห้ออินเวอร์เตอร์",
    "inverter_model": "รุ่นอินเวอร์เตอร์",
    "inverter_total_kw": "ขนาดอินเวอร์เตอร์ (kW)",
    "battery_brand": "ยี่ห้อแบตเตอรี่",
    "battery_model": "รุ่นแบตเตอรี่",
    "battery_total_kwh": "ความจุแบต (kWh)",
    "catalog_price": "ราคาลงทุน (บาท)",
    "warranty_panel_product": "ประกันแผง-ตัวสินค้า (ปี)",
    "warranty_panel_power": "ประกันแผง-กำลังผลิต (ปี)",
    "warranty_inverter": "ประกันอินเวอร์เตอร์ (ปี)",
    "warranty_battery": "ประกันแบตเตอรี่ (ปี)",
    "warranty_install": "ประกันงานติดตั้ง (ปี)",
    "fire_insurance": "ประกันอัคคีภัย (ปี)",
    "maintenance": "บำรุงรักษา (ปี/ครั้ง)",
    "install_area_sqm": "พื้นที่ติดตั้ง (ตร.ม.)",
    "claimed_saving_month": "ประหยัด/เดือน (บาท)",
    "claimed_saving_year": "ประหยัด/ปี (บาท)",
    "claimed_payback_years": "คืนทุน (ปี)",
    "service_area": "พื้นที่ให้บริการ",
}


def customer_view(catalog: pd.DataFrame, rename_thai: bool = True) -> pd.DataFrame:
    """คืน DataFrame เฉพาะคอลัมน์ที่ปลอดภัยให้ลูกค้าเห็น (ตัด Pro price/margin ออก)"""
    cols = [c for c in CUSTOMER_SAFE_COLUMNS if c in catalog.columns]
    view = catalog[cols].copy()
    if rename_thai:
        view = view.rename(columns={c: COLUMN_LABELS_TH.get(c, c) for c in cols})
    return view


_INVISIBLE_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0", "\u2060"]


def _norm(name: str) -> str:
    s = str(name)
    for ch in _INVISIBLE_CHARS:          # แก้ #9: ลบอักขระซ่อนก่อน ไม่งั้น match พลาดเงียบๆ
        s = s.replace(ch, "")
    s = s.strip().lower()
    for ch in ['"', "'", "\n", "\r", "\t", "(", ")", "-", "_", "."]:
        s = s.replace(ch, " ")
    return " ".join(s.split())


# ชื่อมาตรฐานภายใน -> รายการ keyword ที่ต้องพบ "ครบทุกคำ" ในชื่อคอลัมน์ (หลัง normalize)
# เรียงจากเฉพาะเจาะจงมาก -> น้อย เพื่อไม่ให้จับผิดคอลัมน์
_CATALOG_FIELDS = [
    ("pack_id",           [["pack id"]]),
    ("package_code",      [["package code"]]),
    ("period",            [["period"]]),
    ("vendor",            [["vendor"]]),
    ("type",              [["type"]]),
    ("phase",             [["phase"]]),
    ("panel_brand",       [["solar panel", "brand"]]),
    ("panel_model",       [["solar panel", "model"]]),
    ("panel_wp",          [["solar panel", "wp"]]),
    ("panel_qty",         [["solar panel", "qty"]]),
    ("panel_total_wp",    [["solar panel", "total", "wp"], ["total", "wp"]]),
    ("inverter_brand",    [["inverter", "brand"]]),
    ("inverter_model",    [["inverter", "model"]]),
    ("inverter_kw",       [["inverter", "kw"]]),
    ("inverter_qty",      [["inverter", "qty"]]),
    ("inverter_total_kw", [["inverter total"], ["inverter", "total", "kw"]]),
    ("battery_brand",     [["battery", "brand"]]),
    ("battery_model",     [["battery", "model"]]),
    ("battery_kwh",       [["battery", "kwh"]]),
    ("battery_qty",       [["battery", "qty"]]),
    ("battery_total_kwh", [["battery total"], ["battery", "total", "kwh"]]),
    ("catalog_price",     [["catalog price"]]),
    ("warranty_panel_product", [["แผงโซล", "product"]]),
    ("warranty_panel_power",   [["แผงโซล", "power"]]),
    ("warranty_inverter",      [["inverter", "warranty"], ["inverter", "ปี"]]),
    ("warranty_battery",       [["แบตเตอรี่", "warranty"], ["แบตเตอรี่", "ปี"]]),
    ("warranty_install",       [["การรับประกัน การติดตั้ง"], ["ติดตั้ง", "ปี"]]),
    ("fire_insurance",         [["อัคคีภัย"]]),
    ("maintenance",            [["การบำรุงรักษา"], ["บำรุงรักษา"]]),
    ("install_area_sqm",       [["พื้นที่ติดตั้ง"]]),
    ("claimed_saving_month",   [["ผลประหยัดต่อ", "เดือน"], ["ผลประหยัด", "เดือน"]]),
    ("claimed_saving_year",    [["ผลประหยัด ปี"], ["ผลประหยัด", "ปี", "บาท"]]),
    ("claimed_payback_years",  [["ระยะเวลาคืนทุน"]]),
    ("price_per_wp",           [["price thb", "wp"], ["cat price", "wp"], ["price", "wp"]]),
    ("expand_inverter",        [["invertor", "ขนาน"], ["inverter", "ขนาน"]]),
    ("expand_battery",         [["แบตเตอรี่", "เพิ่ม"], ["ติดแบต", "เพิ่ม"]]),
    ("service_area",           [["พื้นที่ที่ให้บริการ"], ["พื้นที่การให้บริการ"]]),
    ("notes",                  [["หมายเหตุ"]]),
]

# คอลัมน์ตัวเลข ที่ต้องแปลงและล้าง comma ออก
_NUMERIC_FIELDS = [
    "panel_wp", "panel_qty", "panel_total_wp", "inverter_kw", "inverter_qty",
    "inverter_total_kw", "battery_kwh", "battery_qty", "battery_total_kwh",
    "catalog_price", "install_area_sqm", "claimed_saving_month",
    "claimed_saving_year", "claimed_payback_years", "price_per_wp",
]


def parse_package_catalog(file) -> pd.DataFrame:
    """อ่านไฟล์ Excel catalog แล้วคืน DataFrame ชื่อคอลัมน์มาตรฐาน"""
    raw = pd.read_excel(file, engine="openpyxl")
    norm_cols = {c: _norm(c) for c in raw.columns}

    out = pd.DataFrame(index=raw.index)
    matched = set()
    std_names = {f[0] for f in _CATALOG_FIELDS}

    # รอบแรก: คอลัมน์ที่ชื่อตรงกับชื่อมาตรฐานอยู่แล้ว (เช่นไฟล์ที่ export จากระบบนี้เอง)
    for c in raw.columns:
        if str(c).strip() in std_names:
            out[str(c).strip()] = raw[c]
            matched.add(c)

    for std_name, keyword_groups in _CATALOG_FIELDS:
        if std_name in out.columns:
            continue
        for kws in keyword_groups:
            hit = None
            for c, nc in norm_cols.items():
                if c in matched:
                    continue
                if all(kw in nc for kw in kws):
                    hit = c
                    break
            if hit is not None:
                out[std_name] = raw[hit]
                matched.add(hit)
                break

    if "pack_id" not in out.columns and "package_code" not in out.columns:
        raise ValueError(
            "ไม่พบคอลัมน์ Pack ID หรือ Package Code ในไฟล์ catalog\n"
            f"คอลัมน์ที่เจอ: {list(raw.columns)}"
        )

    # ล้างตัวเลข: ตัด comma / ช่องว่าง / เครื่องหมาย -
    for f in _NUMERIC_FIELDS:
        if f in out.columns:
            out[f] = (
                out[f].astype(str)
                .str.replace(",", "", regex=False)
                .str.strip()
                .replace({"-": None, "": None, "nan": None})
            )
            out[f] = pd.to_numeric(out[f], errors="coerce")

    # ตัดแถวว่าง (ไม่มีทั้ง pack_id และ package_code)
    key_cols = [c for c in ("pack_id", "package_code") if c in out.columns]
    out = out.dropna(subset=key_cols, how="all").reset_index(drop=True)
    return out


def required_system_wp(avg_kwh_month: float, specific_yield: float = 4.0) -> float:
    """ประเมินกำลังแผงที่ 'เหมาะ' กับการใช้ไฟของลูกค้า (Wp)
    avg_kwh_month : หน่วยไฟเฉลี่ยต่อเดือน (kWh)
    specific_yield: พลังงานที่ผลิตได้ต่อ 1 kWp ต่อวัน (kWh/kWp/วัน) — ไทยเฉลี่ย ~3.5-4.5
    สูตร: kWp ที่ต้องการ = (kWh/วัน) / specific_yield ; Wp = kWp*1000
    ใช้แทนตรรกะเดิม (#2) ที่จับคู่ 'ผลประหยัดที่เคลม' กับ 'ค่าไฟทั้งบิล' แบบ 1:1
    ซึ่งไม่มีฐานทางฟิสิกส์รองรับ
    """
    if not avg_kwh_month or avg_kwh_month <= 0:
        return 0.0
    daily_kwh = avg_kwh_month / 30.0
    return (daily_kwh / max(0.1, specific_yield)) * 1000.0


def recommend_packages(catalog: pd.DataFrame, *, want_battery: bool,
                       batt_min_kwh: float, batt_max_kwh: float,
                       phase_pref: str = "ทั้งหมด",
                       avg_kwh_month: float = 0.0,
                       avail_area_sqm: float | None = None,
                       specific_yield: float = 4.0,
                       max_show: int = 10) -> dict:
    """คัดกรอง + จัดอันดับแพ็กเกจให้เหมาะกับลูกค้า (แยก business logic ออกจาก app.py — แก้ #14)

    คืน dict:
      top        : DataFrame แพ็กที่แนะนำ (เรียงตามความเหมาะ)
      dropped    : list ของ (รหัสแพ็ก, เหตุผลที่ถูกตัด)  (แก้ #10)
      warnings   : list[str] คำเตือนภาพรวม
      target_wp  : กำลังแผงเป้าหมายที่ใช้จับคู่ (Wp) หรือ None
    """
    work = catalog.copy()
    dropped: list[tuple] = []
    warnings: list[str] = []

    def _code(row):
        return str(row.get("package_code") or row.get("pack_id") or "?")

    # ---- กรองแบตเตอรี่ ----
    if "battery_total_kwh" in work.columns:
        b = work["battery_total_kwh"].fillna(0)
        if want_battery:
            mask = (b > 0) & b.between(batt_min_kwh, batt_max_kwh)
            for _, r in work[~mask].iterrows():
                dropped.append((_code(r), "ความจุแบตไม่อยู่ในช่วงที่ต้องการ"))
            work = work[mask]
        else:
            mask = (b == 0)
            for _, r in work[~mask].iterrows():
                dropped.append((_code(r), "ลูกค้าไม่เอาแบต แต่แพ็กนี้มีแบต"))
            work = work[mask]

    # ---- กรองระบบไฟ (phase) ----
    if phase_pref != "ทั้งหมด" and "phase" in work.columns:
        pmask = work["phase"].astype(str).str.contains(phase_pref.split()[0], na=False)
        for _, r in work[~pmask].iterrows():
            dropped.append((_code(r), f"ระบบไฟไม่ตรง ({phase_pref})"))
        work = work[pmask]

    # ---- กรองพื้นที่ติดตั้ง (แก้ #3) ----
    if avail_area_sqm and avail_area_sqm > 0 and "install_area_sqm" in work.columns:
        amask = work["install_area_sqm"].fillna(0) <= avail_area_sqm
        # แพ็กที่ไม่ระบุพื้นที่ (NaN -> fillna 0) จะผ่าน ไม่ตัดทิ้งเพราะข้อมูลขาด
        amask = amask | work["install_area_sqm"].isna()
        for _, r in work[~amask].iterrows():
            dropped.append((_code(r), f"ต้องใช้พื้นที่ {r.get('install_area_sqm')} ตร.ม. "
                                      f"เกินพื้นที่ที่มี ({avail_area_sqm:g} ตร.ม.)"))
        work = work[amask]

    if not len(work):
        warnings.append("ไม่พบแพ็กเกจที่ตรงเงื่อนไขลูกค้าเลย ลองผ่อนเงื่อนไข (แบต/ระบบไฟ/พื้นที่)")
        return {"top": work, "dropped": dropped, "warnings": warnings,
                "target_wp": None, "tiers": {}}

    # ---- จัดอันดับความเหมาะ (แก้ #2) ----
    target_wp = required_system_wp(avg_kwh_month, specific_yield)
    if target_wp > 0 and "panel_total_wp" in work.columns and work["panel_total_wp"].notna().any():
        work = work.assign(_fit=(work["panel_total_wp"].fillna(0) - target_wp).abs())
        work = work.sort_values("_fit")
        warnings.append(f"จัดอันดับตามขนาดแผงที่เหมาะกับการใช้ไฟจริง "
                        f"(เป้าหมาย ≈ {target_wp/1000:.1f} kWp) แทนการเดาจากยอดบิล")
    elif "claimed_payback_years" in work.columns:
        work = work.sort_values("claimed_payback_years", na_position="last")
        target_wp = None
        warnings.append("ไม่มีข้อมูลหน่วยไฟลูกค้า — จัดอันดับตามระยะคืนทุนที่ vendor เคลมแทน")
    else:
        target_wp = None

    # ---- แท็ก "แพ็กตัวแทน 3 ระดับ" ให้ลูกค้าเลือกตามความต้องการ ----
    #   เล็กสุดที่แนะนำ  · ราคากลาง/คุ้มค่าที่สุด · ใกล้เป้าหมายการใช้ไฟ
    # เลือกจาก 'ผู้สมัครที่ผ่านตัวกรองทั้งหมด' (ไม่ใช่แค่ top-N) แล้วการันตีให้อยู่ในตารางเสมอ
    tier_rows, tier_labels = _pick_representative_tiers(work, target_wp)

    top = work.head(int(max_show)).copy()
    # การันตีว่าแพ็กตัวแทนทั้ง 3 อยู่ในตาราง แม้ขนาดจะห่างจากเป้าหมาย
    for idx in tier_rows.values():
        if idx is not None and idx not in top.index:
            top = pd.concat([top, work.loc[[idx]]])
    top = top.reset_index(drop=True)

    # ใส่คอลัมน์ป้ายคำแนะนำ (tier_label) ให้แถวตัวแทน
    label_by_code = {}
    for tier, idx in tier_rows.items():
        if idx is not None:
            code = str(work.loc[idx].get("package_code") or work.loc[idx].get("pack_id"))
            label_by_code[code] = tier_labels[tier]
    top["tier_label"] = [
        label_by_code.get(str(r.get("package_code") or r.get("pack_id")), "")
        for _, r in top.iterrows()
    ]

    return {"top": top, "dropped": dropped, "warnings": warnings,
            "target_wp": target_wp, "tiers": tier_labels}


def _pick_representative_tiers(work: pd.DataFrame, target_wp) -> tuple:
    """เลือกแพ็กตัวแทน 3 ระดับจากผู้สมัครที่ผ่านตัวกรอง
    คืน (dict tier->index, dict tier->label ภาษาไทย)
    - small  : กำลังแผงต่ำสุด (ราคาลงทุนน้อยสุด/ติดได้แน่ในพื้นที่จำกัด)
    - value  : คุ้มค่าที่สุด = ผลประหยัดต่อปี / ราคาลงทุน สูงสุด (ถ้าไม่มีข้อมูล ใช้ราค่ากลาง)
    - target : กำลังแผงใกล้เป้าหมายการใช้ไฟจริงที่สุด
    """
    labels = {"small": "เล็กสุดที่แนะนำ (ลงทุนน้อย)",
              "value": "ราคากลาง (คุ้มค่าที่สุด)",
              "target": "ใกล้เป้าหมายการใช้ไฟ"}
    tiers = {"small": None, "value": None, "target": None}

    if "panel_total_wp" in work.columns and work["panel_total_wp"].notna().any():
        d = work.dropna(subset=["panel_total_wp"])
        tiers["small"] = d["panel_total_wp"].idxmin()
        if target_wp and target_wp > 0:
            tiers["target"] = (d["panel_total_wp"] - target_wp).abs().idxmin()

    if "catalog_price" in work.columns and work["catalog_price"].notna().any():
        dp = work.dropna(subset=["catalog_price"])
        dp = dp[dp["catalog_price"] > 0]
        # กันข้อมูลราคาผิดปกติในแคตตาล็อก (เช่นพิมพ์ราคาตกหลัก) ไม่ให้ชนะ tier คุ้มค่า
        # ระบบโซลาร์จริงตกราว 15-80 บาท/Wp — คัดเฉพาะช่วงที่สมเหตุสมผลถ้าคำนวณได้
        if "panel_total_wp" in dp.columns and dp["panel_total_wp"].notna().any():
            ppw = dp["catalog_price"] / dp["panel_total_wp"].replace(0, pd.NA)
            sane = dp[(ppw >= 10) & (ppw <= 120)]
            if len(sane):
                dp = sane
        if len(dp):
            if "claimed_saving_year" in dp.columns and dp["claimed_saving_year"].notna().any():
                val = dp["claimed_saving_year"].fillna(0) / dp["catalog_price"]
                tiers["value"] = val.idxmax()
            else:
                med = dp["catalog_price"].median()
                tiers["value"] = (dp["catalog_price"] - med).abs().idxmin()

    # กันซ้ำ: ถ้า index เดียวถูกเลือกหลาย tier ให้คงไว้ tier ที่มีความหมายเจาะจงกว่า
    # (target > value > small) แล้วปล่อย tier ที่ซ้ำเป็น None เพื่อไม่ให้ป้ายทับกัน
    seen = {}
    for tier in ("target", "value", "small"):
        idx = tiers[tier]
        if idx is None:
            continue
        if idx in seen:
            tiers[tier] = None
        else:
            seen[idx] = tier
    return tiers, labels


def generate_sample_catalog() -> pd.DataFrame:
    """สร้างข้อมูล catalog ตัวอย่าง (โครงสร้างเดียวกับไฟล์จริง) สำหรับทดสอบระบบ"""
    rows = [
        dict(period="เม.ย.-มิ.ย.69", pack_id=1, package_code="PKG-SB-001", type="SB",
             phase="1 Phase", panel_brand="BrandA", panel_model="A-635", panel_wp=635,
             panel_qty=8, panel_total_wp=5080, inverter_brand="Huawei",
             inverter_model="SUN2000-5K", inverter_kw=5, inverter_qty=1,
             inverter_total_kw=5, battery_brand="Huawei", battery_model="LUNA2000-5",
             battery_kwh=5, battery_qty=1, battery_total_kwh=5, catalog_price=215000,
             warranty_panel_product=12, warranty_panel_power=30, warranty_inverter=10,
             warranty_battery=10, warranty_install=2, fire_insurance=1,
             maintenance="2/4", install_area_sqm=24, claimed_saving_month=2700,
             claimed_saving_year=32400, claimed_payback_years=6.64, price_per_wp=42.32,
             service_area="ทั่วประเทศ", notes="ตรวจเช็คระบบ 2 ปี ล้างแผง 4 ครั้ง"),
        dict(period="เม.ย.-มิ.ย.69", pack_id=2, package_code="PKG-SB-002", type="SB",
             phase="1 Phase", panel_brand="BrandA", panel_model="A-635", panel_wp=635,
             panel_qty=10, panel_total_wp=6350, inverter_brand="Deye",
             inverter_model="SUN-6K-SG", inverter_kw=6, inverter_qty=1,
             inverter_total_kw=6, battery_brand="Deye", battery_model="SE-G5.1PRO",
             battery_kwh=5.12, battery_qty=2, battery_total_kwh=10.24,
             catalog_price=289000, warranty_panel_product=12, warranty_panel_power=30,
             warranty_inverter=10, warranty_battery=10, warranty_install=2,
             fire_insurance=1, maintenance="2/4", install_area_sqm=30,
             claimed_saving_month=3600, claimed_saving_year=43200,
             claimed_payback_years=6.69, price_per_wp=45.51,
             service_area="ทั่วประเทศ", notes=""),
        dict(period="เม.ย.-มิ.ย.69", pack_id=3, package_code="PKG-SB-003", type="SB",
             phase="3 Phase", panel_brand="BrandB", panel_model="B-620", panel_wp=620,
             panel_qty=16, panel_total_wp=9920, inverter_brand="Huawei",
             inverter_model="SUN2000-10K", inverter_kw=10, inverter_qty=1,
             inverter_total_kw=10, battery_brand="Huawei", battery_model="LUNA2000-10",
             battery_kwh=10, battery_qty=1, battery_total_kwh=10, catalog_price=420000,
             warranty_panel_product=12, warranty_panel_power=30, warranty_inverter=10,
             warranty_battery=10, warranty_install=2, fire_insurance=1,
             maintenance="2/4", install_area_sqm=48, claimed_saving_month=5400,
             claimed_saving_year=64800, claimed_payback_years=6.48, price_per_wp=42.34,
             service_area="ทั่วประเทศ", notes=""),
    ]
    return pd.DataFrame(rows)
