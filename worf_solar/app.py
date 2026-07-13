"""
แอปหลัก: Solar & Battery — วิเคราะห์เพื่อการขาย
โยน 2 ไฟล์ (บิลลูกค้า + catalog แพ็กเกจ) ที่แถบซ้ายครั้งเดียว
ระบบคัดแพ็กที่เหมาะ -> ตารางเปรียบเทียบ -> กราฟคืนทุน -> export หน้าเดียว
วิธีรัน: streamlit run app.py
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

import time as _time

from data_parser import parse_customer_bill
from packages import (parse_package_catalog, generate_sample_catalog,
                      customer_view, recommend_packages)
from finance import simple_payback, npv, irr, discounted_payback
from tariff import TariffModel
from sim_bridge import simulate_package_savings
from analysis import (day_night_monthly_summary, linear_trend,
                      demand_peak_monthly, estimate_savings_from_monthly)

st.set_page_config(page_title="Solar & Battery — วิเคราะห์การขาย", layout="wide")

NEO_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

:root{
  --ink:#111111;
  --paper:#FBF8EF;
  --lilac:#E4D4FB;
  --mint:#B7F0CE;
  --pink:#F9CBDD;
  --cream:#FBF1CE;
  --blue:#CED6FA;
  --shadow:6px 6px 0 0 var(--ink);
  --shadow-sm:4px 4px 0 0 var(--ink);
  --radius:14px;
}

/* พื้นหลังหลัก + ฟอนต์ */
.stApp{ background:var(--paper); }
html, body, [class*="css"]{
  font-family:'Space Grotesk', system-ui, sans-serif;
  color:var(--ink);
}

/* ซ่อน header/footer ดีฟอลต์ของ streamlit ให้สะอาด */
header[data-testid="stHeader"]{ background:transparent; }
#MainMenu, footer{ visibility:hidden; }

/* หัวข้อ */
h1{
  font-weight:700 !important;
  letter-spacing:-0.02em;
  font-size:2.3rem !important;
}
h2,h3{ font-weight:600 !important; letter-spacing:-0.01em; }

/* ---------------- Sidebar เป็นแผงสีครีมขอบดำ ---------------- */
section[data-testid="stSidebar"]{
  background:var(--cream);
  border-right:3px solid var(--ink);
}
section[data-testid="stSidebar"] .block-container{ padding-top:1.5rem; }
section[data-testid="stSidebar"] h2{
  font-size:0.8rem !important;
  text-transform:uppercase;
  letter-spacing:0.08em;
  color:var(--ink);
  border-bottom:2px solid var(--ink);
  padding-bottom:.35rem;
  margin-bottom:.6rem;
}

/* ---------------- Input ทุกชนิด: ขอบดำ เงาเล็ก ---------------- */
div[data-baseweb="input"] input,
div[data-baseweb="select"] > div,
.stNumberInput input,
.stTextInput input,
div[data-testid="stFileUploaderDropzone"]{
  background:#fff !important;
  border:2px solid var(--ink) !important;
  border-radius:10px !important;
  box-shadow:var(--shadow-sm);
  color:var(--ink) !important;
  font-weight:500;
}
div[data-baseweb="input"]:focus-within input{ outline:none; }

/* radio / slider label */
.stRadio label, .stSlider label, .stNumberInput label, .stSelectbox label{
  font-weight:600 !important;
}

/* radio pills */
div[role="radiogroup"] label{
  background:#fff;
  border:2px solid var(--ink);
  border-radius:10px;
  padding:.35rem .6rem;
  margin-bottom:.35rem;
  box-shadow:var(--shadow-sm);
}

/* ---------------- Slider: บังคับดำทุกส่วน (แก้ปัญหาแถบม่วงกลืนพื้นเหลือง) ----------------
   สีหลักมาจาก theme primaryColor (config.toml เปลี่ยนเป็น #111111 แล้ว)
   CSS ด้านล่างกันเหนียวทุกชิ้นส่วน: ปุ่มจับ, แถบช่วงที่เลือก, ตัวเลขบนปุ่ม, ตัวเลข min/max */
div[data-testid="stSlider"] div[data-baseweb="slider"] div[role="slider"]{
  background:#111111 !important;
  border:2px solid var(--ink) !important;
  box-shadow:2px 2px 0 0 var(--ink) !important;
}
/* แถบช่วงที่เลือก (inner track) — ตัวที่เคยเป็นม่วงอ่อน */
div[data-testid="stSlider"] div[data-baseweb="slider"] > div > div,
div[data-testid="stSlider"] div[data-baseweb="slider"] > div > div > div{
  background:#111111 !important;
}
/* รางพื้นหลังส่วนที่ยังไม่เลือก ให้เป็นเทาเข้มพอมองเห็นบนพื้นครีม */
div[data-testid="stSlider"] div[data-baseweb="slider"] > div:first-child{
  background:rgba(17,17,17,0.25) !important;
}
/* ตัวเลขลอยเหนือปุ่มจับ */
div[data-testid="stSlider"] [data-testid="stSliderThumbValue"]{
  color:var(--ink) !important; font-weight:700 !important;
}
/* ตัวเลข min/max ใต้ราง */
div[data-testid="stSlider"] [data-testid="stTickBar"] *,
.stSlider [data-testid="stTickBarMin"],
.stSlider [data-testid="stTickBarMax"]{ color:var(--ink) !important; font-weight:600; }

/* ---------------- ปุ่ม ---------------- */
.stButton > button{
  background:var(--lilac);
  color:var(--ink);
  border:3px solid var(--ink);
  border-radius:12px;
  font-weight:700;
  font-size:1rem;
  padding:.6rem 1rem;
  box-shadow:var(--shadow);
  transition:transform .05s ease, box-shadow .05s ease;
  width:100%;
}
.stButton > button:hover{ background:var(--lilac); color:var(--ink); }
.stButton > button:active{
  transform:translate(4px,4px);
  box-shadow:1px 1px 0 0 var(--ink);
}

/* ---------------- การ์ด (block ที่เรา wrap เอง) ---------------- */
.neo-card{
  border:3px solid var(--ink);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  padding:1.1rem 1.25rem;
  margin-bottom:1.2rem;
}
.neo-card .eyebrow{
  font-family:'IBM Plex Mono', monospace;
  text-transform:uppercase;
  letter-spacing:0.1em;
  font-size:0.72rem;
  font-weight:600;
  opacity:.8;
  margin-bottom:.5rem;
}
.neo-lilac{ background:var(--lilac); }
.neo-mint{ background:var(--mint); }
.neo-pink{ background:var(--pink); }
.neo-blue{ background:var(--blue); }
.neo-cream{ background:var(--cream); }

/* KPI ตัวเลขใหญ่ */
.kpi-num{ font-size:2.1rem; font-weight:700; line-height:1; }
.kpi-lab{ font-family:'IBM Plex Mono',monospace; font-size:.7rem; text-transform:uppercase; letter-spacing:.08em; opacity:.75; }

/* ---------------- ตาราง dataframe ---------------- */
div[data-testid="stDataFrame"]{
  border:3px solid var(--ink);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  overflow:hidden;
}

/* ---------------- alert (success/info/error) ---------------- */
div[data-testid="stAlert"]{
  border:3px solid var(--ink) !important;
  border-radius:var(--radius) !important;
  box-shadow:var(--shadow);
  font-weight:600;
}

/* tabs */
button[data-baseweb="tab"]{
  background:#fff;
  border:2px solid var(--ink);
  border-radius:10px 10px 0 0;
  font-weight:700;
  margin-right:.3rem;
  box-shadow:var(--shadow-sm);
}
button[data-baseweb="tab"][aria-selected="true"]{ background:var(--mint); }

/* expander */
details, div[data-testid="stExpander"]{
  border:3px solid var(--ink) !important;
  border-radius:var(--radius) !important;
  box-shadow:var(--shadow);
  overflow:hidden;
}
div[data-testid="stExpander"] summary{ font-weight:700; }

/* spinner */
.stSpinner > div{ border-top-color:var(--ink) !important; }
</style>"""
st.markdown(NEO_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# helper: การ์ด + one-pager
# ---------------------------------------------------------------------------
def card_open(title: str, color: str = "neo-lilac"):
    st.markdown(f'<div class="neo-card {color}"><div class="eyebrow">{title}</div>',
                unsafe_allow_html=True)


def card_close():
    st.markdown("</div>", unsafe_allow_html=True)


def _nice_range(series, pad_frac: float = 0.18):
    """คำนวณช่วงแกน y ให้เส้นเต็มแผงพอดี ไม่ติดขอบ — อ่านง่ายทั้งค่าหลักพันและหลักล้าน
    (ปรับสเกลตามข้อมูลจริงของแต่ละแผง แทนการล็อกช่วงตายตัวที่จะทำให้ลูกค้ารายเล็กเห็นเส้นแบน)"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if not len(s):
        return None
    lo, hi = float(s.min()), float(s.max())
    if lo == hi:                      # ค่าเดียว/เท่ากันหมด: กันเส้นแบนติดขอบ
        span = abs(lo) * 0.1 or 1.0
        return [lo - span, hi + span]
    span = hi - lo
    return [max(0.0, lo - span * pad_frac), hi + span * pad_frac]


def _build_onepager_html(meta, avg_kwh, avg_cost, fin_rows, pkg_df, has_batt=True,
                         saving_source="claim") -> str:
    """สรุปหน้าเดียวส่งลูกค้า (เปิดในเบราว์เซอร์ -> Ctrl+P -> Save as PDF)"""
    biz = meta.get("business_type") or "ไม่ระบุ"
    meter = meta.get("meter_type") or ""
    cost_txt = f"{avg_cost:,.0f} บาท" if avg_cost else "—"
    batt_txt = "แบตเตอรี่" if has_batt else "ไม่มีแบตเตอรี่"
    # #16: ที่มาของตัวเลข + disclaimer ที่เดิมซ่อนอยู่ในคอมเมนต์ finance.py
    if saving_source == "sim":
        source_line = ("ตัวเลขผลประหยัด 'จากข้อมูลลูกค้า' จำลองจากโหลดโปรไฟล์จริงของลูกค้า "
                       "(rule-based dispatch + โปรไฟล์ PV ประมาณการ) และแสดงคู่กับตัวเลขแคตตาล็อก")
    elif saving_source == "estimate":
        source_line = ("ลูกค้ามีเฉพาะบิลรายเดือน — ตัวเลข 'จากข้อมูลลูกค้า' เป็นช่วงประมาณการ "
                       "(ขึ้นกับสัดส่วนการใช้ไฟเองจริง) ไม่ใช่ตัวเลขยืนยัน "
                       "หากต้องการตัวเลขแม่นยำ ควรขอข้อมูลการใช้ไฟราย 15 นาทีเพิ่มเติม")
    else:
        source_line = ("ตัวเลขผลประหยัดเป็นค่าที่ผู้ผลิต/ผู้ขายประเมินไว้ในแคตตาล็อก "
                       "ยังไม่ได้ยืนยันกับการใช้ไฟจริงของลูกค้ารายนี้")

    def table(rows_or_df):
        if isinstance(rows_or_df, pd.DataFrame):
            if not len(rows_or_df):
                return ""
            heads = "".join(f"<th>{c}</th>" for c in rows_or_df.columns)
            body = "".join("<tr>" + "".join(f"<td>{r[c]}</td>" for c in rows_or_df.columns)
                           + "</tr>" for _, r in rows_or_df.iterrows())
        else:
            if not rows_or_df:
                return ""
            heads = "".join(f"<th>{k}</th>" for k in rows_or_df[0].keys())
            body = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in r.values()) + "</tr>"
                           for r in rows_or_df)
        return f"<table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table>"

    return f"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap');
body{{font-family:'Sarabun',sans-serif;color:#111;max-width:900px;margin:24px auto;padding:0 20px;}}
h1{{font-size:1.6rem;border-bottom:4px solid #3B2A6B;padding-bottom:8px;}}
h2{{font-size:1.15rem;margin-top:24px;color:#3B2A6B;}}
.kpis{{display:flex;gap:14px;margin:16px 0;}}
.kpi{{flex:1;border:3px solid #111;border-radius:12px;padding:12px;text-align:center;box-shadow:4px 4px 0 #111;}}
.kpi .n{{font-size:1.4rem;font-weight:700;}}
.kpi .l{{font-size:.8rem;opacity:.7;}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:.8rem;}}
th,td{{border:1px solid #999;padding:6px 8px;text-align:center;}}
th{{background:#E4D4FB;font-weight:600;}}
.note{{font-size:.75rem;color:#777;margin-top:20px;border-top:1px dashed #ccc;padding-top:10px;}}
</style></head><body>
<h1>ข้อเสนอระบบโซลาร์ + {batt_txt}</h1>
<h2>ข้อมูลการใช้ไฟของลูกค้า</h2>
<div class="kpis">
<div class="kpi"><div class="n">{biz}</div><div class="l">{meter}</div></div>
<div class="kpi"><div class="n">{avg_kwh:,.0f}</div><div class="l">หน่วย/เดือน (kWh)</div></div>
<div class="kpi"><div class="n">{cost_txt}</div><div class="l">ค่าไฟเฉลี่ย/เดือน</div></div>
</div>
<h2>แพ็กเกจแนะนำ</h2>
{table(pkg_df)}
<h2>สรุปการเงิน</h2>
{table(fin_rows)}
<div class="note"><b>ข้อควรทราบ (สำคัญ):</b><br>
• {source_line}<br>
• ตัวเลขผลประหยัด/คืนทุนเป็นการประเมินเบื้องต้น อาจต่างจากการใช้งานจริง ควรสำรวจหน้างานก่อนสรุปราคาจริง<br>
• ผลจำลองใช้สมมติฐานแบบ perfect-foresight (ของจริงจะได้ผลประหยัดน้อยกว่าเล็กน้อย)<br>
• <b>ยังไม่รวม</b>ค่าเปลี่ยนแบตเตอรี่ระหว่างอายุโครงการ ถ้าอายุโครงการยาวกว่าอายุแบต ตัวเลข NPV/IRR จะดูดีกว่าความเป็นจริง<br>
• ควรให้ทีมการเงินตรวจสอบ (sanity-check) ก่อนใช้ตัวเลขนี้ผูกพันสัญญา</div>
</body></html>"""


# ---------------------------------------------------------------------------
# ประตูรหัสผ่าน (แก้ #11 ไม่ fallback changeme, #12 lockout, #13 timeout)
# ---------------------------------------------------------------------------
import os

MAX_ATTEMPTS = 5            # ล็อกหลังพลาดครบจำนวนนี้ (#12)
LOCKOUT_SECONDS = 300       # ล็อก 5 นาที
SESSION_TIMEOUT_SECONDS = 30 * 60  # หมดเวลาเซสชันหลังไม่ใช้งาน 30 นาที (#13)


def _get_configured_password():
    """อ่านรหัสผ่านจาก secrets ก่อน แล้วค่อย env var — ไม่มี default 'changeme' (#11)"""
    try:
        if "APP_PASSWORD" in st.secrets:
            return str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    return os.environ.get("APP_PASSWORD")


def check_password() -> bool:
    configured = _get_configured_password()

    # #11: ถ้าไม่ตั้งรหัสผ่านไว้เลย ปฏิเสธการรัน แทนที่จะเปิดด้วยรหัสเดาง่าย
    if not configured or configured == "changeme":
        st.markdown('<div class="neo-card neo-pink" style="max-width:640px;margin:3rem auto;">'
                    '<div class="eyebrow">ตั้งค่าไม่ครบ</div>'
                    '<div style="font-size:1.2rem;font-weight:700;">ยังไม่ได้ตั้งรหัสผ่านแอป</div>'
                    '<div style="margin-top:.6rem;font-weight:500;">ระบบจะไม่เปิดใช้งานจนกว่าจะตั้ง '
                    '<code>APP_PASSWORD</code> ที่ปลอดภัย — ตั้งได้ 2 วิธี:<br>'
                    '1) ไฟล์ <code>.streamlit/secrets.toml</code> ใส่บรรทัด '
                    '<code>APP_PASSWORD = "รหัสที่คาดเดายาก"</code><br>'
                    '2) ตั้ง environment variable <code>APP_PASSWORD</code> ก่อนรัน<br>'
                    '(ห้ามใช้ค่า <code>changeme</code>)</div></div>',
                    unsafe_allow_html=True)
        st.stop()

    now = _time.time()

    # #13: เช็คหมดเวลาเซสชัน
    if st.session_state.get("password_correct", False):
        last = st.session_state.get("last_active", now)
        if now - last > SESSION_TIMEOUT_SECONDS:
            st.session_state["password_correct"] = False
            st.warning("เซสชันหมดเวลา (ไม่ได้ใช้งานนานเกินไป) กรุณาเข้าสู่ระบบใหม่")
        else:
            st.session_state["last_active"] = now
            return True

    # #12: เช็คว่ากำลังถูกล็อกอยู่ไหม
    locked_until = st.session_state.get("locked_until", 0)
    if now < locked_until:
        wait = int(locked_until - now)
        st.markdown('<div class="neo-card neo-pink" style="max-width:520px;margin:3rem auto;">'
                    '<div class="eyebrow">ถูกล็อกชั่วคราว</div>'
                    f'<div style="font-size:1.15rem;font-weight:700;">ใส่รหัสผิดหลายครั้งเกินไป '
                    f'ลองใหม่ในอีก {wait} วินาที</div></div>', unsafe_allow_html=True)
        st.stop()

    def entered():
        attempts = st.session_state.get("attempts", 0)
        if st.session_state.get("password", "") == configured:
            st.session_state["password_correct"] = True
            st.session_state["attempts"] = 0
            st.session_state["last_active"] = _time.time()
            st.session_state.pop("password", None)
        else:
            attempts += 1
            st.session_state["attempts"] = attempts
            st.session_state["password_correct"] = False
            if attempts >= MAX_ATTEMPTS:
                st.session_state["locked_until"] = _time.time() + LOCKOUT_SECONDS
                st.session_state["attempts"] = 0

    st.markdown('<div class="neo-card neo-blue" style="max-width:520px;margin:3rem auto;">'
                '<div class="eyebrow">เข้าสู่ระบบ</div>'
                '<div style="font-size:1.3rem;font-weight:700;">ใส่รหัสผ่านเพื่อเข้าใช้งาน</div></div>',
                unsafe_allow_html=True)
    st.text_input("รหัสผ่าน", type="password", on_change=entered, key="password")
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        left = MAX_ATTEMPTS - st.session_state.get("attempts", 0)
        if st.session_state.get("password") is not None or st.session_state.get("attempts", 0):
            st.error(f"รหัสผ่านไม่ถูกต้อง (เหลืออีก {left} ครั้งก่อนถูกล็อกชั่วคราว)")
    return False


if not check_password():
    st.stop()

# ---------------------------------------------------------------------------
# SIDEBAR: อัปโหลด 2 ไฟล์ + ตั้งค่าทุกอย่างครั้งเดียว
# ---------------------------------------------------------------------------
with st.sidebar:
    if st.button("ออกจากระบบ"):   # #13 logout
        for k in ["password_correct", "last_active", "attempts"]:
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown("## 1) ไฟล์ข้อมูล")
    # #18: รองรับ .xlsx / .xls / .csv
    bill_file = st.file_uploader("ไฟล์บิล / พฤติกรรมลูกค้า (.xlsx/.xls/.csv)",
                                 type=["xlsx", "xls", "csv"])
    cat_file = st.file_uploader("ไฟล์แพ็กเกจสินค้า catalog (.xlsx/.xls/.csv)",
                                type=["xlsx", "xls", "csv"])
    use_sample_cat = st.checkbox("ยังไม่มี catalog — ใช้ตัวอย่างทดสอบ", value=False)

    st.markdown("## 2) ความต้องการลูกค้า")
    want_battery = st.radio("ลูกค้าต้องการแบตเตอรี่ไหม",
                            ["มีแบตเตอรี่", "ไม่เอาแบต (โซลาร์อย่างเดียว)"])
    batt_min_kwh, batt_max_kwh = st.slider("ช่วงความจุแบตที่รับได้ (kWh)", 0, 40, (5, 20))
    phase_pref = st.selectbox("ระบบไฟ", ["ทั้งหมด", "1 Phase", "3 Phase"])
    # #3: พื้นที่ติดตั้งที่ลูกค้ามี (0 = ไม่จำกัด/ไม่ทราบ)
    avail_area = st.number_input("พื้นที่หลังคาที่ติดตั้งได้ (ตร.ม., 0 = ไม่จำกัด)",
                                 value=0, min_value=0, step=5)

    st.markdown("## 3) อัตราค่าไฟ (PEA TOU)")
    # แสดง/กรอกเป็นทศนิยม 4 หลัก ให้ตรงกับประกาศอัตราจริงของการไฟฟ้า
    on_peak_rate = st.number_input("On-Peak (บาท/หน่วย)", value=5.7982,
                                   step=0.0001, format="%.4f")
    off_peak_rate = st.number_input("Off-Peak (บาท/หน่วย)", value=2.6369,
                                    step=0.0001, format="%.4f")
    ft_rate = st.number_input("ค่า Ft ปัจจุบัน (บาท/หน่วย)", value=0.1623,
                              step=0.0001, format="%.4f",
                              help="อัปเดตตามประกาศ กกพ. ทุก 4 เดือน")
    demand_charge = st.number_input("Demand Charge (บาท/kW)", value=132.93,
                                    step=0.0001, format="%.4f")
    # #8: ช่วงเวลา On-Peak ปรับได้ (เดิม hardcode 09:00-22:00)
    op_start, op_end = st.slider("ช่วงเวลา On-Peak (ชั่วโมง)", 0, 24, (9, 22))
    weekdays_only = st.checkbox("On-Peak เฉพาะ จ-ศ (TOU)", value=True)

    st.markdown("## 4) สมมติฐานการเงิน")
    horizon_years = st.number_input("อายุโครงการ (ปี)", value=10, min_value=1, max_value=30)
    escalation = st.slider("ค่าไฟปรับขึ้นต่อปี (%)", 0, 10, 3) / 100
    discount_rate = st.slider("อัตราคิดลด (%)", 0, 15, 5) / 100
    max_show = st.slider("แสดงกี่แพ็กเกจที่เหมาะสุด", 5, 15, 10)

    st.markdown("## 5) การคำนวณผลประหยัด")
    # #1: เลือกให้คำนวณจากข้อมูลจริง (ต้องมี interval data) แทนตัวเลขเคลมจาก catalog
    use_sim = st.checkbox("คำนวณผลประหยัดจากข้อมูลจริงของลูกค้า (จำลอง)", value=True,
                          help="มีไฟล์รายช่วง (interval) = จำลองเต็มรูปแบบ · "
                               "มีแค่บิลรายเดือน = ประเมินเป็นช่วง (range) แทน")
    specific_yield = st.slider("ผลผลิตโซลาร์ (kWh/kWp/วัน)", 3.0, 5.0, 4.0, step=0.1,
                               help="ไทยเฉลี่ย ~3.5-4.5 ขึ้นกับพื้นที่/ทิศทาง/องศาแผง")
    sc_low, sc_high = st.slider(
        "ช่วง Self-consumption ที่คาด (%) — ใช้เฉพาะกรณีมีแค่บิลรายเดือน",
        10, 100, (50, 90), step=5,
        help="สัดส่วนไฟโซลาร์ที่ลูกค้า 'ใช้เอง' — ไม่รู้แน่ถ้าไม่มีโหลดโปรไฟล์ "
             "จึงประเมินผลประหยัดเป็นช่วง ไม่ฟันธงตัวเลขเดียว")

    st.markdown("## 6) เทมเพลตไฟล์ลูกค้า")
    from template_builder import build_template_bytes
    st.download_button(
        "ดาวน์โหลดเทมเพลตกรอกข้อมูลลูกค้า (.xlsx)",
        data=build_template_bytes(),
        file_name="เทมเพลตข้อมูลลูกค้า.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="มีตัวอย่างครบทั้งกรณีโหลดโปรไฟล์ 15 นาที และกรณีมีแค่บิลรายเดือน")

# สร้าง TariffModel จากค่าที่ตั้งใน UI (ใช้ทั้งการจำลองและ On/Off-Peak — แก้ #8)
tariff_model = TariffModel(
    on_peak_rate=on_peak_rate, off_peak_rate=off_peak_rate, ft_rate=ft_rate,
    demand_charge_rate=demand_charge,
    on_peak_start_hour=int(op_start), on_peak_end_hour=int(op_end),
    on_peak_weekdays_only=bool(weekdays_only),
)

# ---------------------------------------------------------------------------
# หัวข้อ (เปลี่ยนตามว่ามีแบตหรือไม่)
# ---------------------------------------------------------------------------
_has_batt = want_battery.startswith("มีแบต")
_title_suffix = "แบตเตอรี่" if _has_batt else "ไม่มีแบตเตอรี่"
st.markdown(f"# วิเคราะห์ระบบโซลาร์ + {_title_suffix} เพื่อการขาย")
st.markdown('<p style="font-family:IBM Plex Mono,monospace;font-size:.85rem;opacity:.8;'
            'margin-top:-.5rem;">อัปโหลด 2 ไฟล์ที่แถบซ้าย แล้วระบบจะคัดแพ็กเกจที่เหมาะ '
            'พร้อมตัวเลขการเงินและไฟล์สรุปส่งลูกค้า</p>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# อ่านไฟล์
# ---------------------------------------------------------------------------
bill = None
if bill_file is not None:
    try:
        bill = parse_customer_bill(bill_file)
        for w in bill.get("warnings", []):   # #6: โชว์คำเตือนแทน fallback เงียบๆ
            st.warning(w)
    except Exception as e:
        st.error(f"อ่านไฟล์ลูกค้าไม่สำเร็จ: {e}")

catalog = None
if cat_file is not None:
    try:
        catalog = parse_package_catalog(cat_file)
    except Exception as e:
        st.error(f"อ่านไฟล์ catalog ไม่สำเร็จ: {e}")
elif use_sample_cat:
    catalog = generate_sample_catalog()

if bill is None and catalog is None:
    st.info("เริ่มต้นด้วยการอัปโหลดไฟล์ที่แถบด้านซ้าย (อย่างน้อยไฟล์ลูกค้า 1 ไฟล์)")
    st.stop()

# ---------------------------------------------------------------------------
# สรุปการใช้ไฟลูกค้า
# ---------------------------------------------------------------------------
avg_kwh = avg_cost = 0.0
meta = {}
if bill is not None:
    meta = bill.get("meta", {})
    if bill["mode"] == "monthly" and bill["monthly"] is not None and len(bill["monthly"]):
        mdf = bill["monthly"]
        n = len(mdf)
        tk = float(mdf["kwh"].sum(skipna=True)) if mdf["kwh"].notna().any() else 0.0
        tc = float(mdf["cost"].sum(skipna=True)) if mdf["cost"].notna().any() else 0.0
        avg_kwh = tk / n if n else 0
        avg_cost = tc / n if n else 0
    elif bill["mode"] == "interval" and bill["data"] is not None and len(bill["data"]):
        idf = bill["data"]
        avg_kwh = float(idf["load_kw"].mean()) * 24 * 30

    card_open("สรุปการใช้ไฟของลูกค้า", "neo-cream")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="neo-card neo-lilac"><div class="eyebrow">ประเภทกิจการ</div>'
                    f'<div class="kpi-num" style="font-size:1.3rem;">'
                    f'{meta.get("business_type") or "ไม่ระบุ"}</div>'
                    f'<div class="kpi-lab">{meta.get("meter_type") or ""}</div></div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="neo-card neo-mint"><div class="eyebrow">ใช้ไฟเฉลี่ย/เดือน</div>'
                    f'<div class="kpi-num">{avg_kwh:,.0f}</div>'
                    f'<div class="kpi-lab">หน่วย kWh</div></div>', unsafe_allow_html=True)
    with c3:
        lab = f"{avg_cost:,.0f}" if avg_cost else "ไม่ระบุ"
        st.markdown(f'<div class="neo-card neo-pink"><div class="eyebrow">ค่าไฟเฉลี่ย/เดือน</div>'
                    f'<div class="kpi-num">{lab}</div>'
                    f'<div class="kpi-lab">บาท</div></div>', unsafe_allow_html=True)
    card_close()

    if bill["mode"] == "monthly" and len(bill["monthly"]):
        card_open("แนวโน้มค่าไฟรายเดือนของลูกค้า", "neo-blue")
        mdf = bill["monthly"]
        has_cost = mdf["cost"].notna().any()
        has_kwh = mdf["kwh"].notna().any()

        if not (has_cost or has_kwh):
            st.info("ไม่มีข้อมูลค่าไฟหรือหน่วยไฟให้แสดงกราฟ")
        else:
            # แยกเป็นแผงบน/ล่าง (แชร์แกน x) แทน dual-axis ที่เส้นทับกันสนิท
            # แต่ละแผงปรับสเกลของตัวเองอัตโนมัติ -> เห็นการเปลี่ยนแปลงชัดทั้งค่าหลักพันและหลักล้าน
            titles, specs = [], []
            if has_cost:
                titles.append("ค่าไฟ (บาท)")
            if has_kwh:
                titles.append("หน่วยไฟ (kWh)")
            n_rows = len(titles)

            figm = make_subplots(rows=n_rows, cols=1, shared_xaxes=True,
                                  vertical_spacing=0.16, subplot_titles=titles)
            row = 1
            if has_cost:
                figm.add_trace(go.Scatter(
                    x=mdf["month"], y=mdf["cost"], name="ค่าไฟ (บาท)",
                    mode="lines+markers", line=dict(color="#D14D72", width=3),
                    marker=dict(size=9),
                    hovertemplate="%{x}<br>ค่าไฟ %{y:,.0f} บาท<extra></extra>"),
                    row=row, col=1)
                figm.update_yaxes(range=_nice_range(mdf["cost"]), tickformat="~s",
                                  ticksuffix=" ฿", gridcolor="rgba(17,17,17,0.08)",
                                  zeroline=False, row=row, col=1)
                row += 1
            if has_kwh:
                figm.add_trace(go.Scatter(
                    x=mdf["month"], y=mdf["kwh"], name="หน่วยไฟ (kWh)",
                    mode="lines+markers", line=dict(color="#111111", width=3),
                    marker=dict(size=9),
                    hovertemplate="%{x}<br>%{y:,.0f} kWh<extra></extra>"),
                    row=row, col=1)
                figm.update_yaxes(range=_nice_range(mdf["kwh"]), tickformat="~s",
                                  ticksuffix=" kWh", gridcolor="rgba(17,17,17,0.08)",
                                  zeroline=False, row=row, col=1)

            # เส้นประแนวโน้ม (Linear trend) แบบเดียวกับไฟล์วิเคราะห์ของทีม
            trow = 1
            if has_cost:
                tr = linear_trend(mdf["cost"])
                if tr:
                    figm.add_trace(go.Scatter(
                        x=mdf["month"], y=tr, name="แนวโน้มค่าไฟ", mode="lines",
                        line=dict(color="#D14D72", width=2, dash="dash"),
                        hoverinfo="skip"), row=trow, col=1)
                trow += 1
            if has_kwh:
                tr = linear_trend(mdf["kwh"])
                if tr:
                    figm.add_trace(go.Scatter(
                        x=mdf["month"], y=tr, name="แนวโน้มหน่วยไฟ", mode="lines",
                        line=dict(color="#111111", width=2, dash="dash"),
                        hoverinfo="skip"), row=trow, col=1)

            figm.update_xaxes(gridcolor="rgba(17,17,17,0.06)")
            figm.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
                font=dict(family="Space Grotesk, sans-serif", color="#111"),
                showlegend=False, height=190 * n_rows + 90,
                margin=dict(l=10, r=10, t=46, b=10))
            st.plotly_chart(figm, use_container_width=True)
            st.caption("แยกค่าไฟกับหน่วยไฟเป็นคนละแผง เส้นจึงไม่ทับกัน · แต่ละแผงปรับสเกลอัตโนมัติ "
                       "ให้เห็นการขึ้นลงชัดไม่ว่าค่าไฟจะหลักพันหรือหลักล้าน "
                       "· เส้นประ = แนวโน้ม (Linear trend)")
        card_close()

        # ---- การ์ดบอกระดับความละเอียดข้อมูล: อะไรวิเคราะห์ได้ / อะไรทำไม่ได้ (ขีดฆ่า) ----
        n_mo = len(bill["monthly"])
        few_note = ("" if n_mo >= 6 else
                    f" <span style='color:#B3261E;font-weight:700;'>(มีเพียง {n_mo} เดือน "
                    "— แนะนำอย่างน้อย 6 เดือน)</span>")
        st.markdown(
            '<div class="neo-card neo-cream"><div class="eyebrow">ระดับความละเอียดข้อมูล — '
            'ลูกค้ารายนี้มีเฉพาะบิลรายเดือน</div>'
            '<div style="line-height:1.9;font-weight:500;">'
            f'✅ แนวโน้มหน่วยไฟ/ค่าไฟรายเดือน + เส้นแนวโน้ม{few_note}<br>'
            '✅ คัดแพ็กเกจตามขนาดแผงที่เหมาะกับปริมาณการใช้ไฟ<br>'
            '✅ ผลประหยัดแบบ <b>ช่วงประมาณการ (ต่ำ–สูง)</b> ตามช่วง Self-consumption ที่ตั้งไว้<br>'
            '<span style="text-decoration:line-through;opacity:.55;">'
            'โปรไฟล์ Day/Night รายเดือน (Average/Max ต่อชั่วโมง)</span>'
            ' <span style="opacity:.7;">— ต้องมีข้อมูลรายช่วง 15 นาที/รายชั่วโมง</span><br>'
            '<span style="text-decoration:line-through;opacity:.55;">'
            'Demand Peak รายเดือน + ผลประหยัด peak shaving</span>'
            ' <span style="opacity:.7;">— บิลปกติไม่บันทึกค่าพีค</span><br>'
            '<span style="text-decoration:line-through;opacity:.55;">'
            'จำลองผลประหยัดจากโหลดจริง (dispatch รายช่วง)</span>'
            ' <span style="opacity:.7;">— ระบบจะใช้ช่วงประมาณการแทน และไม่ฟันธงขนาดแบตเตอรี่</span>'
            '</div>'
            '<div style="margin-top:.6rem;font-size:.85rem;opacity:.75;">'
            '💡 มุมเซล: ถ้าขอไฟล์โหลดโปรไฟล์ราย 15 นาทีจากลูกค้าได้ (มิเตอร์ TOU/AMR ขอจากการไฟฟ้าได้) '
            'อัปโหลดแทนไฟล์นี้ ระบบจะปลดล็อกการวิเคราะห์ที่ขีดฆ่าไว้ทั้งหมดอัตโนมัติ</div></div>',
            unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # กราฟพฤติกรรมการใช้ไฟแบบ monitor (PV solar / โหลด / SOC)
    # ใช้ได้เมื่อไฟล์เป็นรายช่วงเวลา (interval) ที่มีโปรไฟล์รายชั่วโมง
    # -----------------------------------------------------------------------
    if bill["mode"] == "interval" and bill["data"] is not None and len(bill["data"]) > 0:
        idf = bill["data"].copy()
        idf["timestamp"] = pd.to_datetime(idf["timestamp"])
        idf = idf.sort_values("timestamp").reset_index(drop=True)

        # -------------------------------------------------------------------
        # วิเคราะห์พฤติกรรมรายเดือน Day/Night (Average / Max ต่อชั่วโมง + เส้นแนวโน้ม)
        # รูปแบบเดียวกับไฟล์วิเคราะห์ของทีม: Day 07:00-17:59 · Night 18:00-06:59
        # -------------------------------------------------------------------
        dn = day_night_monthly_summary(idf)
        if len(dn) >= 1:
            card_open("พฤติกรรมการใช้ไฟรายเดือน — Day / Night (จากข้อมูลจริง)", "neo-blue")

            k1, k2, k3, k4 = st.columns(4)
            for col, lab, val in [
                    (k1, "Day · Average ของ Average (kW)", dn["day_avg_kw"].mean()),
                    (k2, "Day · Average ของ Max (kW)", dn["day_max_kw"].mean()),
                    (k3, "Night · Average ของ Average (kW)", dn["night_avg_kw"].mean()),
                    (k4, "Night · Average ของ Max (kW)", dn["night_max_kw"].mean())]:
                with col:
                    v = "—" if pd.isna(val) else f"{val:,.2f}"
                    st.markdown(f'<div class="neo-card neo-cream" style="padding:.7rem .9rem;">'
                                f'<div class="kpi-lab">{lab}</div>'
                                f'<div class="kpi-num" style="font-size:1.5rem;">{v}</div></div>',
                                unsafe_allow_html=True)

            def _dn_chart(title, avg_col, max_col):
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dn["month_label"], y=dn[avg_col], name="Average value per hour",
                    mode="lines+markers+text", text=[f"{v:,.2f}" for v in dn[avg_col]],
                    textposition="bottom center", textfont=dict(size=10),
                    line=dict(color="#E8762C", width=3), marker=dict(size=8, symbol="square")))
                fig.add_trace(go.Scatter(
                    x=dn["month_label"], y=dn[max_col], name="Max value per hour",
                    mode="lines+markers+text", text=[f"{v:,.2f}" for v in dn[max_col]],
                    textposition="top center", textfont=dict(size=10),
                    line=dict(color="#2E5FA3", width=3), marker=dict(size=8)))
                tr_avg, tr_max = linear_trend(dn[avg_col]), linear_trend(dn[max_col])
                if tr_avg:
                    fig.add_trace(go.Scatter(
                        x=dn["month_label"], y=tr_avg, name="Linear (Average)",
                        mode="lines", line=dict(color="#5B9E62", width=2, dash="dash"),
                        hoverinfo="skip"))
                if tr_max:
                    fig.add_trace(go.Scatter(
                        x=dn["month_label"], y=tr_max, name="Linear (Max)",
                        mode="lines", line=dict(color="#2FB8D6", width=2, dash="dash"),
                        hoverinfo="skip"))
                fig.update_layout(
                    title=dict(text=title, x=0.5, font=dict(size=15)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
                    font=dict(family="Space Grotesk, sans-serif", color="#111"),
                    xaxis=dict(title="เดือน", gridcolor="rgba(17,17,17,0.06)"),
                    yaxis=dict(title="หน่วย / ชั่วโมง (kW)", rangemode="tozero",
                               gridcolor="rgba(17,17,17,0.08)"),
                    legend=dict(orientation="h", y=-0.28), height=430,
                    margin=dict(l=10, r=10, t=48, b=10))
                return fig

            st.plotly_chart(_dn_chart("Day Time (07:00 - 17:59)",
                                      "day_avg_kw", "day_max_kw"),
                            use_container_width=True)
            st.plotly_chart(_dn_chart("Night Time (18:00 - 06:59)",
                                      "night_avg_kw", "night_max_kw"),
                            use_container_width=True)

            if len(dn) < 2:
                st.info("มีข้อมูลเพียง 1 เดือน — เส้นแนวโน้ม (Linear) จะแสดงเมื่อมีอย่างน้อย 2 เดือน")
            st.caption("Average = ค่าเฉลี่ยโหลดทุกช่วงในเดือน · Max = โหลดสูงสุดที่พบในเดือน "
                       "(ฐานเดียวกับ Demand Peak) · เส้นประ = แนวโน้มเชิงเส้น "
                       "— คำนวณจากไฟล์ข้อมูลจริงของลูกค้า ไม่ใช่ตัวเลขสมมติ")

            # Demand Peak รายเดือน (เฉพาะช่วง On-Peak ตามที่ตั้งไว้) — ใช้คุยเรื่อง peak shaving
            dp = demand_peak_monthly(idf, tariff_model)
            if len(dp):
                with st.expander("Demand Peak รายเดือน (ช่วง On-Peak) — ใช้ประเมิน peak shaving"):
                    dp_show = pd.DataFrame({
                        "เดือน": dp["month_label"],
                        "Demand Peak (kW)": dp["peak_kw"].round(1),
                        "เวลาเกิดพีค": pd.to_datetime(dp["peak_time"]).dt.strftime("%d/%m/%Y %H:%M"),
                        "ค่า Demand Charge (บาท)": (dp["peak_kw"] * demand_charge).round(2),
                    })
                    st.dataframe(dp_show, use_container_width=True)
            card_close()

        card_open("กราฟพฤติกรรมการใช้ไฟ (แบบหน้าจอ monitor)", "neo-mint")
        # #15: เตือนให้ชัดว่าเส้น PV/SOC เป็นการจำลอง ไม่ใช่ค่าวัดจริงหน้างาน
        st.warning("เฉพาะ **เส้นโหลด (ชมพู)** คือข้อมูลจริงจากไฟล์ลูกค้า · "
                   "เส้น PV โซลาร์และ SOC แบตเป็น **การจำลองเพื่อดูภาพรวมเท่านั้น** "
                   "ไม่ใช่ค่าที่จะได้จากการติดตั้งจริง")

        # จำนวนวันที่ข้อมูลครอบคลุมจริง (นับจากช่วงเวลา ไม่ใช่หารจำนวนแถวแบบตายตัว)
        # กันเคสข้อมูลวันเดียว/ช่วงสั้น ที่ทำให้ st.slider ได้ min==max แล้ว crash
        span = idf["timestamp"].max() - idf["timestamp"].min()
        total_days = max(1, int(span.total_seconds() // 86400) + 1)
        max_days = min(30, total_days)

        colsel1, colsel2 = st.columns([2, 1])
        with colsel2:
            show_pv = st.checkbox("จำลอง PV โซลาร์", value=True, key="behav_pv")
        with colsel1:
            if max_days >= 2:
                n_days = st.slider("แสดงข้อมูลกี่วัน", 1, max_days,
                                   min(7, max_days), key="behav_days")
            else:
                # ข้อมูลครอบคลุมช่วงสั้น (เช่น ตัวอย่างลูกค้ารายช่วง 15 นาที ไม่กี่จุด)
                # แสดงทั้งหมดไปเลย ไม่ต้องมีสไลเดอร์
                n_days = 1
                st.caption(f"ข้อมูลครอบคลุมช่วงสั้น ({len(idf):,} จุด ภายใน ~1 วัน) — แสดงทั้งหมด")

        # ตัดข้อมูลตามจำนวนวันจากต้น
        start_ts = idf["timestamp"].iloc[0]
        end_ts = start_ts + pd.Timedelta(days=n_days)
        seg = idf[(idf["timestamp"] >= start_ts) & (idf["timestamp"] < end_ts)].copy()

        figb = go.Figure()
        # โหลดจริงของลูกค้า (เส้นทึบชมพู)
        figb.add_trace(go.Scatter(x=seg["timestamp"], y=seg["load_kw"], name="โหลดที่ใช้ (kW)",
                                  mode="lines", line=dict(color="#D14D72", width=2.5)))

        if show_pv:
            # จำลอง PV จากรูประฆังคว่ำกลางวัน สูงสุด ~ ค่าพีคโหลด
            peak_load = float(seg["load_kw"].max()) if len(seg) else 5.0
            hours = seg["timestamp"].dt.hour + seg["timestamp"].dt.minute / 60
            import numpy as _np
            pv = _np.where((hours >= 6) & (hours <= 18),
                           peak_load * 0.9 * _np.sin(_np.pi * (hours - 6) / 12).clip(0), 0)
            figb.add_trace(go.Scatter(x=seg["timestamp"], y=pv, name="PV โซลาร์ที่ผลิต (kW)",
                                      mode="lines", line=dict(color="#E8A33D", width=2.5)))

            if _has_batt:
                # จำลอง SOC ง่ายๆ: PV เหลือชาร์จเข้า / โหลดเกินดึงออก
                cap = float(batt_max_kwh) if batt_max_kwh else 10.0
                soc_kwh, soc_series = cap * 0.5, []
                dt_h = 0.25  # สมมติราย 15 นาที
                for ld, pvv in zip(seg["load_kw"].values, pv):
                    net = pvv - ld
                    soc_kwh = min(cap, max(cap * 0.2, soc_kwh + net * dt_h))
                    soc_series.append(soc_kwh / cap * 100)
                figb.add_trace(go.Scatter(x=seg["timestamp"], y=soc_series, name="ระดับแบต SOC (%)",
                                          mode="lines", yaxis="y2",
                                          line=dict(color="#111111", width=2, dash="dot")))

        layout_kw = dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
            font=dict(family="Space Grotesk, sans-serif", color="#111"),
            yaxis=dict(title="กำลังไฟ (kW)"),
            legend=dict(orientation="h", y=1.15), height=380,
            margin=dict(l=10, r=10, t=30, b=10))
        if _has_batt and show_pv:
            layout_kw["yaxis2"] = dict(title="SOC (%)", overlaying="y", side="right",
                                       range=[0, 100])
        figb.update_layout(**layout_kw)
        st.plotly_chart(figb, use_container_width=True)
        st.caption("เส้นชมพู = โหลดจริงจากไฟล์ลูกค้า · เส้นส้ม = ประมาณการ PV โซลาร์ "
                   "· เส้นประดำ = SOC แบต (จำลอง) — ใช้ประเมินภาพรวม ไม่ใช่ค่าติดตั้งจริง")
        card_close()
if catalog is None or not len(catalog):
    st.info("อัปโหลดไฟล์ catalog (หรือติ๊กใช้ตัวอย่าง) ที่แถบซ้าย เพื่อดูแพ็กเกจแนะนำ")
    st.stop()

# ---------------------------------------------------------------------------
# คัดกรอง + จัดอันดับ (ย้าย business logic ไป packages.recommend_packages — แก้ #14, #2, #3)
# ---------------------------------------------------------------------------
# กรองยี่ห้อ (มุมเซล: ลูกค้าบางรายเจาะจงแบรนด์ — เลือกแล้วจะเห็น 5-10 ตัวเลือกของแบรนด์นั้น)
if "inverter_brand" in catalog.columns:
    _brands = sorted(catalog["inverter_brand"].dropna().astype(str).unique().tolist())
    if _brands:
        brand_pick = st.multiselect("กรองยี่ห้ออินเวอร์เตอร์ (เว้นว่าง = ทุกแบรนด์)",
                                    _brands, default=[])
        if brand_pick:
            catalog = catalog[catalog["inverter_brand"].astype(str).isin(brand_pick)]

rec = recommend_packages(
    catalog, want_battery=_has_batt,
    batt_min_kwh=batt_min_kwh, batt_max_kwh=batt_max_kwh,
    phase_pref=phase_pref, avg_kwh_month=avg_kwh,
    avail_area_sqm=(avail_area or None), specific_yield=specific_yield,
    max_show=int(max_show),
)
top = rec["top"]
for w in rec["warnings"]:
    st.info(w)
if not len(top):
    st.stop()

# ---------------------------------------------------------------------------
# คำนวณผลประหยัด/เดือน "ต่อแพ็ก" จากข้อมูลจริงถ้าทำได้ (แก้ #1)
# ผลลัพธ์เก็บใน sim_saving[code] ; ถ้าคำนวณไม่ได้ -> None แล้ว fallback ค่าเคลม
# ---------------------------------------------------------------------------
have_interval = (bill is not None and bill.get("mode") == "interval"
                 and bill.get("data") is not None and len(bill["data"]) > 0)
have_monthly = (bill is not None and bill.get("mode") == "monthly"
                and bill.get("monthly") is not None and len(bill["monthly"]) > 0
                and avg_kwh > 0)
sim_saving = {}
est_saving = {}
saving_source = "claim"   # claim | sim | estimate
if use_sim and have_interval:
    with st.spinner("กำลังจำลองผลประหยัดจากข้อมูลการใช้ไฟจริงของลูกค้า..."):
        for _, p in top.iterrows():
            code = str(p.get("package_code") or p.get("pack_id"))
            try:
                res = simulate_package_savings(bill["data"], p, tariff_model,
                                               specific_yield=specific_yield,
                                               has_battery=_has_batt)
            except Exception:
                res = None
            sim_saving[code] = res
    if any(v is not None for v in sim_saving.values()):
        saving_source = "sim"
elif use_sim and have_monthly:
    # กรณีมีแค่บิลรายเดือน: ประเมินผลประหยัดเป็น "ช่วง" (ต่ำ-สูง) รายแพ็ก
    # ตามช่วง Self-consumption ที่ตั้งไว้ในแถบซ้าย — ไม่ฟันธงตัวเลขเดียว
    for _, p in top.iterrows():
        code = str(p.get("package_code") or p.get("pack_id"))
        try:
            est = estimate_savings_from_monthly(
                avg_kwh, avg_cost, p, tariff_model,
                specific_yield=specific_yield, has_battery=_has_batt,
                sc_low=sc_low / 100.0, sc_high=sc_high / 100.0)
        except Exception:
            est = None
        est_saving[code] = est
    if any(v is not None for v in est_saving.values()):
        saving_source = "estimate"


def _saving_month_for(p) -> tuple:
    """คืน (ผลประหยัด/เดือน, ที่มา) ของแพ็กนี้ ตามข้อมูลที่ดีที่สุดที่มี:
    จำลองจากโหลดจริง > ช่วงประมาณการจากบิล (ใช้ค่ากลาง) > ตัวเลขเคลมจาก catalog"""
    code = str(p.get("package_code") or p.get("pack_id"))
    res = sim_saving.get(code)
    if res is not None and res.get("saving_month") is not None:
        return float(res["saving_month"]), "sim"
    est = est_saving.get(code)
    if est is not None and est.get("saving_mid") is not None:
        return float(est["saving_mid"]), "estimate"
    sm = p.get("claimed_saving_month")
    if pd.isna(sm) or not sm:
        return (float(avg_cost) if avg_cost else 0.0), "fallback"
    return float(sm), "claim"


def _saving_display_for(p) -> str:
    """สตริงผลประหยัด/เดือน 'จากข้อมูลลูกค้า' สำหรับโชว์ในตาราง:
    sim = ตัวเลขเดียว · estimate = ช่วง ต่ำ-สูง · ไม่มีข้อมูล = '—'"""
    code = str(p.get("package_code") or p.get("pack_id"))
    res = sim_saving.get(code)
    if res is not None and res.get("saving_month") is not None:
        return f"{res['saving_month']:,.0f}"
    est = est_saving.get(code)
    if est is not None:
        return f"{est['saving_low']:,.0f} – {est['saving_high']:,.0f}"
    return "—"


# แบนเนอร์บอกที่มาของตัวเลข (แก้ #1/#15 — โปร่งใสว่าเป็นตัวเลขจริง/ประมาณ/เคลม)
if saving_source == "sim":
    st.success("ตัวเลขผลประหยัด 'จากข้อมูลลูกค้า' ด้านล่าง **จำลองจากโหลดโปรไฟล์จริงราย 15 นาที"
               "ของลูกค้า** (rule-based dispatch + โปรไฟล์ PV ประมาณการ) "
               "— แสดงคู่กับตัวเลขแคตตาล็อกเพื่อเทียบกัน")
elif saving_source == "estimate":
    st.info(f"ลูกค้ารายนี้มีเฉพาะบิลรายเดือน — ตัวเลข 'จากข้อมูลลูกค้า' จึงเป็น "
            f"**ช่วงประมาณการ (Self-consumption {sc_low}-{sc_high}%)** ไม่ใช่ตัวเลขฟันธง "
            "· แสดงคู่กับตัวเลขแคตตาล็อกเพื่อเทียบกัน "
            "· ถ้าต้องการตัวเลขแม่นขึ้น ให้ขอโหลดโปรไฟล์ราย 15 นาทีจากลูกค้า")
else:
    reason = "ไม่ได้เปิดโหมดจำลอง" if not use_sim else "ไม่มีข้อมูลการใช้ไฟของลูกค้า"
    st.warning(f"ตัวเลขผลประหยัดด้านล่างเป็น **ค่าที่ vendor เคลมในแคตตาล็อก** ({reason}) "
               "ยังไม่ได้ยืนยันกับการใช้ไฟจริงของลูกค้ารายนี้")

# ตารางเปรียบเทียบ (ภาษาไทย ซ่อนต้นทุน/มาร์จิน)
# โจทย์การขาย: โชว์ 2 มุมคู่กันทุกแพ็ก —
#   (1) จากข้อมูลลูกค้า (จำลองโหลดจริง หรือช่วงประมาณการจากบิล)
#   (2) จากแคตตาล็อกในฐานข้อมูล (ตัวเลขที่ vendor เคลม)
card_open(f"แพ็กเกจแนะนำ {len(top)} อันดับ (คัดจาก {len(catalog)} แพ็ก ให้เหมาะกับลูกค้ารายนี้)", "neo-mint")
cust = customer_view(top).copy()

_have_customer_numbers = saving_source in ("sim", "estimate")
if _have_customer_numbers:
    cust["ประหยัด/เดือน — จากข้อมูลลูกค้า (บาท)"] = \
        [_saving_display_for(p) for _, p in top.iterrows()]
    # คืนทุนจากข้อมูลลูกค้า = ราคาลงทุน / (ผลประหยัดต่อปีที่คำนวณได้)
    _payback_cust = []
    for _, p in top.iterrows():
        sm, _src = _saving_month_for(p)
        capex = p.get("catalog_price")
        if _src in ("sim", "estimate") and sm > 0 and capex and not pd.isna(capex):
            _payback_cust.append(round(float(capex) / (sm * 12), 1))
        else:
            _payback_cust.append(None)
    cust["คืนทุน — จากข้อมูลลูกค้า (ปี)"] = _payback_cust
# ตัวเลขแคตตาล็อกคงไว้ตามไฟล์ ไม่ทับด้วยตัวเลขคำนวณ (เพื่อให้เทียบกันได้จริง)
cust = cust.rename(columns={
    "ประหยัด/เดือน (บาท)": "ประหยัด/เดือน — แคตตาล็อก (บาท)",
    "คืนทุน (ปี)": "คืนทุน — แคตตาล็อก (ปี)",
})

show_cols = [c for c in [
    "รหัสแพ็กเกจ", "ยี่ห้ออินเวอร์เตอร์", "ขนาดอินเวอร์เตอร์ (kW)",
    # #: โชว์ยี่ห้อ/รุ่นแบตเตอรี่เสมอเมื่อลูกค้าเลือก 'มีแบตเตอรี่' (แก้บั๊กที่ไม่ขึ้นชื่อแบรนด์)
    *(["ยี่ห้อแบตเตอรี่", "รุ่นแบตเตอรี่", "ความจุแบต (kWh)"] if _has_batt else []),
    "กำลังแผงรวม (Wp)", "จำนวนแผง", "ราคาลงทุน (บาท)",
    "ประหยัด/เดือน — จากข้อมูลลูกค้า (บาท)", "ประหยัด/เดือน — แคตตาล็อก (บาท)",
    "คืนทุน — จากข้อมูลลูกค้า (ปี)", "คืนทุน — แคตตาล็อก (ปี)",
    "ประกันแบตเตอรี่ (ปี)"]
    if c in cust.columns]
# แทรกคอลัมน์ป้ายคำแนะนำ (เล็กสุด/ราคากลาง/ใกล้เป้าหมาย) ไว้ต้นตาราง ถ้ามี
if "tier_label" in top.columns and top["tier_label"].astype(str).str.len().gt(0).any():
    cust.insert(0, "คำแนะนำ", top["tier_label"].values)
    show_cols = ["คำแนะนำ"] + show_cols
st.dataframe(cust[show_cols], use_container_width=True)
if _have_customer_numbers:
    st.caption("คอลัมน์ 'จากข้อมูลลูกค้า' = คำนวณจากพฤติกรรมใช้ไฟจริง (แม่นกับลูกค้ารายนี้) · "
               "'แคตตาล็อก' = ตัวเลขมาตรฐานจากฐานข้อมูล ซึ่งมักดูดีกว่าเพราะใช้สมมติฐานกลาง "
               "— โชว์คู่กันให้ลูกค้าเห็นภาพและตัดสินใจบนตัวเลขของตัวเอง")
if "tier_label" in top.columns and top["tier_label"].astype(str).str.len().gt(0).any():
    st.caption("คอลัมน์ 'คำแนะนำ' ชี้ 3 ทางเลือกให้ลูกค้าเลือกตามความต้องการ: "
               "**เล็กสุดที่แนะนำ** (ลงทุนน้อย เหมาะพื้นที่/งบจำกัด) · "
               "**ราคากลาง (คุ้มค่าที่สุด)** (ประหยัดต่อบาทที่ลงทุนสูงสุด) · "
               "**ใกล้เป้าหมายการใช้ไฟ** (ขนาดใกล้ ≈ เป้าหมาย kWp ที่วิเคราะห์จากการใช้ไฟจริง)")
card_close()

# แจ้งแพ็กที่ถูกตัดออก (แก้ #10)
if rec["dropped"]:
    with st.expander(f"ดูแพ็กที่ถูกคัดออก ({len(rec['dropped'])} แพ็ก) และเหตุผล"):
        st.dataframe(pd.DataFrame(rec["dropped"], columns=["รหัสแพ็กเกจ", "เหตุผลที่ถูกตัด"]),
                     use_container_width=True)

# ---------------------------------------------------------------------------
# ตารางการเงิน
# ---------------------------------------------------------------------------
card_open("ตัวเลขการเงินพร้อมนำเสนอ", "neo-lilac")
fin_rows = []
dropped_fin = []
for _, p in top.iterrows():
    name = str(p.get("package_code") or p.get("pack_id"))
    capex = p.get("catalog_price")
    if pd.isna(capex) or not capex:
        dropped_fin.append((name, "ไม่มีราคาลงทุน (catalog_price) ในไฟล์"))
        continue
    sm, _src = _saving_month_for(p)
    sy = float(sm) * 12
    if sy <= 0:
        dropped_fin.append((name, "ผลประหยัดที่คำนวณได้ ≤ 0"))
        continue
    cat_pb = p.get("claimed_payback_years")
    fin_rows.append({
        "รหัสแพ็กเกจ": name,
        "ราคาลงทุน (บาท)": f"{capex:,.0f}",
        "ประหยัด/ปี (บาท)": f"{sy:,.0f}",
        "คืนทุน — จากข้อมูลลูกค้า (ปี)": round(simple_payback(capex, sy), 1),
        "คืนทุน — แคตตาล็อก (ปี)": (round(float(cat_pb), 1)
                                    if cat_pb and not pd.isna(cat_pb) else "—"),
        "คืนทุนแบบคิดลด (ปี)": round(discounted_payback(capex, sy, int(horizon_years),
                                                        discount_rate, escalation), 1),
        # แก้ #4: ใช้ discount_rate จริง (เดิมใส่ 0.0 ทำให้ slider ไม่มีผล)
        f"กำไรสะสม {int(horizon_years)} ปี (NPV, บาท)":
            f"{npv(capex, sy, int(horizon_years), discount_rate, escalation):,.0f}",
        "IRR (%)": round(irr(capex, sy, int(horizon_years), escalation) * 100, 1),
    })
if fin_rows:
    st.dataframe(pd.DataFrame(fin_rows), use_container_width=True)
    st.caption("กำไรสะสมคิดแบบ NPV (ปรับด้วยอัตราคิดลดจริงจากแถบซ้าย) · "
               "ตัวเลขประเมินเบื้องต้น ควรให้ทีมการเงินตรวจก่อนใช้ผูกพันสัญญา")
# แก้ #10: แจ้งด้วยว่าแพ็กไหนหลุดจากตารางการเงินเพราะข้อมูลขาด
if dropped_fin:
    st.caption("แพ็กที่ไม่ขึ้นในตารางการเงิน: "
               + " · ".join(f"{c} ({r})" for c, r in dropped_fin))
card_close()

# ---------------------------------------------------------------------------
# กราฟคืนทุน — เรียบง่าย โชว์แค่ 3 แพ็กแรก (ถูก/กลาง/แพง) ไม่ให้เส้นรก
# ---------------------------------------------------------------------------
if fin_rows:
    card_open("กราฟจุดคืนทุน (เส้นตัดเส้นประ = คืนทุนแล้ว)", "neo-pink")
    # ใช้ 3 แพ็กตัวแทนเดียวกับตาราง: เล็กสุด / ราคากลางคุ้มค่า / ใกล้เป้าหมาย
    picks, pick_labels = [], []
    if "tier_label" in top.columns:
        for tier in ["เล็กสุดที่แนะนำ (ลงทุนน้อย)", "ราคากลาง (คุ้มค่าที่สุด)",
                     "ใกล้เป้าหมายการใช้ไฟ"]:
            m = top[top["tier_label"] == tier]
            m = m.dropna(subset=["catalog_price"])
            if len(m):
                picks.append(m.iloc[0])
                pick_labels.append(tier.split(" (")[0])
    if not picks:
        # fallback: กระจายตามราคา ถ้าไม่มีป้ายตัวแทน
        price_sorted = top.dropna(subset=["catalog_price"]).sort_values("catalog_price")
        if len(price_sorted) >= 3:
            picks = [price_sorted.iloc[0], price_sorted.iloc[len(price_sorted)//2],
                     price_sorted.iloc[-1]]
            pick_labels = ["ราคาประหยัดสุด", "ราคากลาง", "สเปกสูงสุด"]
        else:
            picks = [price_sorted.iloc[i] for i in range(len(price_sorted))]
            pick_labels = [f"แพ็ก {i+1}" for i in range(len(picks))]

    colors = ["#2E8B57", "#3B2A6B", "#D14D72"]
    figc = go.Figure()
    for i, p in enumerate(picks):
        capex = p["catalog_price"]
        sm, _src = _saving_month_for(p)   # ใช้ผลประหยัดจำลองจริงถ้ามี (แก้ #1)
        sy = float(sm) * 12
        cum, vals, s = -capex, [-capex], sy
        for _ in range(int(horizon_years)):
            cum += s
            vals.append(cum)
            s *= (1 + escalation)
        figc.add_trace(go.Scatter(
            x=list(range(int(horizon_years) + 1)), y=vals, mode="lines+markers",
            name=f"{pick_labels[i]} ({capex:,.0f} บ.)",
            line=dict(width=3, color=colors[i % len(colors)])))
    figc.add_hline(y=0, line_dash="dash", line_color="#111")
    figc.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
                       font=dict(family="Space Grotesk, sans-serif", color="#111"),
                       xaxis=dict(title="ปีที่"), yaxis=dict(title="กำไรสะสม (บาท)"),
                       legend=dict(orientation="h", y=1.15), height=400,
                       margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(figc, use_container_width=True)
    st.caption("แสดง 3 แพ็กตัวแทนตามคำแนะนำ (เล็กสุด / ราคากลางคุ้มค่า / ใกล้เป้าหมายการใช้ไฟ) "
               "ให้ลูกค้าเทียบจุดคืนทุนของแต่ละทางเลือก")
    card_close()

# ---------------------------------------------------------------------------
# export one-pager
# ---------------------------------------------------------------------------
card_open("บันทึกสรุปส่งลูกค้า / นำเสนอหัวหน้า", "neo-cream")
st.write("ดาวน์โหลดไฟล์สรุปหน้าเดียว เปิดในเบราว์เซอร์แล้วกด Ctrl+P เพื่อบันทึกเป็น PDF "
         "หรือแคปหน้าจอส่งได้เลย")
html = _build_onepager_html(meta, avg_kwh, avg_cost, fin_rows, cust[show_cols],
                            has_batt=_has_batt, saving_source=saving_source)
st.download_button("ดาวน์โหลดสรุปหน้าเดียว (HTML)", data=html,
                   file_name="สรุปเสนอลูกค้า.html", mime="text/html")
with st.expander("ดูตัวอย่างก่อนบันทึก"):
    st.components.v1.html(html, height=600, scrolling=True)
card_close()
