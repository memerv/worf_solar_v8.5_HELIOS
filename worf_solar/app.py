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
                      customer_view, recommend_packages, pick_three_solar_sizes,
                      required_system_wp)
from finance import simple_payback, npv, irr, discounted_payback
from tariff import TariffModel
from sim_bridge import simulate_package_savings, _monthly_bill
from optimizer import _infer_dt_hours
from analysis import (day_night_monthly_summary, linear_trend,
                      demand_peak_monthly, estimate_savings_from_monthly,
                      monthly_total_kwh, hourly_avg_profile, solar_hourly_profile)
from quant import (build_hourly_profiles, estimate_growth, monthly_total_kwh_simple,
                   min_sensible_kwp, size_sweep, pick_sweep_options,
                   monte_carlo_payback, score_lead, project_future_kwh)

st.set_page_config(page_title="Solar & Battery — วิเคราะห์การขาย", layout="wide")

NEO_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

:root{
  --ink:#111111;
  /* ธีมสีม่วงอ่อนตาม PEA (จาก palette: #D4BFFB, #8C6EF1, #FF87F5, #EFA9A6)
     พื้นหลังใช้ม่วงอ่อนมากๆ ไม่เข้ม อ่านสบายตา */
  --paper:#F3EEFC;
  --lilac:#D4BFFB;
  --purple:#8C6EF1;
  --mint:#B7F0CE;
  --pink:#F9CBDD;
  --cream:#E9DEFB;
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


def _quant_block(q) -> str:
    """แถบสรุปผลวิเคราะห์เชิงลึก (ขนาดคุ้มสุด + ช่วงคืนทุน) สำหรับหน้าสรุปส่งลูกค้า"""
    if not q or not q.get("opts"):
        return ""
    names = {"floor": "ขั้นต่ำที่สมเหตุสมผล", "best": "คุ้มที่สุด (แนะนำ)",
             "target": "ใกล้เป้าหมายการใช้ไฟ"}
    rows = ""
    for k, r in q["opts"].items():
        mc = q.get("mc", {}).get(k)
        pb = (f'{mc["payback_p10"]:.1f}–{mc["payback_p90"]:.1f} ปี' if mc
              else f'{r["payback_years"]:.1f} ปี')
        brand = str(r.get("inverter_brand") or "-")
        if r.get("battery_brand"):
            brand += f'<br><span style="font-size:11px;color:#555;">แบต {r["battery_brand"]}</span>'
        rows += (f"<tr><td><b>{names.get(k, k)}</b></td>"
                 f"<td>{r['kwp_total']:,.0f} kWp ({int(r['n_units'])} ชุด)</td>"
                 f"<td>{brand}</td>"
                 f"<td>{r['capex']:,.0f} บาท</td>"
                 f"<td>{r['saving_month']:,.0f} บาท/เดือน</td>"
                 f"<td>{pb}</td>"
                 f"<td>{r['self_consumption_ratio']:.0%}</td></tr>")
    g = q.get("growth", {})
    note = ""
    if g:
        note = (f"<p style='font-size:12px;color:#555;'>แนวโน้มการใช้ไฟของลูกค้า "
                f"{g['growth_rate']:+.1%}/ปี ({g.get('method','')}) · "
                f"เป้าหมายเผื่ออนาคต ≈ {q.get('target_kwp',0):,.0f} kWp · "
                f"เปรียบเทียบทั้งหมด {q.get('sweep_n',0)} ตัวเลือก</p>")
    return (f"<h2>ตัวเลือกที่แนะนำ (วิเคราะห์จากการใช้ไฟจริง)</h2>"
            f"<table><thead><tr><th>ตัวเลือก</th><th>ขนาด</th><th>ยี่ห้อ</th>"
            f"<th>เงินลงทุน</th><th>ประหยัด</th><th>คืนทุน (ช่วงที่เป็นไปได้)</th>"
            f"<th>ใช้ไฟโซลาร์เอง</th></tr></thead><tbody>{rows}</tbody></table>{note}"
            f"<p style='font-size:12px;color:#555;'>ช่วงคืนทุนมาจากการสุ่มสมมติฐาน 300 รอบ "
            f"(แดดปีดี/ปีแย่, ค่าไฟขึ้นเร็ว/ช้า, แผงเสื่อม, ค่าดูแลรักษา) "
            f"จึงเป็นช่วงที่เป็นไปได้จริง ไม่ใช่ตัวเลขรับประกัน</p>")


def _usage_profile_block(up) -> str:
    """แถบสรุปพฤติกรรมการใช้ไฟ (เดือนมากสุด/น้อยสุด + ขนาดโซลาร์ที่เหมาะ) สำหรับหน้าสรุป
    up: dict {'hi_label','hi_kwh','lo_label','lo_kwh','target_kwp','sizes':[(name,kwp)...]}
    """
    if not up:
        return ""
    rows = ""
    if up.get("hi_label"):
        rows += (f"<tr><td>เดือนใช้ไฟมากสุด</td><td>{up['hi_label']}</td>"
                 f"<td>{up.get('hi_kwh',0):,.0f} kWh</td></tr>")
    if up.get("lo_label"):
        rows += (f"<tr><td>เดือนใช้ไฟน้อยสุด</td><td>{up['lo_label']}</td>"
                 f"<td>{up.get('lo_kwh',0):,.0f} kWh</td></tr>")
    if up.get("target_kwp"):
        rows += (f"<tr><td>ขนาดระบบที่เหมาะกับการใช้ไฟ</td>"
                 f"<td colspan='2'>≈ {up['target_kwp']:.0f} kWp</td></tr>")
    for name, kwp in up.get("sizes", []):
        rows += f"<tr><td>ตัวเลือกโซลาร์: {name}</td><td colspan='2'>{kwp:.0f} kWp</td></tr>"
    if not rows:
        return ""
    return (f"<h2>พฤติกรรมการใช้ไฟ (จากข้อมูลจริง)</h2>"
            f"<table><tbody>{rows}</tbody></table>")


def _build_onepager_html(meta, avg_kwh, avg_cost, fin_rows, pkg_df, has_batt=True,
                         saving_source="claim", usage_profile=None, quant=None) -> str:
    """สรุปหน้าเดียวส่งลูกค้า (เปิดในเบราว์เซอร์ -> Ctrl+P -> Save as PDF)
    usage_profile: dict ผลวิเคราะห์พฤติกรรม (เดือนมากสุด/น้อยสุด, เป้าหมาย kWp) หรือ None
    """
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
h1{{font-size:1.6rem;border-bottom:4px solid #8C6EF1;padding-bottom:8px;}}
h2{{font-size:1.15rem;margin-top:24px;color:#6B4FC7;}}
.kpis{{display:flex;gap:14px;margin:16px 0;}}
.kpi{{flex:1;border:3px solid #111;border-radius:12px;padding:12px;text-align:center;box-shadow:4px 4px 0 #111;}}
.kpi .n{{font-size:1.4rem;font-weight:700;}}
.kpi .l{{font-size:.8rem;opacity:.7;}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:.8rem;}}
th,td{{border:1px solid #999;padding:6px 8px;text-align:center;}}
th{{background:#D4BFFB;font-weight:600;}}
.note{{font-size:.75rem;color:#777;margin-top:20px;border-top:1px dashed #ccc;padding-top:10px;}}
</style></head><body>
<h1>ข้อเสนอระบบโซลาร์ + {batt_txt}</h1>
<h2>ข้อมูลการใช้ไฟของลูกค้า</h2>
<div class="kpis">
<div class="kpi"><div class="n">{biz}</div><div class="l">{meter}</div></div>
<div class="kpi"><div class="n">{avg_kwh:,.0f}</div><div class="l">หน่วย/เดือน (kWh)</div></div>
<div class="kpi"><div class="n">{cost_txt}</div><div class="l">ค่าไฟเฉลี่ย/เดือน</div></div>
</div>
{_usage_profile_block(usage_profile)}
{_quant_block(quant)}
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
    # เพดานแบตขยายเป็น 300 kWh (เดิม 40) เพื่อรองรับระบบเชิงพาณิชย์ขนาดใหญ่จริง
    # เช่นลูกค้าโหลด 150-200 kW ที่ต้องใช้แบตหลายก้อนรวมกัน
    batt_min_kwh, batt_max_kwh = st.slider("ช่วงความจุแบตที่รับได้ (kWh)", 0, 300, (5, 100))
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

    st.markdown("## 4) การคำนวณผลประหยัด")
    # #1: เลือกให้คำนวณจากข้อมูลจริง (ต้องมี interval data) แทนตัวเลขเคลมจาก catalog
    use_sim = st.checkbox("คำนวณผลประหยัดจากข้อมูลจริงของลูกค้า (จำลอง)", value=True,
                          help="มีไฟล์รายช่วง (interval) = จำลองเต็มรูปแบบ · "
                               "มีแค่บิลรายเดือน = ประเมินเป็นช่วง (range) แทน")
    specific_yield = st.slider("ผลผลิตโซลาร์ (kWh/kWp/วัน)", 3.0, 5.0, 4.5, step=0.1,
                               help="ไทยเฉลี่ย ~4.0-4.8 ขึ้นกับพื้นที่/ทิศทาง/องศาแผง")
    sc_low, sc_high = st.slider(
        "ช่วง Self-consumption ที่คาด (%) — ใช้เฉพาะกรณีมีแค่บิลรายเดือน",
        10, 100, (50, 90), step=5,
        help="สัดส่วนไฟโซลาร์ที่ลูกค้า 'ใช้เอง' — ไม่รู้แน่ถ้าไม่มีโหลดโปรไฟล์ "
             "จึงประเมินผลประหยัดเป็นช่วง ไม่ฟันธงตัวเลขเดียว")

    st.markdown("## 5) เทมเพลตไฟล์ลูกค้า")
    from template_builder import build_template_bytes, build_lead_batch_examples
    st.download_button(
        "ดาวน์โหลดเทมเพลตกรอกข้อมูลลูกค้า (.xlsx)",
        data=build_template_bytes(),
        file_name="เทมเพลตข้อมูลลูกค้า.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="มีตัวอย่างครบทั้งกรณีโหลดโปรไฟล์ 15 นาที และกรณีมีแค่บิลรายเดือน")

# ---- สมมติฐานการเงิน (ค่าคงที่มาตรฐาน — เดิมเป็นสไลเดอร์แต่แทบไม่มีใครปรับ) ----
# ถ้าต้องการเปลี่ยน แก้ตัวเลขตรงนี้ได้เลย
HORIZON_YEARS = 10        # อายุโครงการที่ใช้คิด NPV/IRR (ปี)
ESCALATION = 0.03         # ค่าไฟปรับขึ้นเฉลี่ยต่อปี (3%)
DISCOUNT_RATE = 0.05      # อัตราคิดลด (5%)
MAX_SHOW = 10             # จำนวนแพ็กเกจที่แสดงในตารางแนะนำ
horizon_years, escalation = HORIZON_YEARS, ESCALATION
discount_rate, max_show = DISCOUNT_RATE, MAX_SHOW

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
quant_ctx = {}   # ผลวิเคราะห์เชิงลึก (คำนวณในบล็อก interval ด้านล่าง) ใช้ร่วมกันหลายส่วน
_title_suffix = "แบตเตอรี่" if _has_batt else "ไม่มีแบตเตอรี่"

# โลโก้ PEA Easy D / EZD — ทำด้วยข้อความ+สีตาม palette (ไม่ได้ก็อปไฟล์โลโก้ตราสินค้า)
st.markdown(
    '<div style="display:inline-flex;flex-direction:column;align-items:center;'
    'background:#ffffff;border:3px solid var(--ink);border-radius:16px;'
    'box-shadow:var(--shadow-sm);padding:.6rem 1.4rem;margin-bottom:1rem;">'
    '<div style="font-family:\'Space Grotesk\',sans-serif;font-weight:700;'
    'font-size:1.9rem;line-height:1;letter-spacing:-0.01em;">'
    '<span style="color:#8E2C8E;">PEA</span> '
    '<span style="color:#2AA0DE;">Easy</span> '
    '<span style="color:#7CB82F;">D</span>'
    '<span style="color:#2AA0DE;font-size:1.1rem;vertical-align:super;">&#127760;</span>'
    '</div>'
    '<div style="font-family:\'Space Grotesk\',sans-serif;font-weight:700;'
    'font-size:1rem;letter-spacing:0.25em;margin-top:.15rem;">'
    '<span style="color:#8E2C8E;">E</span>'
    '<span style="color:#2AA0DE;">Z</span>'
    '<span style="color:#7CB82F;">D</span>'
    '</div></div>',
    unsafe_allow_html=True)

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
avg_cost_is_estimate = False
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
        # ลูกค้าที่มีข้อมูลรายช่วงมักกรอกแค่ kWh ไม่มีคอลัมน์ค่าไฟ (บาท) ต่อช่วง
        # ประเมิน "ค่าไฟเฉลี่ย/เดือน" จากโหลดจริง + อัตราค่าไฟ (TOU) ที่ตั้งไว้ในแถบซ้าย
        # แทนที่จะปล่อยว่าง — คำนวณแบบเดียวกับ baseline_bill ในโมดูลจำลอง (ก่อนติดระบบ)
        try:
            idf_ts = idf.copy()
            idf_ts["timestamp"] = pd.to_datetime(idf_ts["timestamp"])
            idf_ts = idf_ts.dropna(subset=["timestamp", "load_kw"]).sort_values("timestamp")
            dt_est = _infer_dt_hours(idf_ts)
            n_days_est = max(1, idf_ts["timestamp"].dt.date.nunique())
            grid_kwh = (idf_ts["load_kw"] * dt_est).tolist()
            avg_cost = _monthly_bill(list(idf_ts["timestamp"]), grid_kwh, tariff_model,
                                     dt_est, n_days_est)
            avg_cost_is_estimate = True
        except Exception:
            avg_cost = 0.0  # เผื่อข้อมูลผิดปกติจนคำนวณไม่ได้ — กลับไปโชว์ "ไม่ระบุ" เหมือนเดิม

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
        sub_lab = "บาท (ประมาณจากอัตราค่าไฟ + โหลดจริง)" if avg_cost_is_estimate else "บาท"
        st.markdown(f'<div class="neo-card neo-pink"><div class="eyebrow">ค่าไฟเฉลี่ย/เดือน</div>'
                    f'<div class="kpi-num">{lab}</div>'
                    f'<div class="kpi-lab">{sub_lab}</div></div>', unsafe_allow_html=True)

    # เกรดความน่าสนใจของลูกค้า (ข้อ4) — ใช้ตัดสินใจว่าควรเข้าไปคุยก่อนไหม
    if bill["mode"] == "interval" and bill["data"] is not None and len(bill["data"]):
        try:
            _lead_prof = build_hourly_profiles(bill["data"])
            _lead_mk = monthly_total_kwh_simple(bill["data"])
            _lead_g = estimate_growth(_lead_mk)["growth_rate"] if len(_lead_mk) >= 3 else 0.0
            lead = score_lead(_lead_prof, avg_kwh, avg_cost, growth_rate=_lead_g)
            _gcolor = {"A": "neo-mint", "B": "neo-cream", "C": "neo-pink"}.get(
                lead["grade"], "neo-cream")
            _gtext = {"A": "น่าสนใจสูง — ควรเข้าไปคุยก่อน",
                      "B": "น่าสนใจปานกลาง",
                      "C": "น่าสนใจน้อย — โซลาร์อาจไม่คุ้มนัก"}.get(lead["grade"], "")
            st.markdown(
                f'<div class="neo-card {_gcolor}" style="margin-top:.8rem;padding:.8rem 1rem;">'
                f'<div class="eyebrow">เกรดความน่าสนใจของลูกค้ารายนี้ (Lead Score)</div>'
                f'<div style="display:flex;align-items:baseline;gap:.8rem;">'
                f'<div class="kpi-num" style="font-size:2.2rem;">{lead["grade"]}</div>'
                f'<div style="font-weight:600;">{lead["score"]:.0f}/100 — {_gtext}</div></div>'
                f'<div class="kpi-lab" style="margin-top:.3rem;">'
                + " · ".join(lead["reasons"]) +
                '</div></div>', unsafe_allow_html=True)
        except Exception:
            pass
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

        # -------------------------------------------------------------------
        # กราฟเทียบพฤติกรรม: โปรไฟล์โหลดเฉลี่ยรายชั่วโมง (เดือนใช้ไฟมากสุด/น้อยสุด)
        # เทียบกับ PV โซลาร์ 3 ขนาด (เล็กสุด/กลาง/ใกล้โหลดจริง) + SOC แบต (ถ้ามี)
        # แทนกราฟ monitor เดิมที่โชว์ได้แค่ช่วงสั้นๆ และต้องเลื่อนสไลเดอร์วัน
        # -------------------------------------------------------------------
        # -------------------------------------------------------------------
        # คำนวณ Quant ก่อนวาดกราฟ เพื่อให้ "ขนาดโซลาร์ในกราฟ" ตรงกับ
        # "3 ตัวเลือกที่แนะนำ" ด้านล่าง (ขั้นต่ำ / คุ้มสุด / ใกล้เป้าหมาย)
        # -------------------------------------------------------------------
        if catalog is not None and len(catalog):
            with st.spinner("กำลังไล่คำนวณทุกขนาดที่ติดตั้งได้จริง..."):
                _prof = build_hourly_profiles(idf)
                _mk = monthly_total_kwh_simple(idf)
                _growth = estimate_growth(_mk)
                _fut_kwh = project_future_kwh(avg_kwh, _growth["growth_rate"],
                                              years_ahead=2.5)
                _minsz = min_sensible_kwp(_prof, specific_yield)
                _target_kwp_q = required_system_wp(_fut_kwh, specific_yield) / 1000.0
                _sweep = size_sweep(catalog, _prof, tariff_model, want_battery=_has_batt,
                                    specific_yield=specific_yield,
                                    horizon_years=int(horizon_years),
                                    discount_rate=discount_rate, escalation=escalation,
                                    max_units=4, avail_area_sqm=(avail_area or None))
                _opts = pick_sweep_options(_sweep, _minsz["kwp"], _target_kwp_q) \
                    if len(_sweep) else {}
            quant_ctx = {"prof": _prof, "growth": _growth, "minsz": _minsz,
                         "opts": _opts, "sweep": _sweep, "target_kwp": _target_kwp_q,
                         "fut_kwh": _fut_kwh, "sweep_n": len(_sweep)}

        mt = monthly_total_kwh(idf)
        if len(mt) >= 1:
            card_open("เทียบโหลดจริงของลูกค้า กับ PV โซลาร์ 3 ขนาด", "neo-mint")
            st.warning("**เส้นโหลด (ชมพู)** = โปรไฟล์เฉลี่ยรายชั่วโมงจากข้อมูลจริงของลูกค้า · "
                       "เส้นโซลาร์และ SOC แบตเป็น **การจำลอง** จากขนาดระบบ ไม่ใช่ค่าติดตั้งจริง")

            # ใช้ "3 ขนาดเดียวกับตัวเลือกที่แนะนำ" (ขั้นต่ำ/คุ้มสุด/ใกล้เป้าหมาย)
            # เพื่อให้กราฟสอดคล้องกับตัวเลขที่เซลเอาไปเสนอจริง
            _qopts = quant_ctx.get("opts") or {}
            size_colors = {"floor": "#5B9E62", "best": "#E8A33D", "target": "#2E5FA3"}
            size_names = {"floor": "ขั้นต่ำที่สมเหตุสมผล", "best": "คุ้มสุด (แนะนำ)",
                          "target": "ใกล้เป้าหมายการใช้ไฟ"}
            solar_sizes = {}
            for _k in ("floor", "best", "target"):
                if _k in _qopts:
                    _r = _qopts[_k]
                    solar_sizes[_k] = {"kwp": float(_r["kwp_total"]),
                                       "batt": float(_r["battery_kwh_total"]),
                                       "n_units": int(_r["n_units"])}
            # สำรอง: ถ้ายังไม่มีผล quant (เช่นไม่มีแคตตาล็อก) ใช้วิธีเดิมจากแคตตาล็อก
            if not solar_sizes and catalog is not None and len(catalog):
                _tw = required_system_wp(avg_kwh, specific_yield)
                _ps = pick_three_solar_sizes(catalog, _tw, want_battery=_has_batt)
                size_colors = {"min": "#5B9E62", "mid": "#E8A33D", "near": "#2E5FA3"}
                size_names = {"min": "โซลาร์ขั้นต่ำ", "mid": "โซลาร์ขนาดกลาง",
                              "near": "โซลาร์ใกล้โหลดจริง"}
                solar_sizes = {k: {"kwp": v["kwp"],
                                   "batt": float(v["row"].get("battery_total_kwh") or 0),
                                   "n_units": 1}
                               for k, v in _ps.items()}

            def _profile_chart(period, title):
                prof = hourly_avg_profile(idf, period)
                fig = go.Figure()
                # โหลดจริงเฉลี่ยรายชั่วโมง (เส้นทึบชมพู)
                fig.add_trace(go.Scatter(
                    x=prof["hour"], y=prof["load_kw"], name="โหลดเฉลี่ยจริง (kW)",
                    mode="lines", line=dict(color="#D14D72", width=3)))
                # PV ตามขนาดที่แนะนำ (วนตามคีย์ที่มีจริง รองรับทั้ง quant และสำรอง)
                for key in solar_sizes:
                    kwp = solar_sizes[key]["kwp"]
                    nu = solar_sizes[key].get("n_units", 1)
                    pv = solar_hourly_profile(kwp, specific_yield)
                    _sfx = f" ({nu} ชุด)" if nu > 1 else ""
                    fig.add_trace(go.Scatter(
                        x=list(range(24)), y=pv,
                        name=f"{size_names.get(key, key)} {kwp:,.0f} kWp{_sfx}",
                        mode="lines", line=dict(color=size_colors.get(key, "#888"),
                                                width=2)))
                # SOC แบต (เส้นประ) — ใช้แบตของตัวเลือก 'คุ้มสุด' เป็นตัวแทน
                _soc_key = ("best" if "best" in solar_sizes
                            else ("near" if "near" in solar_sizes else None))
                if _has_batt and _soc_key:
                    cap = float(solar_sizes[_soc_key].get("batt") or 0)
                    if cap > 0:
                        pv_ref = solar_hourly_profile(solar_sizes[_soc_key]["kwp"],
                                                      specific_yield)
                        soc, soc_series = cap * 0.2, []
                        for h in range(24):
                            _lv = prof["load_kw"].iloc[h]
                            net = pv_ref[h] - (0 if pd.isna(_lv) else float(_lv))
                            soc = min(cap, max(cap * 0.2, soc + net * 1.0))  # dt=1ชม.
                            soc_series.append(soc / cap * 100)
                        fig.add_trace(go.Scatter(
                            x=list(range(24)), y=soc_series,
                            name=f"SOC แบต {cap:,.0f} kWh (%) จำลอง",
                            mode="lines", yaxis="y2",
                            line=dict(color="#111111", width=2, dash="dot")))

                lay = dict(
                    title=dict(text=title, x=0.5, font=dict(size=15)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
                    font=dict(family="Space Grotesk, sans-serif", color="#111"),
                    xaxis=dict(title="ชั่วโมง (0-23 น.)", dtick=3,
                               gridcolor="rgba(17,17,17,0.06)"),
                    yaxis=dict(title="กำลังไฟเฉลี่ย (kW)", rangemode="tozero",
                               gridcolor="rgba(17,17,17,0.08)"),
                    legend=dict(orientation="h", y=-0.22), height=400,
                    margin=dict(l=10, r=10, t=48, b=10))
                if _has_batt and _soc_key and float(
                        solar_sizes[_soc_key].get("batt") or 0) > 0:
                    lay["yaxis2"] = dict(title="SOC (%)", overlaying="y",
                                         side="right", range=[0, 100])
                fig.update_layout(**lay)
                return fig

            hi = mt.loc[mt["total_kwh"].idxmax()]
            lo = mt.loc[mt["total_kwh"].idxmin()]
            # กันเดือนที่ข้อมูลไม่ครบ (เช่น <20 วัน จากไฟล์ที่กรอกตกหล่น) มาเป็น 'เดือนน้อยสุด'
            # เพราะจะทำให้โปรไฟล์เพี้ยน — ใช้เฉพาะเดือนที่มีวันข้อมูลพอสมควร
            mt_full = mt[mt["n_days"] >= 20]
            if len(mt_full) >= 2:
                hi = mt_full.loc[mt_full["total_kwh"].idxmax()]
                lo = mt_full.loc[mt_full["total_kwh"].idxmin()]
                n_incomplete = int((mt["n_days"] < 20).sum())
                if n_incomplete:
                    st.caption(f"⚠️ ข้าม{n_incomplete}เดือนที่ข้อมูลไม่ครบ (<20วัน) "
                               "ในการเลือกเดือนมากสุด/น้อยสุด")
            c_hi, c_lo = st.columns(2)
            with c_hi:
                st.plotly_chart(
                    _profile_chart(hi["month"],
                                   f'เดือนใช้ไฟมากสุด — {hi["month_label"]} '
                                   f'({hi["total_kwh"]:,.0f} kWh)'),
                    use_container_width=True)
            with c_lo:
                st.plotly_chart(
                    _profile_chart(lo["month"],
                                   f'เดือนใช้ไฟน้อยสุด — {lo["month_label"]} '
                                   f'({lo["total_kwh"]:,.0f} kWh)'),
                    use_container_width=True)

            if solar_sizes:
                sz_txt = " · ".join(
                    f"{size_names.get(k, k)} {solar_sizes[k]['kwp']:,.0f} kWp"
                    for k in solar_sizes)
                _tgt_txt = quant_ctx.get("target_kwp") or (
                    required_system_wp(avg_kwh, specific_yield) / 1000.0)
                st.caption(f"เทียบโหลดเฉลี่ยรายชั่วโมงกับขนาดโซลาร์ **ชุดเดียวกับตัวเลือกที่แนะนำ**"
                           f"ด้านล่าง: {sz_txt} (เป้าหมายจากการใช้ไฟ ≈ {_tgt_txt:,.0f} kWp) "
                           "· ช่วงที่เส้นโซลาร์สูงกว่าโหลด = ไฟเหลือไปชาร์จแบต/เหลือทิ้ง "
                           "· ช่วงที่โหลดสูงกว่า = ยังต้องซื้อไฟบางส่วน")
            else:
                st.caption("อัปโหลดแคตตาล็อกเพื่อเทียบกับขนาดโซลาร์จริง")
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
# วิเคราะห์เชิงลึก (Quant) — ไล่ทุกขนาด หาขนาดคุ้มสุด + ช่วงคืนทุนที่น่าเชื่อถือ
# ---------------------------------------------------------------------------
if have_interval and quant_ctx.get("sweep") is not None:
    card_open("วิเคราะห์เชิงลึก — หาขนาดที่คุ้มที่สุด (ไม่ใช่แค่ขนาดที่ใกล้โหลดสุด)", "neo-blue")
    # ใช้ผลที่คำนวณไว้แล้วก่อนวาดกราฟพฤติกรรม (ไม่คำนวณซ้ำ)
    _prof = quant_ctx["prof"]
    _growth = quant_ctx["growth"]
    _fut_kwh = quant_ctx["fut_kwh"]
    _minsz = quant_ctx["minsz"]
    _target_kwp_q = quant_ctx["target_kwp"]
    _sweep = quant_ctx["sweep"]

    if not len(_sweep):
        st.info("ไม่มีแพ็กเกจที่คำนวณได้ (ตรวจสอบแคตตาล็อก/เงื่อนไขแบตเตอรี่)")
        card_close()
    else:
        _opts = quant_ctx["opts"]

        # ---- แถบแนวโน้ม + ขนาดขั้นต่ำ ----
        gcol1, gcol2 = st.columns(2)
        _conf_th = {"high": "เชื่อถือได้สูง", "medium": "ปานกลาง",
                    "low": "ต่ำ (ข้อมูลน้อย)", "none": "ประเมินไม่ได้"}
        with gcol1:
            _g = _growth["growth_rate"]
            _sign = "+" if _g >= 0 else ""
            st.markdown(
                f'<div class="neo-card neo-cream" style="padding:.8rem 1rem;">'
                f'<div class="eyebrow">แนวโน้มการใช้ไฟ (จากข้อมูลลูกค้าเอง)</div>'
                f'<div class="kpi-num" style="font-size:1.6rem;">{_sign}{_g:.1%} <span '
                f'style="font-size:.9rem;font-weight:500;">ต่อปี</span></div>'
                f'<div class="kpi-lab">ความเชื่อมั่น: {_conf_th.get(_growth["confidence"])} '
                f'· {_growth["method"]}</div></div>', unsafe_allow_html=True)
        with gcol2:
            st.markdown(
                f'<div class="neo-card neo-cream" style="padding:.8rem 1rem;">'
                f'<div class="eyebrow">ขนาดขั้นต่ำที่สมเหตุสมผล</div>'
                f'<div class="kpi-num" style="font-size:1.6rem;">{_minsz["kwp"]:,.0f} '
                f'<span style="font-size:.9rem;font-weight:500;">kWp</span></div>'
                f'<div class="kpi-lab">{_minsz["method"]}</div></div>',
                unsafe_allow_html=True)
        st.caption(f"เป้าหมายเผื่ออนาคต 2-3 ปี ≈ **{_target_kwp_q:,.0f} kWp** "
                   f"(จากใช้ไฟ {avg_kwh:,.0f} → {_fut_kwh:,.0f} kWh/เดือน) "
                   "— ระบบประเมินแนวโน้มจากบิลย้อนหลังของลูกค้าเอง ไม่ต้องถามลูกค้าว่าจะขยายกิจการไหม")

        # ---- กราฟ NPV/คืนทุน ต่อขนาด (หัวใจข้อ 3) ----
        _sw1 = _sweep[_sweep["n_units"] == 1]
        figq = make_subplots(specs=[[{"secondary_y": True}]])
        figq.add_trace(go.Scatter(
            x=_sweep["kwp_total"], y=_sweep["npv"], name="NPV (บาท)",
            mode="markers", marker=dict(color="#8C6EF1", size=7,
                                        line=dict(color="#111", width=1))),
            secondary_y=False)
        figq.add_trace(go.Scatter(
            x=_sweep["kwp_total"], y=_sweep["payback_years"], name="คืนทุน (ปี)",
            mode="markers", marker=dict(color="#D14D72", size=6, symbol="diamond")),
            secondary_y=True)
        for _k, _lbl, _c in [("best", "คุ้มสุด (NPV สูงสุด)", "#2E8B57"),
                             ("floor", "ขั้นต่ำสมเหตุสมผล", "#E8A33D"),
                             ("target", "ใกล้เป้าหมายการใช้ไฟ", "#2E5FA3")]:
            if _k in _opts:
                figq.add_vline(x=float(_opts[_k]["kwp_total"]), line_dash="dash",
                               line_color=_c, annotation_text=_lbl,
                               annotation_position="top")
        figq.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.55)",
            font=dict(family="Space Grotesk, sans-serif", color="#111"),
            xaxis=dict(title="ขนาดระบบ (kWp)", gridcolor="rgba(17,17,17,0.06)"),
            legend=dict(orientation="h", y=1.12), height=420,
            margin=dict(l=10, r=10, t=60, b=10))
        figq.update_yaxes(title_text="NPV ตลอดอายุโครงการ (บาท)", secondary_y=False,
                          gridcolor="rgba(17,17,17,0.08)")
        figq.update_yaxes(title_text="ระยะคืนทุน (ปี)", secondary_y=True,
                          rangemode="tozero", showgrid=False)
        st.plotly_chart(figq, use_container_width=True)
        st.caption(f"ไล่คำนวณ **{len(_sweep)} ตัวเลือก** (รวมการติดหลายชุดขนานกัน) "
                   "บนโหลดจริงของลูกค้า · จุดม่วง = NPV (ยิ่งสูงยิ่งดี) · "
                   "จุดชมพู = ระยะคืนทุน (ยิ่งต่ำยิ่งดี) — "
                   "**ขนาดที่คุ้มสุดมักไม่ใช่ขนาดที่ใหญ่ที่สุด** เพราะไฟที่ผลิตเกินโหลดจะเหลือทิ้ง")

        # ---- (3) Monte Carlo: สรุปเป็นช่วง P10-P90 ----
        st.markdown("#### 3 ตัวเลือกที่แนะนำ พร้อมช่วงคืนทุนที่น่าเชื่อถือ")
        _names = {"floor": "ขั้นต่ำที่สมเหตุสมผล", "best": "คุ้มสุด (แนะนำ)",
                  "target": "ใกล้เป้าหมายการใช้ไฟ"}
        _colors = {"floor": "neo-cream", "best": "neo-mint", "target": "neo-blue"}
        _mc_rows = []
        _mc_store = {}
        _ocols = st.columns(len(_opts))
        for _i, (_k, _row) in enumerate(_opts.items()):
            _mc = monte_carlo_payback(_prof, float(_row["kwp_total"]),
                                      float(_row["battery_kwh_total"]),
                                      float(_row["capex"]), tariff_model,
                                      specific_yield=specific_yield, n_draws=300,
                                      horizon_years=int(horizon_years),
                                      discount_rate=discount_rate,
                                      escalation_mean=escalation,
                                      growth_rate=_growth["growth_rate"])
            if _mc:
                _mc_store[_k] = _mc
            with _ocols[_i]:
                _pb = (f'{_mc["payback_p10"]:.1f}–{_mc["payback_p90"]:.1f}'
                       if _mc else f'{_row["payback_years"]:.1f}')
                _brand_txt = str(_row.get("inverter_brand") or "-")
                if _has_batt and _row.get("battery_brand"):
                    _brand_txt += f' / แบต {_row["battery_brand"]}'
                st.markdown(
                    f'<div class="neo-card {_colors[_k]}" style="padding:.9rem 1rem;">'
                    f'<div class="eyebrow">{_names[_k]}</div>'
                    f'<div class="kpi-num" style="font-size:1.7rem;">'
                    f'{_row["kwp_total"]:,.0f} kWp</div>'
                    f'<div class="kpi-lab">'
                    f'{int(_row["n_units"])} ชุด × {_row["kwp_total"]/_row["n_units"]:,.0f} kWp'
                    f'{" · แบต " + format(_row["battery_kwh_total"], ",.0f") + " kWh" if _has_batt else ""}'
                    f'</div>'
                    f'<div class="kpi-lab" style="margin-top:.2rem;font-weight:700;">'
                    f'{_brand_txt}</div>'
                    f'<div style="margin-top:.5rem;font-size:.95rem;line-height:1.7;">'
                    f'ลงทุน <b>{_row["capex"]:,.0f}</b> บาท<br>'
                    f'ประหยัด <b>{_row["saving_month"]:,.0f}</b> บาท/เดือน<br>'
                    f'คืนทุน <b>{_pb} ปี</b><br>'
                    f'ใช้ไฟโซลาร์เอง <b>{_row["self_consumption_ratio"]:.0%}</b>'
                    f'</div></div>', unsafe_allow_html=True)
            if _mc:
                _mc_rows.append({
                    "ตัวเลือก": _names[_k],
                    "ขนาด (kWp)": round(float(_row["kwp_total"]), 1),
                    "จำนวนชุด": int(_row["n_units"]),
                    "ยี่ห้ออินเวอร์เตอร์": _row.get("inverter_brand") or "-",
                    **({"ยี่ห้อแบตเตอรี่": _row.get("battery_brand") or "-"}
                       if _has_batt else {}),
                    "รหัสแพ็กเกจ": _row.get("package_code") or "-",
                    "ลงทุน (บาท)": f'{_row["capex"]:,.0f}',
                    "คืนทุน P10 (เร็ว)": round(_mc["payback_p10"], 1),
                    "คืนทุน P50 (กลาง)": round(_mc["payback_p50"], 1),
                    "คืนทุน P90 (ช้า)": round(_mc["payback_p90"], 1),
                    "โอกาสคืนทุนใน 7 ปี": f'{_mc["prob_payback_under"][7]:.0%}',
                    "NPV กลาง (บาท)": f'{_mc["npv_p50"]:,.0f}',
                })
        if _mc_rows:
            st.dataframe(pd.DataFrame(_mc_rows), use_container_width=True)
            st.caption("ช่วงคืนทุนมาจากการ**สุ่มสมมติฐาน 300 รอบ** (แดดปีดี/ปีแย่ ±10%, "
                       "ค่าไฟขึ้นเร็ว/ช้า, แผงเสื่อม 0.4-0.8%/ปี, ค่าดูแลรักษา 0.5-1.5%/ปี) "
                       "— **P10 = กรณีดี · P90 = กรณีแย่** เสนอลูกค้าเป็นช่วงจะน่าเชื่อถือกว่า"
                       "ตัวเลขเป๊ะที่โดนแย้งง่ายภายหลัง")

        quant_ctx["mc"] = _mc_store
        card_close()

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
    # ใช้ 3 แพ็กตัวแทนตามขนาด: ขั้นต่ำ / กลาง / ใกล้โหลดจริง (ตรงกับ 3 band ในตาราง)
    # ในแต่ละ band เลือกแพ็กที่คุ้มสุด (คืนทุนเร็วสุด) เป็นตัวแทน
    picks, pick_labels = [], []
    if "tier_label" in top.columns:
        for tier in ["ขั้นต่ำ (ลงทุนน้อย)", "ขนาดกลาง", "ใกล้โหลดจริง (เต็มประสิทธิภาพ)"]:
            m = top[top["tier_label"] == tier].dropna(subset=["catalog_price"])
            if len(m):
                # เลือกแพ็กคืนทุนเร็วสุดใน band นี้เป็นตัวแทน
                if "claimed_payback_years" in m.columns and m["claimed_payback_years"].notna().any():
                    m = m.sort_values("claimed_payback_years", na_position="last")
                picks.append(m.iloc[0])
                pick_labels.append(tier.split(" (")[0])
    if not picks:
        # fallback: กระจายตามราคา ถ้าไม่มีป้าย band
        price_sorted = top.dropna(subset=["catalog_price"]).sort_values("catalog_price")
        if len(price_sorted) >= 3:
            picks = [price_sorted.iloc[0], price_sorted.iloc[len(price_sorted)//2],
                     price_sorted.iloc[-1]]
            pick_labels = ["ราคาประหยัดสุด", "ราคากลาง", "สเปกสูงสุด"]
        else:
            picks = [price_sorted.iloc[i] for i in range(len(price_sorted))]
            pick_labels = [f"แพ็ก {i+1}" for i in range(len(picks))]

    colors = ["#5B9E62", "#E8A33D", "#2E5FA3"]
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
# หาลูกค้าเชิงรุก (Lead Scoring แบบหลายราย) — ข้อ4
# ---------------------------------------------------------------------------
card_open("หาลูกค้าเชิงรุก — สแกนหลายรายพร้อมกัน แล้วจัดลำดับ A/B/C", "neo-lilac")
st.write("อัปโหลดไฟล์โหลดโปรไฟล์ของลูกค้าหลายราย ระบบจะให้คะแนนว่ารายไหน "
         "**น่าจะคุ้มโซลาร์มากที่สุด** เพื่อให้ทีมขายเข้าไปคุยกับรายที่ปิดดีลง่ายก่อน "
         "— ใช้กับข้อมูลมิเตอร์ที่ PEA มีอยู่แล้ว ไม่ต้องรอลูกค้าเดินมาหา")
_lc1, _lc2 = st.columns([1, 2])
with _lc1:
    st.download_button(
        "ดาวน์โหลดไฟล์ตัวอย่าง 3 ราย (.zip)",
        data=build_lead_batch_examples(),
        file_name="ตัวอย่างลูกค้าสำหรับสแกน.zip", mime="application/zip",
        help="แตกไฟล์แล้วลากไฟล์ .xlsx ทั้ง 3 ใส่ช่องอัปโหลดด้านล่างได้เลยเพื่อทดลองใช้")
with _lc2:
    st.caption("**1 ไฟล์ = ลูกค้า 1 ราย** (ชื่อไฟล์ = ชื่อลูกค้าในตารางผล) · "
               "ใช้คอลัมน์ชุดเดียวกับเทมเพลตข้อมูลลูกค้า (กรณี A รายช่วง) · "
               "ไฟล์ตัวอย่างมีทั้งโรงงานกลางวัน / สำนักงาน / โรงงานกะกลางคืน "
               "เพื่อให้เห็นความต่างของเกรด")
batch_files = st.file_uploader("ไฟล์โหลดโปรไฟล์ลูกค้า (เลือกได้หลายไฟล์)",
                               type=["xlsx", "xls", "csv"], accept_multiple_files=True,
                               key="batch_leads")
if batch_files:
    with st.spinner(f"กำลังวิเคราะห์ {len(batch_files)} ราย..."):
        _rows = []
        for _f in batch_files:
            _name = _f.name.rsplit(".", 1)[0]
            try:
                _b = parse_customer_bill(_f)
                if _b["mode"] != "interval" or _b["data"] is None or not len(_b["data"]):
                    _rows.append({"ลูกค้า": _name, "เกรด": "-", "คะแนน": 0,
                                  "หมายเหตุ": "ต้องเป็นข้อมูลรายช่วง (15 นาที/ชั่วโมง)"})
                    continue
                _d = _b["data"]
                _p = build_hourly_profiles(_d)
                _a = float(_d["load_kw"].mean()) * 24 * 30
                _m = monthly_total_kwh_simple(_d)
                _gr = estimate_growth(_m)["growth_rate"] if len(_m) >= 3 else 0.0
                _s = score_lead(_p, _a, growth_rate=_gr)
                _rows.append({
                    "ลูกค้า": _name, "เกรด": _s["grade"], "คะแนน": _s["score"],
                    "ใช้ไฟ (kWh/เดือน)": round(_a),
                    "สัดส่วนใช้ไฟกลางวัน": f'{_s.get("day_share", 0):.0%}',
                    "แนวโน้ม/ปี": f'{_gr:+.1%}',
                    "หมายเหตุ": " · ".join(_s["reasons"][:2]),
                })
            except Exception as e:
                _rows.append({"ลูกค้า": _name, "เกรด": "-", "คะแนน": 0,
                              "หมายเหตุ": f"อ่านไฟล์ไม่สำเร็จ: {str(e)[:50]}"})
        _bdf = pd.DataFrame(_rows).sort_values("คะแนน", ascending=False)
    _na = int((_bdf["เกรด"] == "A").sum())
    _nb = int((_bdf["เกรด"] == "B").sum())
    _nc = int((_bdf["เกรด"] == "C").sum())
    b1, b2, b3 = st.columns(3)
    for _c, _lab, _n, _cls in [(b1, "เกรด A — ควรเข้าไปคุยก่อน", _na, "neo-mint"),
                               (b2, "เกรด B — น่าสนใจปานกลาง", _nb, "neo-cream"),
                               (b3, "เกรด C — คุ้มน้อย", _nc, "neo-pink")]:
        with _c:
            st.markdown(f'<div class="neo-card {_cls}" style="padding:.7rem .9rem;">'
                        f'<div class="kpi-lab">{_lab}</div>'
                        f'<div class="kpi-num" style="font-size:1.8rem;">{_n} ราย</div>'
                        f'</div>', unsafe_allow_html=True)
    st.dataframe(_bdf, use_container_width=True)
    st.download_button("ดาวน์โหลดลิสต์ลูกค้า (CSV)",
                       data=_bdf.to_csv(index=False).encode("utf-8-sig"),
                       file_name="ลิสต์ลูกค้าน่าสนใจ.csv", mime="text/csv")
    st.caption("เกณฑ์ให้คะแนน: สัดส่วนใช้ไฟกลางวัน (40) · ขนาดการใช้ไฟ (25) · "
               "ความสม่ำเสมอของโหลดกลางวัน (20) · ใช้ไฟทุกวัน/เฉพาะวันธรรมดา (10) · "
               "แนวโน้มการใช้ไฟโต (5) — เกรด A คือใช้ไฟกลางวันเยอะ สม่ำเสมอ ปริมาณมาก "
               "ซึ่งโซลาร์จะคุ้มที่สุด")
card_close()

# ---------------------------------------------------------------------------
# export one-pager
# ---------------------------------------------------------------------------
card_open("บันทึกสรุปส่งลูกค้า / นำเสนอหัวหน้า", "neo-cream")
st.write("ดาวน์โหลดไฟล์สรุปหน้าเดียว เปิดในเบราว์เซอร์แล้วกด Ctrl+P เพื่อบันทึกเป็น PDF "
         "หรือแคปหน้าจอส่งได้เลย")
# รวบรวมข้อมูลพฤติกรรม (เดือนมากสุด/น้อยสุด + ขนาดโซลาร์ที่เหมาะ) สำหรับหน้าสรุป (ข้อ4)
usage_profile = None
if have_interval:
    try:
        _mt = monthly_total_kwh(bill["data"])
        _mt_full = _mt[_mt["n_days"] >= 20] if len(_mt) else _mt
        _src = _mt_full if len(_mt_full) >= 2 else _mt
        up = {"target_kwp": (rec.get("target_wp") or 0) / 1000.0 or None, "sizes": []}
        if len(_src):
            _hi = _src.loc[_src["total_kwh"].idxmax()]
            _lo = _src.loc[_src["total_kwh"].idxmin()]
            up.update(hi_label=_hi["month_label"], hi_kwh=_hi["total_kwh"],
                      lo_label=_lo["month_label"], lo_kwh=_lo["total_kwh"])
        _sz = pick_three_solar_sizes(catalog, rec.get("target_wp") or 0, want_battery=_has_batt)
        _names = {"min": "ขั้นต่ำ", "mid": "กลาง", "near": "ใกล้โหลดจริง"}
        up["sizes"] = [(_names[k], _sz[k]["kwp"]) for k in ("min", "mid", "near") if k in _sz]
        usage_profile = up
    except Exception:
        usage_profile = None

html = _build_onepager_html(meta, avg_kwh, avg_cost, fin_rows, cust[show_cols],
                            has_batt=_has_batt, saving_source=saving_source,
                            usage_profile=usage_profile, quant=quant_ctx)
st.download_button("ดาวน์โหลดสรุปหน้าเดียว (HTML)", data=html,
                   file_name="สรุปเสนอลูกค้า.html", mime="text/html")
with st.expander("ดูตัวอย่างก่อนบันทึก"):
    st.components.v1.html(html, height=600, scrolling=True)
card_close()
