# =============================================================
# HR Disciplinary Management System — Clean Production v3.9
# =============================================================
# Single-file Streamlit app. SQLite only. No Google Sheets.
# Phases covered:
#   1 – SQLite-only, GSheets fully removed
#   2 – Bug fixes & stability
#   3 – Refactor & cleanup
#   4 – Core features verified
#   5 – Audit trail (submitted_by column)
#   6 – Final clean version
#   7 – ADDED: i18n Bilingual Support (English/Arabic) Toggle
#   8 – ADDED: Manager Overrides (Force Investigation & Custom Deduction)
#   9 – FIXED: Custom deductions now reflect in Emails & DB correctly
#  10 – ADDED: Visual Penalties Guide for HR
#  11 – ADDED: Image Attachment Upload (Stored in DB as Base64 & Emailed)
#  12 – ADDED: Image Viewer Tool in Admin Dashboard to retrieve proofs
#  13 – CHANGED: Export format from CSV to Excel (.xlsx) with Multi-sheets
# =============================================================

import re
import sqlite3
import base64
import io
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import streamlit as st

# Optional Google Sheets support — app works fine if package not installed
try:
    import gspread
    from google.oauth2.service_account import Credentials as _GCPCredentials
    _GSHEETS_AVAILABLE = True
except ImportError:
    _GSHEETS_AVAILABLE = False

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG  (must be the very first Streamlit call)
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Travel Gate — HR System",
    page_icon="✈️",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# BRAND THEME  — Travel Gate (teal #3ECAC0 · orange #F47B3A)
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Font ───────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&family=Inter:wght@400;500;600;700&display=swap');

/* ── Root variables ─────────────────────────────────────────── */
:root {
    --tg-teal:        #3ECAC0;
    --tg-teal-dark:   #2AADA3;
    --tg-teal-light:  #E8FAF9;
    --tg-orange:      #F47B3A;
    --tg-orange-dark: #D9621F;
    --tg-white:       #FFFFFF;
    --tg-bg:          #F5FAFA;
    --tg-card:        #FFFFFF;
    --tg-border:      #D0F0EE;
    --tg-text:        #1C2B2A;
    --tg-muted:       #5E7A78;
    --radius:         10px;
}

/* ── Global reset ───────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Cairo', sans-serif;
    background-color: var(--tg-bg) !important;
    color: var(--tg-text) !important;
}

/* ── Hide default Streamlit chrome ──────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; }

/* ── Top brand bar ──────────────────────────────────────────── */
.tg-topbar {
    background: linear-gradient(135deg, #3ECAC0 0%, #2AADA3 100%);
    padding: 18px 32px;
    border-radius: 0 0 16px 16px;
    margin: -1rem -1rem 1.5rem -1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 20px rgba(62,202,192,.35);
}
.tg-topbar .brand-left { display: flex; align-items: center; gap: 16px; }
.tg-logo-circle {
    width: 52px; height: 52px;
    background: white;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px;
    box-shadow: 0 2px 8px rgba(0,0,0,.15);
}
.tg-brand-name {
    font-family: 'Inter', sans-serif;
    font-weight: 900;
    font-size: 1.5rem;
    color: white;
    letter-spacing: 1px;
    line-height: 1.1;
}
.tg-brand-sub {
    font-family: 'Cairo', sans-serif;
    font-weight: 400;
    font-size: 0.85rem;
    color: rgba(255,255,255,.85);
}
.tg-badge {
    background: var(--tg-orange);
    color: white;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: .5px;
}

/* ── Tabs ───────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: var(--tg-card);
    border-radius: var(--radius);
    padding: 6px;
    border: 1px solid var(--tg-border);
    box-shadow: 0 2px 8px rgba(62,202,192,.1);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 10px 24px;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--tg-muted) !important;
    background: transparent !important;
    border: none !important;
    transition: all .2s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--tg-teal) !important;
    background: var(--tg-teal-light) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, var(--tg-teal) 0%, var(--tg-teal-dark) 100%) !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(62,202,192,.4);
}
.stTabs [data-baseweb="tab-highlight"] { display: none; }
.stTabs [data-baseweb="tab-border"]    { display: none; }

/* ── Buttons ────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, var(--tg-teal) 0%, var(--tg-teal-dark) 100%);
    color: white !important;
    border: none;
    border-radius: 8px;
    padding: 10px 22px;
    font-weight: 600;
    font-size: 0.9rem;
    box-shadow: 0 3px 10px rgba(62,202,192,.35);
    transition: all .2s ease;
    cursor: pointer;
}
.stButton > button:hover {
    background: linear-gradient(135deg, var(--tg-teal-dark) 0%, #1F8F87 100%);
    box-shadow: 0 5px 16px rgba(62,202,192,.5);
    transform: translateY(-1px);
}
.stButton > button:active { transform: translateY(0); }

/* Submit / primary action button (full-width) */
div[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, var(--tg-orange) 0%, var(--tg-orange-dark) 100%) !important;
    box-shadow: 0 4px 14px rgba(244,123,58,.4) !important;
    width: 100%;
    font-size: 1rem;
    padding: 14px 22px;
    border-radius: 10px;
}
div[data-testid="stFormSubmitButton"] > button:hover {
    box-shadow: 0 6px 20px rgba(244,123,58,.55) !important;
    transform: translateY(-2px);
}

/* ── Metric cards (KPI row) ─────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--tg-card);
    border: 1px solid var(--tg-border);
    border-top: 4px solid var(--tg-teal);
    border-radius: var(--radius);
    padding: 16px 20px;
    box-shadow: 0 2px 8px rgba(62,202,192,.1);
}
[data-testid="stMetric"] label {
    color: var(--tg-muted) !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: .5px;
}
[data-testid="stMetricValue"] {
    color: var(--tg-teal-dark) !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
}

/* ── Text inputs & selects ──────────────────────────────────── */
input, textarea, select,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] {
    border-radius: 8px !important;
    border-color: var(--tg-border) !important;
    background: white !important;
    transition: border-color .2s ease, box-shadow .2s ease;
}
input:focus, textarea:focus {
    border-color: var(--tg-teal) !important;
    box-shadow: 0 0 0 3px rgba(62,202,192,.2) !important;
    outline: none !important;
}

/* ── Expanders ──────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--tg-card);
    border: 1px solid var(--tg-border) !important;
    border-radius: var(--radius) !important;
    box-shadow: 0 2px 6px rgba(62,202,192,.07);
}
[data-testid="stExpander"] summary {
    font-weight: 600;
    color: var(--tg-teal-dark) !important;
    padding: 12px 16px;
}
[data-testid="stExpander"] summary:hover { color: var(--tg-teal) !important; }

/* ── Alerts ─────────────────────────────────────────────────── */
[data-testid="stAlert"][kind="info"]    { background: #E8FAF9; border-color: var(--tg-teal); }
[data-testid="stAlert"][kind="success"] { background: #EAFAF1; border-color: #27AE60; }
[data-testid="stAlert"][kind="warning"] { background: #FFF4EC; border-color: var(--tg-orange); }
[data-testid="stAlert"][kind="error"]   { background: #FDEDED; border-color: #C0392B; }

/* ── Dataframes ─────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--radius) !important;
    overflow: hidden;
    border: 1px solid var(--tg-border) !important;
    box-shadow: 0 2px 8px rgba(62,202,192,.08);
}
[data-testid="stDataFrame"] thead tr th {
    background: linear-gradient(135deg, var(--tg-teal) 0%, var(--tg-teal-dark) 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    font-size: 0.82rem !important;
    letter-spacing: .4px;
}

/* ── Form containers ────────────────────────────────────────── */
[data-testid="stForm"] {
    background: var(--tg-card);
    border: 1px solid var(--tg-border);
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 2px 10px rgba(62,202,192,.08);
}

/* ── Dividers ───────────────────────────────────────────────── */
hr { border-color: var(--tg-border) !important; }

/* ── Section headings ───────────────────────────────────────── */
h1 { color: var(--tg-teal-dark) !important; font-weight: 800 !important; }
h2 { color: var(--tg-teal-dark) !important; font-weight: 700 !important; font-size: 1.25rem !important; }
h3 { color: var(--tg-teal-dark) !important; font-weight: 600 !important; }

/* ── Download button ────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #2ECC71 0%, #27AE60 100%) !important;
    box-shadow: 0 4px 12px rgba(46,204,113,.35) !important;
}

/* ── Selectbox ──────────────────────────────────────────────── */
[data-baseweb="select"] > div {
    border-radius: 8px !important;
    border-color: var(--tg-border) !important;
    background: white !important;
}

/* ── Checkbox ───────────────────────────────────────────────── */
[data-baseweb="checkbox"] span[aria-checked="true"] > div {
    background: var(--tg-teal) !important;
    border-color: var(--tg-teal) !important;
}

/* ── Number input ───────────────────────────────────────────── */
[data-testid="stNumberInput"] button {
    background: var(--tg-teal-light) !important;
    color: var(--tg-teal-dark) !important;
    border-color: var(--tg-border) !important;
}

/* ── File uploader ──────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: var(--tg-teal-light) !important;
    border: 2px dashed var(--tg-teal) !important;
    border-radius: var(--radius) !important;
    padding: 12px !important;
}

/* ── Plotly charts ──────────────────────────────────────────── */
.js-plotly-plot .plotly .modebar { display: none; }

/* ── Scrollbar ──────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--tg-teal-light); }
::-webkit-scrollbar-thumb { background: var(--tg-teal); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--tg-teal-dark); }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# I18N TRANSLATION DICTIONARY & HELPERS
# ─────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state.lang = "en"

ARABIC_DICT = {
    # General UI
    "HR Disciplinary System": "نظام إدارة الإنذارات الإدارية",
    "HR Disciplinary Management System": "نظام إدارة الإنذارات والمخالفات",
    "📝 Log Violation": "📝 تسجيل مخالفة",
    "⚙️ Admin Dashboard": "⚙️ لوحة الإدارة",
    "📊 Reports & Analytics": "📊 التقارير والإحصائيات",
    "Password": "كلمة المرور",
    "Login": "تسجيل الدخول",
    "Logout": "تسجيل الخروج",
    "❌ Incorrect password.": "❌ كلمة المرور غير صحيحة.",
    "### 🔑 HR Access Required": "### 🔑 مطلوب صلاحيات الموارد البشرية",
    
    # Tab 1: Log Violation
    "⚠️ No employees found. Please add employees in the **Admin Dashboard** tab first.": "⚠️ لم يتم العثور على موظفين. برجاء إضافة موظفين من لوحة الإدارة أولاً.",
    "Register New Violation": "تسجيل مخالفة جديدة",
    "Violation Category": "تصنيف المخالفة",
    "Incident Type": "نوع الخطأ",
    "ℹ️ Incident Reference": "ℹ️ مرجع الخطأ",
    "**Details:**": "**التفاصيل:**",
    "**Reset Window:**": "**فترة السماح:**",
    "days": "أيام",
    "**Max Steps:**": "**الحد الأقصى:**",
    "📌 **HR Note:**": "📌 **ملاحظة HR:**",
    "**Escalation path:**": "**مسار التصعيد:**",
    "Penalties Guide (Default Deductions):": "دليل العقوبات (الخصم الافتراضي للنظام):",
    "Employee *": "الموظف *",
    "HR Representative Name *": "اسم ممثل الـ HR (المدخل) *",
    "HR Comments / Alignment Notes": "ملاحظات الإدارة / تفاصيل الموقف",
    "Attach Proof Image (Optional)": "إرفاق صورة إثبات (اختياري)",
    "✅ Submit & Notify": "✅ إرسال الإشعار وتسجيل العقوبة",
    "⚠️ **HR Representative Name** is required. This field is the system's audit trail.": "⚠️ **اسم ممثل الـ HR** مطلوب (مهم لسجل التدقيق).",
    "🚨 **INVESTIGATION TRIGGERED** \nThe employee must be suspended immediately. Escalate to the HR Director and do **not** allow the employee on-site.": "🚨 **تم تفعيل التحقيق** \nيجب إيقاف الموظف فوراً وإبلاغ مدير الموارد البشرية، وعدم السماح له بالتواجد في مقر العمل.",
    "💰 **Payroll:**": "💰 **الرواتب:**",
    "day(s) deduction": "يوم خصم",
    "must be applied.": "يجب أن تُطبق.",
    "🔒 **Promotion freeze** active until **": "🔒 **تجميد ترقية** نشط حتى **",
    "months).": "شهور).",
    
    # OVERRIDES
    "🚨 Force Direct Investigation (Bypass Escalation)": "🚨 تحويل مباشر للتحقيق (تخطي السلم)",
    "Deduction Days Override (Optional)": "تعديل أيام الخصم يدوياً (اختياري)",
    "Leave as -1.0 to use default system calculation.": "اتركه على -1.0 لتطبيق الخصم الافتراضي للنظام.",

    # Tab 2: Admin
    "👥 Employee Management": "👥 إدارة الموظفين",
    "Full Name *": "الاسم الكامل *",
    "Email Address *": "البريد الإلكتروني *",
    "Department": "القسم",
    "Manager Email (CC on penalties)": "إيميل المدير المباشر (لإرسال CC)",
    "💾 Save Employee": "💾 حفظ بيانات الموظف",
    "⚠️ Name and Email are required.": "⚠️ الاسم والبريد الإلكتروني مطلوبان.",
    "✅ Employee": "✅ الموظف",
    "saved.": "تم حفظه.",
    "Select employee to remove:": "اختر الموظف لإزالته:",
    "— select —": "— اختر —",
    "🗑️ Delete Employee": "🗑️ حذف الموظف",
    "removed.": "تمت إزالته.",
    "No employees yet. Use the form above to add one.": "لا يوجد موظفين بعد. استخدم النموذج أعلاه للإضافة.",
    "🗂️ Violation Records": "🗂️ سجلات المخالفات",
    "Select Record ID to delete:": "اختر رقم السجل للحذف:",
    "🗑️ Delete Violation Record": "🗑️ حذف السجل نهائياً",
    "Record": "سجل",
    "deleted.": "تم حذفه.",
    "No violations logged yet.": "لم يتم تسجيل أي مخالفات بعد.",
    # Image Viewer UI
    "🖼️ View Proof Image": "🖼️ عرض صورة الإثبات",
    "Select Record ID to view proof:": "اختر رقم السجل لعرض الصورة:",
    "👁️ View Image": "👁️ عرض الصورة",
    "No image attached to this record.": "لا توجد صورة مرفقة مع هذا السجل.",
    "Proof for Record ID:": "صورة الإثبات للسجل رقم:",

    # Tab 3: Reports
    "📊 HR Reports & Analytics": "📊 تقارير وإحصائيات الموارد البشرية",
    "🔍 Filters": "🔍 الفلاتر والبحث",
    "Employee Name": "اسم الموظف",
    "From": "من تاريخ",
    "To": "إلى تاريخ",
    "Penalty Level": "مستوى العقوبة",
    "All": "الكل",
    "⚠️ 'From' date must be before or equal to 'To' date.": "⚠️ تاريخ 'من' يجب أن يكون قبل أو يساوي تاريخ 'إلى'.",
    "ℹ️ No violations match the selected filters.": "ℹ️ لا توجد مخالفات تطابق الفلاتر المحددة.",
    "Total Violations": "إجمالي المخالفات",
    "Unique Employees": "الموظفين المخالفين",
    "Total Deduction Days": "إجمالي أيام الخصم",
    "Active Promotion Freezes": "حالات التجميد النشطة",
    "Violations by Category": "المخالفات حسب التصنيف",
    "Violations per Employee": "المخالفات لكل موظف",
    "📅 Violations Over Time": "📅 معدل المخالفات الزمني",
    "Daily Violation Count": "عدد المخالفات اليومي",
    "Date": "التاريخ",
    "Violations": "المخالفات",
    "Violations by Penalty Level": "حسب مستوى العقوبة",
    "Top 10 Incidents": "أكثر 10 أخطاء شيوعاً",
    "📋 Violation History — Full Detail": "📋 السجل الكامل للمخالفات",
    "Employee": "الموظف",
    "Category": "التصنيف",
    "Incident": "الخطأ",
    "Penalty": "العقوبة",
    "Penalty Description": "وصف العقوبة",
    "Deduction (hrs)": "خصم (ساعات)",
    "Deduction (days)": "خصم (أيام)",
    "Freeze Until": "مجمد حتى",
    "Currently Frozen": "حالة التجميد",
    "Submitted By": "أُدخلت بواسطة (HR)",
    "Date & Time": "التاريخ والوقت",
    "💰 Payroll Deduction Summary": "💰 ملخص خصومات الرواتب",
    "Count": "العدد",
    "Active Freeze": "تجميد نشط",
    "📥 Export Filtered Report (Excel)": "📥 تصدير التقرير (إكسيل)",
    "Yes": "نعم",
    "No": "لا",

    # Categories & Incidents
    "Attendance & Adherence": "الحضور والالتزام",
    "Personal Attitude": "السلوك الشخصي",
    "Abusing": "إساءة الاستخدام",
    "Policy Violations": "مخالفة السياسات",
    "Late Arrival": "التأخير عن موعد العمل",
    "No-Show": "الغياب بدون إذن",
    "Exceed Breaks": "تجاوز وقت الراحة المسموح",
    "Unscheduled Breaks": "أخذ راحات غير مجدولة",
    "Out-of-Hours Attendance": "البقاء في العمل خارج المواعيد",
    "Attendance Manipulation": "التلاعب في بصمة الحضور",
    "Early Leave": "الانصراف المبكر",
    "Use of Abusive Words": "استخدام ألفاظ مسيئة",
    "Physical Harm": "الإيذاء البدني",
    "Sleeping on the Job": "النوم أثناء العمل",
    "Unprofessional Behaviour": "سلوك غير مهني",
    "Company Assets": "إساءة استخدام ممتلكات الشركة",
    "Routing Calls / Tickets": "توجيه خاطئ للعمل/التذاكر",
    "Releasing Calls / Tickets": "إغلاق العمل بدون إنجاز",
    "Using Colleague Logins": "استخدام حساب زميل",
    "Aux System Abuse": "إساءة استخدام أنظمة العمل",
    "Refusing Medical Examination": "رفض الكشف الطبي",
    "Unauthorised Visitors": "استقبال زوار بدون إذن",
    "Smoking in Prohibited Areas": "التدخين في أماكن ممنوعة",
    "Alcohol / Drug Influence": "تحت تأثير الكحول/المخدرات",
    "Harassment": "التحرش أو المضايقة",
    "Theft": "السرقة",
    "Social Media Misuse": "إساءة استخدام السوشيال ميديا",
    "Data Confidentiality Breach": "اختراق سرية البيانات",
    "Personal Mobile Phone Use": "استخدام الهاتف الشخصي بالعمل",
    "Food & Beverage in Prohibited Areas": "الأكل/الشرب في أماكن ممنوعة",
    "Business Process Failure": "مخالفة إجراءات العمل",
    "End-User Critical Failure": "خطأ فادح مع العميل",
    "Cyber Security Breach": "اختراق أمن المعلومات",

    # Penalty Levels
    "Yellow": "أصفر",
    "Orange": "برتقالي",
    "Red": "أحمر",
    "Black": "أسود",
    "Investigation": "تحقيق",
    "Performance Notice": "إشعار أداء",
    "Performance Flag — 4.5 hrs (Half Day) Deduction": "لفت نظر — خصم نصف يوم (4.5 ساعات)",
    "Performance Alert — 2 Days Deduction": "إنذار أداء — خصم يومين",
    "Performance Warning — 4 Days Deduction + 3-Month Freeze": "تحذير نهائي — خصم 4 أيام + تجميد 3 شهور",
    "Suspended — Transferred to Investigation on Spot": "إيقاف — تحويل للتحقيق الفوري",

    # Tab 4: Rules Management
    "📜 Rules Management": "📜 إدارة القواعد",
    "📜 Rules & Escalation Management": "📜 إدارة القواعد والتصعيد",
    "Add, edit, or delete violation rules. Changes take effect immediately on new violations.": "إضافة أو تعديل أو حذف قواعد المخالفات. التغييرات تسري فوراً على المخالفات الجديدة.",
    "Current Rules": "القواعد الحالية",
    "Description": "الوصف",
    "Reset (days)": "فترة السماح (أيام)",
    "Escalation Path": "مسار التصعيد",
    "Select Rule ID to delete:": "اختر رقم القاعدة للحذف:",
    "🗑️ Delete Rule": "🗑️ حذف القاعدة",
    "Rule": "القاعدة",
    "Select Rule ID to edit:": "اختر رقم القاعدة للتعديل:",
    "✏️ Load Rule for Editing": "✏️ تحميل القاعدة للتعديل",
    "No rules configured yet. Use the form below to add the first rule.": "لا توجد قواعد بعد. استخدم النموذج أدناه لإضافة أول قاعدة.",
    "Edit Rule": "تعديل القاعدة",
    "Add New Rule": "إضافة قاعدة جديدة",
    "Rule not found. It may have been deleted.": "لم يتم العثور على القاعدة. ربما تم حذفها.",
    "Category *": "التصنيف *",
    "Incident Name *": "اسم المخالفة *",
    "Reset Period (days) *": "فترة السماح (أيام) *",
    "HR Note (Optional)": "ملاحظة HR (اختياري)",
    "Escalation Path": "مسار التصعيد",
    "Select penalty levels in order (1st offense → last)": "اختر مستويات العقوبة بالترتيب (أول مخالفة ← آخر مخالفة)",
    "Number of escalation steps": "عدد مراحل التصعيد",
    "💾 Save Rule": "💾 حفظ القاعدة",
    "💾 Update Rule": "💾 تحديث القاعدة",
    "Category is required.": "التصنيف مطلوب.",
    "Incident Name is required.": "اسم المخالفة مطلوب.",
    "At least one escalation step is required.": "مطلوب مرحلة تصعيد واحدة على الأقل.",
    "Rule updated successfully.": "تم تحديث القاعدة بنجاح.",
    "Rule added successfully.": "تمت إضافة القاعدة بنجاح.",
    "❌ Cancel Editing": "❌ إلغاء التعديل",
    "⚠️ No rules configured. Please add rules in the **Rules Management** tab first.": "⚠️ لا توجد قواعد. يرجى إضافة قواعد من تبويب **إدارة القواعد** أولاً.",
}

def _t(text: str) -> str:
    """Return the translated string if Arabic is selected, else original."""
    if not isinstance(text, str):
        return text
    if st.session_state.lang == "en":
        return text
        
    # Catch dynamic override string for Arabic translation
    if "Days Deduction (Override)" in text:
        try:
            color_part = text.split(" Card — ")[0]
            days_part = text.split(" Card — ")[1].split(" ")[0]
            color_ar = ARABIC_DICT.get(color_part, color_part)
            return f"إنذار {color_ar} — خصم {days_part} أيام (تعديل يدوي)"
        except (IndexError, ValueError, AttributeError):
            pass  # Fallback to untranslated string
            
    return ARABIC_DICT.get(text, text)

# ── Brand top-bar with language toggle ──────────────────────
_lang_label = "🌐 عربي" if st.session_state.lang == "en" else "🌐 EN"
_sys_label  = "نظام إدارة الإنذارات" if st.session_state.lang == "ar" else "HR Disciplinary System"

_tb_col, _btn_col = st.columns([11, 1])
with _tb_col:
    st.markdown(f"""
    <div class="tg-topbar">
        <div class="brand-left">
            <div class="tg-logo-circle">✈️</div>
            <div>
                <div class="tg-brand-name">TRAVEL GATE</div>
                <div class="tg-brand-sub">ترزل جيت للسفر و السياحة &nbsp;|&nbsp; {_sys_label}</div>
            </div>
        </div>
        <div class="tg-badge">⚖️ Disciplinary Portal</div>
    </div>
    """, unsafe_allow_html=True)
with _btn_col:
    st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
    if st.button(_lang_label, use_container_width=True, key="lang_toggle"):
        st.session_state.lang = "ar" if st.session_state.lang == "en" else "en"
        st.rerun()

# =============================================================
# SECTION 1 — CONSTANTS & CONFIGURATION
# =============================================================

PENALTY_MAP: dict[str, dict] = {
    "Yellow": {
        "label":           "Performance Notice",
        "deduction_hours": 0.0,
        "deduction_days":  0.0,
        "freeze_months":   0,
        "badge":           "🟡",
    },
    "Orange": {
        "label":           "Performance Flag — 4.5 hrs (Half Day) Deduction",
        "deduction_hours": 4.5,
        "deduction_days":  0.5,
        "freeze_months":   0,
        "badge":           "🟠",
    },
    "Red": {
        "label":           "Performance Alert — 2 Days Deduction",
        "deduction_hours": 0.0,
        "deduction_days":  2.0,
        "freeze_months":   0,
        "badge":           "🔴",
    },
    "Black": {
        "label":           "Performance Warning — 4 Days Deduction + 3-Month Freeze",
        "deduction_hours": 0.0,
        "deduction_days":  4.0,
        "freeze_months":   3,
        "badge":           "⬛",
    },
    "Investigation": {
        "label":           "Suspended — Transferred to Investigation on Spot",
        "deduction_hours": 0.0,
        "deduction_days":  0.0,
        "freeze_months":   0,
        "badge":           "🔍",
    },
}

MATRIX_DATA: dict[str, dict] = {
    "Attendance & Adherence": {
        "Late Arrival": {
            "reset": 30,
            "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"],
            "details": "Arriving late to work.",
            "hr_note": "Time deduction required. Manager alignment is mandatory; "
                       "failure to align escalates to the next level.",
        },
        "No-Show": {
            "reset": 90,
            "escalation": ["Red", "Red", "Black", "Investigation"],
            "details": "Missing a scheduled shift without prior notification.",
        },
        "Exceed Breaks": {
            "reset": 30,
            "escalation": [
                "Yellow", "Yellow", "Yellow", "Yellow",
                "Orange", "Red", "Black", "Investigation",
            ],
            "details": "Taking longer breaks than the permitted duration.",
        },
        "Unscheduled Breaks": {
            "reset": 30,
            "escalation": ["Yellow", "Red", "Black", "Investigation"],
            "details": "Taking breaks at unauthorised times.",
        },
        "Out-of-Hours Attendance": {
            "reset": 90,
            "escalation": ["Yellow", "Red", "Black", "Investigation"],
            "details": "Remaining in the workplace beyond the end of a shift without approval.",
        },
        "Attendance Manipulation": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Falsifying or manipulating attendance records.",
        },
        "Early Leave": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Leaving work before end of shift without approval.",
        },
    },
    "Personal Attitude": {
        "Use of Abusive Words": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Using offensive or disrespectful language.",
        },
        "Physical Harm": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Causing physical harm to any person on company premises.",
        },
        "Sleeping on the Job": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Sleeping in the workplace during working hours.",
        },
        "Unprofessional Behaviour": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Conduct that is inappropriate for a professional workplace.",
        },
    },
    "Abusing": {
        "Company Assets": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Damaging or misusing company property.",
        },
        "Routing Calls / Tickets": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Avoiding or incorrectly redirecting assigned calls or tickets.",
        },
        "Releasing Calls / Tickets": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Closing assigned work items without completing them.",
        },
        "Using Colleague Logins": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Sharing or using another employee's login credentials.",
        },
        "Aux System Abuse": {
            "reset": 30,
            "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"],
            "details": "Misusing auxiliary systems, reports, or tools.",
        },
    },
    "Policy Violations": {
        "Refusing Medical Examination": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Refusing to undergo a required medical examination.",
        },
        "Unauthorised Visitors": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Meeting personal visitors in unauthorised areas.",
        },
        "Smoking in Prohibited Areas": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Smoking in areas where it is strictly prohibited.",
        },
        "Alcohol / Drug Influence": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Being under the influence of alcohol or drugs at work.",
        },
        "Harassment": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Engaging in any form of harassment towards colleagues or customers.",
        },
        "Theft": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Taking company or personal property without permission.",
        },
        "Social Media Misuse": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Using social media in a way that damages the company's reputation.",
        },
        "Data Confidentiality Breach": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Unauthorised data sharing, unethical conduct, or actions causing reputational damage.",
        },
        "Personal Mobile Phone Use": {
            "reset": 30,
            "escalation": ["Red", "Black", "Investigation"],
            "details": "Using personal mobile phones for non-work purposes during working hours.",
        },
        "Food & Beverage in Prohibited Areas": {
            "reset": 30,
            "escalation": ["Orange", "Red", "Black", "Investigation"],
            "details": "Eating or drinking in areas where it is not permitted.",
        },
        "Business Process Failure": {
            "reset": 30,
            "escalation": ["Orange", "Red", "Black", "Investigation"],
            "details": "Repeated or severe violation of a critical business process.",
        },
        "End-User Critical Failure": {
            "reset": 60,
            "escalation": ["Black", "Investigation"],
            "details": "Severe failure directly impacting end-users (e.g. payouts, customer attitude).",
        },
        "Cyber Security Breach": {
            "reset": 30,
            "escalation": ["Red", "Black", "Investigation"],
            "details": "Downloading unauthorised software, bypassing security, or sharing restricted links.",
        },
    },
}

def _secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return default

SENDER_EMAIL      = _secret("EMAIL")
SENDER_PASSWORD   = _secret("PASSWORD")
HR_MANAGER_EMAIL  = _secret("HR_MANAGER_EMAIL", SENDER_EMAIL)
HR_ADMIN_PASSWORD = _secret("HR_ADMIN_PASSWORD")
if not HR_ADMIN_PASSWORD:
    st.error(
        "⚠️ HR_ADMIN_PASSWORD is not configured in secrets.toml. "
        "Admin and Reports access is disabled until it is set."
    )
    HR_ADMIN_PASSWORD = "__UNSET__"   # ensures login always fails safely

# Google Sheets (optional backup)
GSHEETS_SPREADSHEET_ID = _secret("GSHEETS_SPREADSHEET_ID")

def _gcp_service_account_info() -> dict | None:
    """Return the [gcp_service_account] table from secrets, or None if absent."""
    try:
        return dict(st.secrets["gcp_service_account"])
    except (KeyError, FileNotFoundError):
        return None


# =============================================================
# SECTION 2 — DATABASE LAYER  (SQLite only)
# =============================================================

DB_FILE = "hr_system.db"

@contextmanager
def _db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")       # allow concurrent reads during writes
    conn.execute("PRAGMA busy_timeout=5000")      # retry up to 5 s on locked DB
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    UNIQUE NOT NULL,
                email         TEXT    NOT NULL,
                department    TEXT    DEFAULT '',
                manager_email TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS violations (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                employee_name   TEXT     NOT NULL,
                category        TEXT     NOT NULL,
                incident        TEXT     NOT NULL,
                penalty_color   TEXT     NOT NULL,
                penalty_label   TEXT     NOT NULL,
                deduction_hours REAL     DEFAULT 0.0,
                deduction_days  REAL     DEFAULT 0.0,
                freeze_months   INTEGER  DEFAULT 0,
                comment         TEXT     DEFAULT '',
                submitted_by    TEXT     NOT NULL DEFAULT '',
                proof_image     TEXT     NOT NULL DEFAULT '',
                created_at      DATETIME NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_vio_employee ON violations(employee_name);
            CREATE INDEX IF NOT EXISTS idx_vio_created  ON violations(created_at);
            CREATE INDEX IF NOT EXISTS idx_vio_incident ON violations(incident);
            CREATE INDEX IF NOT EXISTS idx_vio_penalty  ON violations(penalty_color);

            CREATE TABLE IF NOT EXISTS rules (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                category         TEXT    NOT NULL,
                incident         TEXT    NOT NULL,
                description      TEXT    DEFAULT '',
                hr_note          TEXT    DEFAULT '',
                reset_days       INTEGER NOT NULL DEFAULT 30,
                escalation_json  TEXT    NOT NULL DEFAULT '["Yellow"]',
                UNIQUE(category, incident)
            );
        """)

        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(violations)")}
        
        if "submitted_by" not in existing_cols:
            conn.execute("ALTER TABLE violations ADD COLUMN submitted_by TEXT NOT NULL DEFAULT ''")
            
        if "proof_image" not in existing_cols:
            conn.execute("ALTER TABLE violations ADD COLUMN proof_image TEXT NOT NULL DEFAULT ''")

        col_types = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(violations)")}
        if col_types.get("deduction_days", "REAL") == "INTEGER":
            conn.executescript("""
                ALTER TABLE violations RENAME TO violations_v1;

                CREATE TABLE violations (
                    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                    employee_name   TEXT     NOT NULL,
                    category        TEXT     NOT NULL,
                    incident        TEXT     NOT NULL,
                    penalty_color   TEXT     NOT NULL,
                    penalty_label   TEXT     NOT NULL,
                    deduction_hours REAL     DEFAULT 0.0,
                    deduction_days  REAL     DEFAULT 0.0,
                    freeze_months   INTEGER  DEFAULT 0,
                    comment         TEXT     DEFAULT '',
                    submitted_by    TEXT     NOT NULL DEFAULT '',
                    proof_image     TEXT     NOT NULL DEFAULT '',
                    created_at      DATETIME NOT NULL
                );

                INSERT INTO violations
                SELECT
                    id, employee_name, category, incident,
                    penalty_color, penalty_label,
                    CAST(deduction_hours AS REAL),
                    CAST(deduction_days  AS REAL),
                    freeze_months, comment,
                    COALESCE(submitted_by, ''),
                    COALESCE(proof_image, ''),
                    created_at
                FROM violations_v1;

                DROP TABLE violations_v1;
            """)

        # Seed rules table from MATRIX_DATA if empty (first run only)
        count = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
        if count == 0:
            import json as _json
            for cat, incidents in MATRIX_DATA.items():
                for inc_name, meta in incidents.items():
                    conn.execute(
                        """INSERT OR IGNORE INTO rules
                           (category, incident, description, hr_note, reset_days, escalation_json)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            cat, inc_name,
                            meta.get("details", ""),
                            meta.get("hr_note", ""),
                            meta["reset"],
                            _json.dumps(meta["escalation"]),
                        ),
                    )


# ── Rules CRUD ────────────────────────────────────────────────

import json as _json   # noqa: E402  (needed for escalation_json serialisation)

def get_rules() -> pd.DataFrame:
    with _db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM rules ORDER BY category, incident", conn
        )

def get_matrix_from_rules() -> dict[str, dict]:
    """Build MATRIX_DATA-format dict from the rules table."""
    matrix: dict[str, dict] = {}
    with _db() as conn:
        rows = conn.execute("SELECT * FROM rules ORDER BY category, incident").fetchall()
    for r in rows:
        cat = r["category"]
        inc = r["incident"]
        matrix.setdefault(cat, {})[inc] = {
            "reset":      r["reset_days"],
            "escalation": _json.loads(r["escalation_json"]),
            "details":    r["description"] or "",
            "hr_note":    r["hr_note"] or "",
        }
    return matrix

def save_rule(
    category: str,
    incident: str,
    description: str,
    hr_note: str,
    reset_days: int,
    escalation: list[str],
    rule_id: int | None = None,
) -> None:
    esc_json = _json.dumps(escalation)
    with _db() as conn:
        if rule_id:
            conn.execute(
                """UPDATE rules
                   SET category=?, incident=?, description=?, hr_note=?,
                       reset_days=?, escalation_json=?
                   WHERE id=?""",
                (category, incident, description, hr_note, reset_days, esc_json, rule_id),
            )
        else:
            conn.execute(
                """INSERT INTO rules
                   (category, incident, description, hr_note, reset_days, escalation_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (category, incident, description, hr_note, reset_days, esc_json),
            )

def delete_rule(rule_id: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


def get_employees() -> pd.DataFrame:
    with _db() as conn:
        return pd.read_sql_query("SELECT * FROM employees ORDER BY name", conn)

def save_employee(name: str, email: str, dept: str, manager: str) -> None:
    with _db() as conn:
        conn.execute(
            """INSERT INTO employees (name, email, department, manager_email)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   email         = excluded.email,
                   department    = excluded.department,
                   manager_email = excluded.manager_email""",
            (name, email, dept, manager),
        )

def delete_employee(name: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM employees WHERE name = ?", (name,))

def insert_violation(
    emp_name: str,
    category: str,
    incident: str,
    penalty_color: str,
    comment: str,
    submitted_by: str,
    override_days: float = None,
    proof_image: str = ""
) -> None:
    p = PENALTY_MAP[penalty_color]
    applied_deduction = override_days if override_days is not None and override_days >= 0 else p["deduction_days"]
    
    if applied_deduction != p["deduction_days"] and penalty_color != "Investigation":
        actual_label = f"{penalty_color} Card — {applied_deduction} Days Deduction (Override)"
    else:
        actual_label = p["label"]
        
    with _db() as conn:
        conn.execute(
            """INSERT INTO violations
               (employee_name, category, incident, penalty_color, penalty_label,
                deduction_hours, deduction_days, freeze_months,
                comment, submitted_by, proof_image, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                emp_name, category, incident,
                penalty_color, actual_label,
                p["deduction_hours"], applied_deduction, p["freeze_months"],
                comment, submitted_by, proof_image,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

def delete_violation(vid: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM violations WHERE id = ?", (vid,))

_VIO_COLS = (
    "id, employee_name, category, incident, penalty_color, penalty_label, "
    "deduction_hours, deduction_days, freeze_months, comment, submitted_by, created_at"
)

def get_violations(
    employee:  str | None = None,
    date_from: datetime | None = None,
    date_to:   datetime | None = None,
    incident:  str | None = None,
    penalty:   str | None = None,
) -> pd.DataFrame:
    clauses: list[str] = ["1=1"]
    params:  list      = []

    if employee:
        clauses.append("employee_name = ?")
        params.append(employee)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from.strftime("%Y-%m-%d 00:00:00"))
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to.strftime("%Y-%m-%d 23:59:59"))
    if incident:
        clauses.append("incident = ?")
        params.append(incident)
    if penalty:
        clauses.append("penalty_color = ?")
        params.append(penalty)

    sql = (
        f"SELECT {_VIO_COLS} FROM violations "
        f"WHERE {' AND '.join(clauses)} "
        f"ORDER BY created_at DESC"
    )

    with _db() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    for col in ("deduction_hours", "deduction_days", "freeze_months"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df

# =============================================================
# SECTION 2.5 — GOOGLE SHEETS SYNC  (non-blocking, optional)
# =============================================================

_VIO_SHEET_HEADERS = [
    "ID", "Employee", "Category", "Incident", "Penalty", "Penalty Label",
    "Deduction Hours", "Deduction Days", "Freeze Months",
    "Comment", "Submitted By", "Date & Time",
]
_EMP_SHEET_HEADERS = ["ID", "Name", "Email", "Department", "Manager Email"]

_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_or_create_ws(sh, title: str, headers: list):
    """Return worksheet by title, creating it with headers if it doesn't exist."""
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.update([headers], "A1")
        return ws


@st.cache_resource(show_spinner=False)
def _get_sheets_client():
    """
    Lazily initialise and cache a gspread client for the app's lifetime.
    Uses gspread 6.x service_account_from_dict (replaces deprecated authorize()).
    Returns None when: gspread not installed, credentials missing, or any error.
    """
    if not _GSHEETS_AVAILABLE:
        return None
    sa_info = _gcp_service_account_info()
    if not sa_info or not GSHEETS_SPREADSHEET_ID:
        return None
    try:
        return gspread.service_account_from_dict(sa_info)
    except Exception:
        return None


def _sheets_append_violation(row: list) -> None:
    """
    Append one violation row to the 'Violations' worksheet.
    row = [id, employee, category, incident, penalty_color, penalty_label,
           deduction_hours, deduction_days, freeze_months, comment,
           submitted_by, created_at]
    Silently skips (st.warning only) on any error — never blocks the main flow.
    """
    try:
        client = _get_sheets_client()
        if client is None:
            return
        sh = client.open_by_key(GSHEETS_SPREADSHEET_ID)
        ws = _get_or_create_ws(sh, "Violations", _VIO_SHEET_HEADERS)
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as exc:
        st.warning(f"☁️ Google Sheets sync skipped: {exc}")


def _sheets_full_sync() -> tuple[bool, str]:
    """
    Overwrite both 'Violations' and 'Employees' sheets with all current SQLite data.
    Returns (True, success_msg) or (False, error_msg).
    proof_image is intentionally excluded (binary, irrelevant in a sheet).
    """
    try:
        client = _get_sheets_client()
        if client is None:
            return False, (
                "Google Sheets is not configured. "
                "Add GSHEETS_SPREADSHEET_ID and [gcp_service_account] to secrets.toml."
            )
        sh = client.open_by_key(GSHEETS_SPREADSHEET_ID)

        # ── Violations sheet (auto-create if missing) ─────────
        vio_df = get_violations()
        ws_vio = _get_or_create_ws(sh, "Violations", _VIO_SHEET_HEADERS)
        ws_vio.clear()
        ws_vio.update([_VIO_SHEET_HEADERS], "A1")
        if not vio_df.empty:
            _vio_cols = [
                "id", "employee_name", "category", "incident",
                "penalty_color", "penalty_label", "deduction_hours",
                "deduction_days", "freeze_months", "comment",
                "submitted_by", "created_at",
            ]
            ws_vio.append_rows(
                vio_df[_vio_cols].astype(str).values.tolist(),
                value_input_option="USER_ENTERED",
            )

        # ── Employees sheet (auto-create if missing) ──────────
        emp_df = get_employees()
        ws_emp = _get_or_create_ws(sh, "Employees", _EMP_SHEET_HEADERS)
        ws_emp.clear()
        ws_emp.update([_EMP_SHEET_HEADERS], "A1")
        if not emp_df.empty:
            ws_emp.append_rows(
                emp_df[["id", "name", "email", "department", "manager_email"]]
                .astype(str).values.tolist(),
                value_input_option="USER_ENTERED",
            )

        return True, (
            f"✅ Full sync complete — {len(vio_df)} violation(s) and "
            f"{len(emp_df)} employee(s) written to Google Sheets."
        )

    except Exception as exc:
        return False, f"Sync failed: {exc}"


# =============================================================
# SECTION 3 — BUSINESS LOGIC
# =============================================================

def calculate_next_penalty(emp_name: str, category: str, incident: str) -> str:
    _live = get_matrix_from_rules()
    meta       = _live[category][incident]
    escalation = meta["escalation"]
    reset_days = meta["reset"]
    cutoff     = (
        datetime.now() - timedelta(days=reset_days)
    ).strftime("%Y-%m-%d %H:%M:%S")

    with _db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM violations
               WHERE employee_name = ?
                 AND incident      = ?
                 AND created_at   >= ?
                 AND penalty_color != 'Investigation'""",
            (emp_name, incident, cutoff),
        ).fetchone()

    count = row[0] if row else 0
    index = min(count, len(escalation) - 1)
    return escalation[index]

# =============================================================
# SECTION 4 — EMAIL SERVICE
# =============================================================

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _valid_email(addr: str) -> bool:
    return bool(_EMAIL_REGEX.match(addr.strip()))

def send_notifications(
    emp_email:     str,
    manager_email: str,
    emp_name:      str,
    category:      str,
    incident:      str,
    penalty_color: str,
    comment:       str,
    applied_days:  float = None,
    proof_b64:     str = "",
) -> tuple[bool, str]:
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return False, "Email credentials missing in secrets.toml."

    p         = PENALTY_MAP[penalty_color]
    is_invest = penalty_color == "Investigation"

    if applied_days is not None and applied_days != p["deduction_days"] and not is_invest:
        actual_label = f"{penalty_color} Card — {applied_days} Days Deduction (Override)"
    else:
        actual_label = p["label"]

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
            srv.login(SENDER_EMAIL, SENDER_PASSWORD)

            if _valid_email(emp_email):
                msg = MIMEMultipart()
                msg["From"]    = SENDER_EMAIL
                msg["To"]      = emp_email
                msg["Subject"] = (
                    f"URGENT: Suspension Notice — {emp_name}"
                    if is_invest
                    else f"Disciplinary Action: {p['badge']} {penalty_color} Card"
                )
                if is_invest:
                    body = (
                        f"Dear {emp_name},\n\n"
                        f"You are hereby SUSPENDED pending an investigation.\n\n"
                        f"  Incident : {incident} ({category})\n"
                        f"  HR Notes : {comment}\n\n"
                        f"HR will contact you with further instructions.\n"
                        f"Do NOT report to the office until notified."
                    )
                else:
                    body = (
                        f"Dear {emp_name},\n\n"
                        f"A disciplinary action has been recorded on your file:\n\n"
                        f"  Incident : {incident} ({category})\n"
                        f"  Penalty  : {actual_label}\n"
                        f"  HR Notes : {comment}\n\n"
                        f"Please adhere to company policies to avoid further escalation.\n\n"
                        f"Human Resources Department"
                    )
                msg.attach(MIMEText(body, "plain", "utf-8"))
                
                if proof_b64:
                    try:
                        img_data = base64.b64decode(proof_b64)
                        img_part = MIMEImage(img_data, name="Attached_Proof.jpg")
                        msg.attach(img_part)
                    except Exception:
                        pass
                
                srv.sendmail(SENDER_EMAIL, [emp_email], msg.as_string())

            if manager_email and _valid_email(manager_email):
                mgr = MIMEMultipart()
                mgr["From"]    = SENDER_EMAIL
                mgr["To"]      = manager_email
                mgr["Subject"] = (
                    f"🚨 URGENT: Employee Suspended — {emp_name}"
                    if is_invest
                    else f"Manager Notice — {emp_name} | {p['badge']} {penalty_color}"
                )
                mgr_body = (
                    f"Dear Manager,\n\n"
                    f"Your team member {emp_name} has received a disciplinary penalty.\n\n"
                    f"  Incident : {incident} ({category})\n"
                    f"  Penalty  : {actual_label}\n"
                    f"  Notes    : {comment}\n"
                )
                if is_invest:
                    mgr_body += (
                        "\n\n🚨 IMPORTANT: This employee is SUSPENDED. "
                        "Do NOT allow them on-site until HR clearance is issued."
                    )
                    recipients = list({manager_email, HR_MANAGER_EMAIL} - {""})
                else:
                    recipients = [manager_email]

                mgr.attach(MIMEText(mgr_body, "plain", "utf-8"))
                
                if proof_b64:
                    try:
                        img_data = base64.b64decode(proof_b64)
                        img_part = MIMEImage(img_data, name="Attached_Proof.jpg")
                        mgr.attach(img_part)
                    except Exception:
                        pass
                
                srv.sendmail(SENDER_EMAIL, recipients, mgr.as_string())

        return True, "Emails sent successfully."

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — check EMAIL / PASSWORD in secrets."
    except smtplib.SMTPException as exc:
        return False, f"SMTP error: {exc}"
    except OSError as exc:
        return False, f"Network error: {exc}"

# =============================================================
# SECTION 5 — AUTHENTICATION
# =============================================================

def require_auth(page_key: str) -> bool:
    state_key = f"auth_{page_key}"
    if st.session_state.get(state_key):
        return True

    st.markdown(_t("### 🔑 HR Access Required"))
    with st.form(f"login_{page_key}"):
        pwd    = st.text_input(_t("Password"), type="password")
        submit = st.form_submit_button(_t("Login"))

    if submit:
        if pwd == HR_ADMIN_PASSWORD:
            st.session_state[state_key] = True
            st.rerun()
        else:
            st.error(_t("❌ Incorrect password."))

    return False

def _logout_button(page_key: str) -> None:
    _, btn_col = st.columns([9, 1])
    if btn_col.button(_t("Logout"), key=f"logout_{page_key}"):
        st.session_state[f"auth_{page_key}"] = False
        st.rerun()

# =============================================================
# SECTION 6 — SHARED UI HELPERS
# =============================================================

def _kpi_row(df: pd.DataFrame) -> None:
    today = datetime.now()

    def _active_freeze(sub: pd.DataFrame) -> bool:
        frozen = sub[sub["freeze_months"] > 0]
        if frozen.empty:
            return False
        last = frozen.loc[frozen["created_at"].idxmax()]
        end  = pd.to_datetime(last["created_at"]) + pd.DateOffset(
            months=int(last["freeze_months"])
        )
        return end.to_pydatetime() > today

    active_freezes = (
        df.groupby("employee_name")
          .apply(_active_freeze)
          .sum()
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(_t("Total Violations"),       len(df))
    k2.metric(_t("Unique Employees"),        df["employee_name"].nunique())
    k3.metric(_t("Total Deduction Days"),    f"{df['deduction_days'].sum():.1f}")
    k4.metric(_t("Active Promotion Freezes"), int(active_freezes))


# =============================================================
# SECTION 7 — APP BOOTSTRAP
# =============================================================

init_db()

tab_log, tab_admin, tab_reports, tab_rules = st.tabs([
    _t("📝 Log Violation"),
    _t("⚙️ Admin Dashboard"),
    _t("📊 Reports & Analytics"),
    _t("📜 Rules Management"),
])

# =============================================================
# TAB 1 — LOG VIOLATION
# =============================================================
with tab_log:
    employees_df = get_employees()
    _LIVE_MATRIX = get_matrix_from_rules()

    if employees_df.empty:
        st.warning(_t("⚠️ No employees found. Please add employees in the **Admin Dashboard** tab first."))
    elif not _LIVE_MATRIX:
        st.warning(_t("⚠️ No rules configured. Please add rules in the **Rules Management** tab first."))
    else:
        st.subheader(_t("Register New Violation"))

        col_cat, col_inc = st.columns(2)
        with col_cat:
            category = st.selectbox(
                _t("Violation Category"),
                list(_LIVE_MATRIX.keys()),
                format_func=lambda x: _t(x),
                key="t1_cat",
            )
        with col_inc:
            incident = st.selectbox(
                _t("Incident Type"),
                list(_LIVE_MATRIX[category].keys()),
                format_func=lambda x: _t(x),
                key="t1_inc",
            )

        inc_meta   = _LIVE_MATRIX[category][incident]
        escalation = inc_meta["escalation"]
        reset_days = inc_meta["reset"]
        details    = inc_meta.get("details", "")
        hr_note    = inc_meta.get("hr_note", "")

        with st.expander(_t("ℹ️ Incident Reference"), expanded=True):
            d1, d2 = st.columns(2)
            d1.info(f"{_t('**Details:**')} {_t(details)}")
            d2.info(
                f"{_t('**Reset Window:**')} {reset_days} {_t('days')}  "
                f"|  {_t('**Max Steps:**')} {len(escalation)}"
            )
            if hr_note:
                st.warning(f"{_t('📌 **HR Note:**')} {_t(hr_note)}")
            path_str = "  →  ".join(
                f"{PENALTY_MAP[p]['badge']} {_t(p)}" for p in escalation
            )
            st.write(f"{_t('**Escalation path:**')} {path_str}")

            st.markdown("---")
            st.markdown(f"*{_t('Penalties Guide (Default Deductions):')}*")
            for c, info in PENALTY_MAP.items():
                st.caption(f"{info['badge']} **{_t(c)}**: {_t(info['label'])}")

        with st.form("violation_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            with f1:
                emp_name = st.selectbox(
                    _t("Employee *"), employees_df["name"].tolist()
                )
                submitted_by = st.text_input(
                    _t("HR Representative Name *"),
                    help="Name of the HR staff member logging this violation. "
                         "Stored as the Audit Trail entry.",
                )
                
                st.markdown("---")
                force_investigation = st.checkbox(_t("🚨 Force Direct Investigation (Bypass Escalation)"))
                custom_deduction = st.number_input(
                    _t("Deduction Days Override (Optional)"), 
                    value=-1.0, step=0.5, 
                    help=_t("Leave as -1.0 to use default system calculation.")
                )

            with f2:
                comment = st.text_area(
                    _t("HR Comments / Alignment Notes"),
                    height=130,
                    help="Include contextual notes, manager alignment details, "
                         "or any mitigating factors.",
                )
                
                proof_file = st.file_uploader(
                    _t("Attach Proof Image (Optional)"), 
                    type=["png", "jpg", "jpeg"]
                )

            do_submit = st.form_submit_button(
                _t("✅ Submit & Notify"), use_container_width=True
            )

        if do_submit:
            if not submitted_by.strip():
                st.error(_t("⚠️ **HR Representative Name** is required. This field is the system's audit trail."))
            else:
                _MAX_IMAGE_BYTES = 2 * 1024 * 1024   # 2 MB
                proof_b64 = ""
                if proof_file is not None:
                    if proof_file.size > _MAX_IMAGE_BYTES:
                        st.error("⚠️ Image too large. Maximum allowed size is 2 MB.")
                        proof_file = None
                    else:
                        try:
                            proof_b64 = base64.b64encode(proof_file.read()).decode("utf-8")
                        except Exception as e:
                            st.error(f"Image Error: {e}")

                penalty_color = calculate_next_penalty(emp_name, category, incident)
                
                if force_investigation:
                    penalty_color = "Investigation"
                
                p_info  = PENALTY_MAP[penalty_color]
                
                actual_override = custom_deduction if custom_deduction >= 0.0 else None
                applied_days = actual_override if actual_override is not None else p_info["deduction_days"]

                emp_row = employees_df[
                    employees_df["name"] == emp_name
                ].iloc[0]

                insert_violation(
                    emp_name, category, incident,
                    penalty_color, comment, submitted_by.strip(),
                    override_days=actual_override,
                    proof_image=proof_b64
                )

                # ── Google Sheets: append this violation (non-blocking) ──
                with _db() as _gc:
                    _last_id = _gc.execute(
                        "SELECT id FROM violations ORDER BY id DESC LIMIT 1"
                    ).fetchone()["id"]
                _gs_label = (
                    f"{penalty_color} Card — {applied_days} Days Deduction (Override)"
                    if applied_days != p_info["deduction_days"] and penalty_color != "Investigation"
                    else p_info["label"]
                )
                _sheets_append_violation([
                    _last_id, emp_name, category, incident,
                    penalty_color, _gs_label,
                    p_info["deduction_hours"], applied_days,
                    p_info["freeze_months"], comment,
                    submitted_by.strip(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ])

                email_ok, email_msg = send_notifications(
                    str(emp_row["email"]),
                    str(emp_row["manager_email"] or ""),
                    emp_name, category, incident,
                    penalty_color, comment,
                    applied_days=applied_days,
                    proof_b64=proof_b64        
                )

                badge = p_info["badge"]
                
                success_label = f"{penalty_color} Card — {applied_days} Days Deduction (Override)" if applied_days != p_info["deduction_days"] and penalty_color != "Investigation" else p_info['label']

                if email_ok:
                    st.success(
                        f"{badge} Penalty recorded: **{_t(success_label)}** "
                        f"— Notifications sent."
                    )
                else:
                    st.warning(
                        f"{badge} Penalty recorded: **{_t(success_label)}** "
                        f"— Email skipped: {email_msg}"
                    )

                if penalty_color == "Investigation":
                    st.error(_t("🚨 **INVESTIGATION TRIGGERED** \nThe employee must be suspended immediately. Escalate to the HR Director and do **not** allow the employee on-site."))
                elif applied_days > 0:
                    hrs = (
                        f" ({p_info['deduction_hours']} hrs)"
                        if p_info["deduction_hours"] > 0 else ""
                    )
                    st.info(f"{_t('💰 **Payroll:**')} {applied_days} {_t('day(s) deduction')} {hrs} {_t('must be applied.')}")

                if p_info["freeze_months"] > 0:
                    until = (
                        datetime.now()
                        + timedelta(days=30 * p_info["freeze_months"])
                    ).strftime("%d %b %Y")
                    st.warning(f"{_t('🔒 **Promotion freeze** active until **')}{until}** ({p_info['freeze_months']} {_t('months).')}")

# =============================================================
# TAB 2 — ADMIN DASHBOARD
# =============================================================
with tab_admin:
    if not require_auth("tab2"):
        pass   # Login form already rendered by require_auth
    else:
        _logout_button("tab2")
        st.subheader(_t("👥 Employee Management"))

        # ── Add / Update Employee ─────────────────────────
        with st.form("add_emp_form", clear_on_submit=True):
            a1, a2 = st.columns(2)
            with a1:
                e_name  = st.text_input(_t("Full Name *"))
                e_email = st.text_input(_t("Email Address *"))
            with a2:
                e_dept    = st.text_input(_t("Department"))
                e_manager = st.text_input(_t("Manager Email (CC on penalties)"))

            if st.form_submit_button(_t("💾 Save Employee")):
                errors: list[str] = []
                if not e_name.strip():
                    errors.append("Employee name is required.")
                if not e_email.strip():
                    errors.append("Email address is required.")
                elif not _valid_email(e_email.strip()):
                    errors.append("Email address format is invalid.")
                if e_manager.strip() and not _valid_email(e_manager.strip()):
                    errors.append("Manager email format is invalid.")

                if errors:
                    for err in errors:
                        st.error(f"⚠️ {err}")
                else:
                    save_employee(
                        e_name.strip(), e_email.strip(),
                        e_dept.strip(), e_manager.strip(),
                    )
                    st.success(f"{_t('✅ Employee')} **{e_name.strip()}** {_t('saved.')}")
                    st.rerun()

        # ── Employee List ─────────────────────────────────
        emp_df = get_employees()
        if not emp_df.empty:
            disp_emp = emp_df[["name", "email", "department", "manager_email"]].rename(columns={
                "name": _t("Full Name *"), "email": _t("Email Address *"), 
                "department": _t("Department"), "manager_email": _t("Manager Email (CC on penalties)")
            })
            st.dataframe(disp_emp, use_container_width=True)
            
            del_name = st.selectbox(
                _t("Select employee to remove:"),
                [_t("— select —")] + emp_df["name"].tolist(),
                key="del_emp_sel",
            )
            if del_name != _t("— select —"):
                if st.button(_t("🗑️ Delete Employee"), key="del_emp_btn"):
                    delete_employee(del_name)
                    st.success(f"Employee **{del_name}** {_t('removed.')}")
                    st.rerun()
        else:
            st.info(_t("No employees yet. Use the form above to add one."))

        st.divider()

        # ── Violation Records (admin view) ────────────────
        st.subheader(_t("🗂️ Violation Records"))
        v_all = get_violations()

        if not v_all.empty:
            v_disp_admin = v_all.copy()
            v_disp_admin['incident'] = v_disp_admin['incident'].apply(_t)
            v_disp_admin['penalty_color'] = v_disp_admin['penalty_color'].apply(_t)
            
            _admin_cols = {
                "id": "ID", "employee_name": _t("Employee"), "incident": _t("Incident"),
                "penalty_color": _t("Penalty"), "deduction_days": _t("Deduction (days)"),
                "submitted_by": _t("Submitted By"), "created_at": _t("Date & Time")
            }
            
            st.dataframe(
                v_disp_admin[list(_admin_cols.keys())].rename(columns=_admin_cols),
                use_container_width=True,
            )
            del_id = st.selectbox(
                _t("Select Record ID to delete:"),
                v_all["id"].tolist(),
                key="del_v_sel",
            )
            if st.button(_t("🗑️ Delete Violation Record"), key="del_v_btn"):
                delete_violation(int(del_id))
                st.success(f"{_t('Record')} **{del_id}** {_t('deleted.')}")
                st.rerun()
                
            # ── View Proof Image (admin view) NEW ────────────
            st.markdown("---")
            st.subheader(_t("🖼️ View Proof Image"))
            view_id = st.selectbox(
                _t("Select Record ID to view proof:"),
                v_all["id"].tolist(),
                key="view_img_sel",
            )
            if st.button(_t("👁️ View Image"), key="view_img_btn"):
                # Fetch only the image for this specific record (no full table scan)
                with _db() as _img_conn:
                    _img_row = _img_conn.execute(
                        "SELECT proof_image FROM violations WHERE id = ?", (int(view_id),)
                    ).fetchone()
                img_b64 = _img_row["proof_image"] if _img_row else ""
                if img_b64:
                    try:
                        img_data = base64.b64decode(img_b64)
                        st.image(img_data, caption=f"{_t('Proof for Record ID:')} {view_id}")
                    except Exception as e:
                        st.error(f"Error loading image: {e}")
                else:
                    st.info(_t("No image attached to this record."))
                    
        else:
            st.info(_t("No violations logged yet."))

        # ── Google Sheets Backup ──────────────────────────────
        st.divider()
        st.subheader("☁️ Google Sheets Backup")

        if not GSHEETS_SPREADSHEET_ID:
            st.info(
                "Google Sheets sync is **not configured** yet. "
                "Expand the setup guide below to get started."
            )
        else:
            st.caption(
                f"📋 Spreadsheet ID: `{GSHEETS_SPREADSHEET_ID}`  \n"
                "Full sync overwrites both **Violations** and **Employees** sheets "
                "with the current SQLite data."
            )
            if st.button("🔄 Full Sync to Google Sheets", key="gsheets_sync_btn"):
                with st.spinner("Syncing to Google Sheets…"):
                    _ok, _msg = _sheets_full_sync()
                if _ok:
                    st.success(_msg)
                else:
                    st.error(f"Sync failed: {_msg}")

        with st.expander("⚙️ How to Set Up Google Sheets Sync", expanded=not bool(GSHEETS_SPREADSHEET_ID)):
            st.markdown("""
### Step-by-step Setup Guide

---

**Step 1 — Create a Google Cloud Project**
1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Click the project dropdown → **New Project** → give it a name (e.g. `hr-system`) → **Create**.

---

**Step 2 — Enable the required APIs**
1. Left menu → **APIs & Services → Library**.
2. Search **Google Sheets API** → **Enable**.
3. Search **Google Drive API** → **Enable** (required for gspread to work).

---

**Step 3 — Create a Service Account**
1. Left menu → **APIs & Services → Credentials**.
2. Click **+ Create Credentials → Service Account**.
3. Name it (e.g. `hr-sheets`) → **Create and Continue** → **Done**.

---

**Step 4 — Download the JSON Key**
1. Click the service account email you just created.
2. Go to the **Keys** tab → **Add Key → Create new key → JSON → Create**.
3. A `.json` file downloads — treat it like a password, keep it safe.

---

**Step 5 — Create the Google Spreadsheet**
1. Go to [sheets.google.com](https://sheets.google.com) → create a new **Blank** spreadsheet.
2. Name it **HR System Backup** (or anything you prefer).
3. Rename **Sheet1** tab → `Violations`.
4. Click the **+** button at the bottom → rename the new sheet → `Employees`.
5. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/  ← SPREADSHEET_ID →  /edit
   ```

---

**Step 6 — Share the Sheet with the Service Account**
1. Click **Share** (top-right of the spreadsheet).
2. Paste the service account email (ends with `.iam.gserviceaccount.com`).
3. Set permission to **Editor** → **Send**.

---

**Step 7 — Add Credentials to `secrets.toml`**

Create or edit `.streamlit/secrets.toml` in the project root and add:

```toml
GSHEETS_SPREADSHEET_ID = "paste-your-spreadsheet-id-here"

[gcp_service_account]
type                        = "service_account"
project_id                  = "from-json-file"
private_key_id              = "from-json-file"
private_key                 = "-----BEGIN RSA PRIVATE KEY-----\\nABC...XYZ\\n-----END RSA PRIVATE KEY-----\\n"
client_email                = "hr-sheets@your-project.iam.gserviceaccount.com"
client_id                   = "from-json-file"
auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
token_uri                   = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "from-json-file"
```

> ⚠️ For `private_key`: open the downloaded JSON file, copy the entire value of `"private_key"`,
> and replace every actual newline with `\\n` (two characters: backslash + n).

---

**Step 8 — Restart the App**

After saving `secrets.toml`, restart the Streamlit app (or press **R** in Streamlit Cloud).
The **Full Sync** button above will then be active.

---

**How it works after setup:**
- Every new violation → 1 row auto-appended to the **Violations** sheet instantly.
- Use the **Full Sync** button after deleting records to keep the sheet clean.
- The sheet is read-only for HR visibility — edits in the sheet do **not** affect the system.
            """)

# =============================================================
# TAB 3 — REPORTS & ANALYTICS
# =============================================================
with tab_reports:
    if not require_auth("tab3"):
        pass   # Login form already rendered by require_auth
    else:
        _logout_button("tab3")
        st.header(_t("📊 HR Reports & Analytics"))

        # ── Filters ───────────────────────────────────────
        with st.expander(_t("🔍 Filters"), expanded=True):
            fi1, fi2, fi3, fi4 = st.columns([2, 3, 2, 2])

            all_names = [_t("All")] + sorted(
                get_employees()["name"].tolist()
            )
            _rpt_matrix = get_matrix_from_rules()
            all_incidents = [_t("All")] + sorted(
                inc
                for cat in _rpt_matrix.values()
                for inc in cat
            )
            all_penalties = [_t("All")] + list(PENALTY_MAP.keys())

            with fi1:
                f_emp = st.selectbox(
                    _t("Employee Name"), all_names, key="r_emp"
                )

            with fi2:
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_from = st.date_input(
                        _t("From"),
                        value=datetime.now().date() - timedelta(days=90),
                        key="r_from",
                    )
                with fc2:
                    f_to = st.date_input(
                        _t("To"),
                        value=datetime.now().date(),
                        key="r_to",
                    )

            with fi3:
                f_inc = st.selectbox(
                    _t("Incident Type"), all_incidents, format_func=lambda x: _t(x) if x != _t("All") else x, key="r_inc"
                )

            with fi4:
                f_pen = st.selectbox(
                    _t("Penalty Level"), all_penalties, format_func=lambda x: _t(x) if x != _t("All") else x, key="r_pen"
                )

        # Validate date range — no st.stop() inside a tab.
        if f_from > f_to:
            st.error(_t("⚠️ 'From' date must be before or equal to 'To' date."))
        else:
            db_inc = None if f_inc == _t("All") else f_inc
            db_pen = None if f_pen == _t("All") else f_pen
            
            df = get_violations(
                employee  = None if f_emp == _t("All") else f_emp,
                date_from = datetime.combine(f_from, datetime.min.time()),
                date_to   = datetime.combine(f_to,   datetime.max.time()),
                incident  = db_inc,
                penalty   = db_pen,
            )

            if df.empty:
                st.info(_t("ℹ️ No violations match the selected filters."))
            else:
                df["created_at"] = pd.to_datetime(df["created_at"])

                # ── KPI row ───────────────────────────────
                _kpi_row(df)
                st.divider()
                
                # Copy for Translated Display
                df_disp = df.copy()
                df_disp['category'] = df_disp['category'].apply(_t)
                df_disp['incident'] = df_disp['incident'].apply(_t)
                df_disp['penalty_color'] = df_disp['penalty_color'].apply(_t)
                df_disp['penalty_label'] = df_disp['penalty_label'].apply(_t)

                # ── Chart row 1 ───────────────────────────
                ch1, ch2 = st.columns(2)

                with ch1:
                    fig_pie = px.pie(
                        df_disp,
                        names="category",
                        title=_t("Violations by Category"),
                        color_discrete_sequence=["#3ECAC0","#F47B3A","#2AADA3","#FDB97D","#1F8F87","#FFD580","#7ECECE"],
                    )
                    fig_pie.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                    )
                    fig_pie.update_layout(showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)

                with ch2:
                    emp_cnt = (
                        df_disp["employee_name"]
                        .value_counts()
                        .reset_index()
                    )
                    emp_cnt.columns = [_t("Employee"), _t("Count")]
                    fig_emp_bar = px.bar(
                        emp_cnt,
                        x=_t("Employee"),
                        y=_t("Count"),
                        title=_t("Violations per Employee"),
                        color=_t("Count"),
                        color_continuous_scale=["#E8FAF9","#3ECAC0","#1F8F87"],
                    )
                    fig_emp_bar.update_layout(
                        showlegend=False,
                        xaxis_tickangle=-30,
                        coloraxis_showscale=False,
                    )
                    st.plotly_chart(fig_emp_bar, use_container_width=True)

                # ── Date bar chart (Feature B) ────────────
                st.subheader(_t("📅 Violations Over Time"))
                df_disp["date_only"] = df_disp["created_at"].dt.date
                daily = (
                    df_disp.groupby("date_only")
                    .size()
                    .reset_index(name="count")
                )
                daily["date_only"] = pd.to_datetime(daily["date_only"])

                fig_time = px.bar(
                    daily,
                    x="date_only",
                    y="count",
                    title=_t("Daily Violation Count"),
                    labels={"date_only": _t("Date"), "count": _t("Violations")},
                    color_discrete_sequence=["#F47B3A"],
                )
                fig_time.update_layout(
                    bargap=0.25,
                    xaxis_tickformat="%d %b %Y",
                    xaxis_title=_t("Date"),
                    yaxis_title=_t("Violations"),
                )
                st.plotly_chart(fig_time, use_container_width=True)

                # ── Chart row 2 ───────────────────────────
                ch3, ch4 = st.columns(2)

                _PENALTY_COLOUR_MAP = {
                    _t("Yellow"):        "#FFD700",
                    _t("Orange"):        "#FF8C00",
                    _t("Red"):           "#DC143C",
                    _t("Black"):         "#444444",
                    _t("Investigation"): "#7B2FBE",
                }

                with ch3:
                    pen_cnt = (
                        df_disp["penalty_color"].value_counts().reset_index()
                    )
                    pen_cnt.columns = [_t("Penalty"), _t("Count")]
                    fig_pen = px.bar(
                        pen_cnt,
                        x=_t("Penalty"),
                        y=_t("Count"),
                        title=_t("Violations by Penalty Level"),
                        color=_t("Penalty"),
                        color_discrete_map=_PENALTY_COLOUR_MAP,
                    )
                    fig_pen.update_layout(showlegend=False)
                    st.plotly_chart(fig_pen, use_container_width=True)

                with ch4:
                    inc_cnt = (
                        df_disp["incident"]
                        .value_counts()
                        .head(10)
                        .reset_index()
                    )
                    inc_cnt.columns = [_t("Incident"), _t("Count")]
                    fig_inc = px.bar(
                        inc_cnt,
                        x=_t("Count"),
                        y=_t("Incident"),
                        orientation="h",
                        title=_t("Top 10 Incidents"),
                        color_discrete_sequence=["#3ECAC0"],
                    )
                    fig_inc.update_layout(
                        yaxis={"categoryorder": "total ascending"}
                    )
                    st.plotly_chart(fig_inc, use_container_width=True)

                st.divider()

                # ── History table with deduction days ────
                st.subheader(_t("📋 Violation History — Full Detail"))

                today_d = date.today()

                df_disp["freeze_end_date"] = df_disp.apply(
                    lambda r: (
                        r["created_at"]
                        + pd.DateOffset(months=int(r["freeze_months"]))
                    ).date()
                    if r["freeze_months"] > 0 else None,
                    axis=1,
                )
                df_disp["Currently Frozen"] = df_disp[
                    "freeze_end_date"
                ].apply(
                    lambda d: f"🔒 {_t('Yes')}"
                    if (d is not None and d > today_d)
                    else f"✅ {_t('No')}"
                )

                # Column selection and renaming
                _cols = {
                    "employee_name":    _t("Employee"),
                    "category":         _t("Category"),
                    "incident":         _t("Incident"),
                    "penalty_color":    _t("Penalty"),
                    "penalty_label":    _t("Penalty Description"),
                    "deduction_hours":  _t("Deduction (hrs)"),
                    "deduction_days":   _t("Deduction (days)"),
                    "freeze_end_date":  _t("Freeze Until"),
                    "Currently Frozen": _t("Currently Frozen"),
                    "submitted_by":     _t("Submitted By"),   # ← Audit Trail
                    "created_at":       _t("Date & Time"),
                }
                
                hist_df = df_disp[list(_cols.keys())].rename(columns=_cols)
                st.dataframe(hist_df, use_container_width=True, height=420)

                # ── Payroll summary per employee ──────────
                st.subheader(_t("💰 Payroll Deduction Summary"))

                def _active_freeze_label(emp: str) -> str:
                    sub = df[
                        (df["employee_name"] == emp) & (df["freeze_months"] > 0)
                    ]
                    if sub.empty:
                        return f"✅ {_t('No')}"
                    latest_idx = sub["created_at"].idxmax()
                    months     = int(sub.at[latest_idx, "freeze_months"])
                    end        = (
                        sub.at[latest_idx, "created_at"]
                        + pd.DateOffset(months=months)
                    ).date()
                    return f"🔒 {_t('Yes')}" if end > today_d else f"✅ {_t('No')}"

                payroll = (
                    df_disp.groupby("employee_name")
                    .agg(
                        Violations      =("id",              "count"),
                        Deduction_Hours =("deduction_hours", "sum"),
                        Deduction_Days  =("deduction_days",  "sum"),
                    )
                    .reset_index()
                    .rename(columns={
                        "employee_name": _t("Employee"),
                        "Violations": _t("Violations"),
                        "Deduction_Hours": _t("Deduction (hrs)"),
                        "Deduction_Days": _t("Deduction (days)")
                    })
                )
                payroll[_t("Active Freeze")] = payroll[_t("Employee")].apply(
                    _active_freeze_label
                )
                st.dataframe(payroll, use_container_width=True)

                # ── Excel export ────────────────────────────
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    hist_df.to_excel(writer, index=False, sheet_name='Violations History')
                    payroll.to_excel(writer, index=False, sheet_name='Payroll Summary')
                
                excel_bytes = buffer.getvalue()
                
                st.download_button(
                    label=_t("📥 Export Filtered Report (Excel)"),
                    data=excel_bytes,
                    file_name=(
                        f"hr_report_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
                    ),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

# =============================================================
# TAB 4 — RULES MANAGEMENT
# =============================================================
with tab_rules:
    if not require_auth("tab4"):
        pass
    else:
        _logout_button("tab4")
        st.header(_t("📜 Rules & Escalation Management"))
        st.caption(_t("Add, edit, or delete violation rules. Changes take effect immediately on new violations."))

        _VALID_PENALTIES = list(PENALTY_MAP.keys())

        # ── State helpers for edit mode ─────────────────────
        if "edit_rule_id" not in st.session_state:
            st.session_state.edit_rule_id = None

        # ── Current rules table ─────────────────────────────
        rules_df = get_rules()

        if not rules_df.empty:
            st.subheader(_t("Current Rules"))

            # Build display dataframe
            _rdisp = rules_df.copy()
            _rdisp["escalation_preview"] = _rdisp["escalation_json"].apply(
                lambda j: " → ".join(
                    f"{PENALTY_MAP.get(p, {}).get('badge', '?')} {_t(p)}"
                    for p in _json.loads(j)
                )
            )
            _rdisp["category"] = _rdisp["category"].apply(_t)
            _rdisp["incident"] = _rdisp["incident"].apply(_t)

            _rcols = {
                "id": "ID",
                "category": _t("Category"),
                "incident": _t("Incident"),
                "description": _t("Description"),
                "reset_days": _t("Reset (days)"),
                "escalation_preview": _t("Escalation Path"),
            }
            st.dataframe(
                _rdisp[list(_rcols.keys())].rename(columns=_rcols),
                use_container_width=True,
                height=min(400, 60 + len(rules_df) * 35),
            )

            # ── Delete rule ──────────────────────────────
            st.markdown("---")
            _del_col, _edit_col = st.columns(2)
            with _del_col:
                _del_rule_id = st.selectbox(
                    _t("Select Rule ID to delete:"),
                    rules_df["id"].tolist(),
                    key="del_rule_sel",
                )
                if st.button(_t("🗑️ Delete Rule"), key="del_rule_btn"):
                    delete_rule(int(_del_rule_id))
                    st.success(f"{_t('Rule')} **{_del_rule_id}** {_t('deleted.')}")
                    st.rerun()

            # ── Load rule for editing ────────────────────
            with _edit_col:
                _edit_rule_id = st.selectbox(
                    _t("Select Rule ID to edit:"),
                    rules_df["id"].tolist(),
                    key="edit_rule_sel",
                )
                if st.button(_t("✏️ Load Rule for Editing"), key="load_rule_btn"):
                    st.session_state.edit_rule_id = int(_edit_rule_id)
                    st.rerun()

        else:
            st.info(_t("No rules configured yet. Use the form below to add the first rule."))

        st.divider()

        # ── Add / Edit Form ──────────────────────────────────
        _editing = st.session_state.edit_rule_id is not None
        _edit_data: dict = {}

        if _editing and not rules_df.empty:
            _row = rules_df[rules_df["id"] == st.session_state.edit_rule_id]
            if not _row.empty:
                _edit_data = _row.iloc[0].to_dict()
                _edit_data["escalation"] = _json.loads(_edit_data["escalation_json"])

        _form_title = (
            f"✏️ {_t('Edit Rule')} (ID: {st.session_state.edit_rule_id})"
            if _editing and _edit_data
            else f"➕ {_t('Add New Rule')}"
        )
        st.subheader(_form_title)

        if _editing and not _edit_data:
            st.warning(_t("Rule not found. It may have been deleted."))
            st.session_state.edit_rule_id = None
            _editing = False

        with st.form("rule_form", clear_on_submit=not _editing):
            _rf1, _rf2 = st.columns(2)
            with _rf1:
                _r_category = st.text_input(
                    _t("Category *"),
                    value=_edit_data.get("category", ""),
                    placeholder="e.g. Attendance & Adherence",
                )
                _r_incident = st.text_input(
                    _t("Incident Name *"),
                    value=_edit_data.get("incident", ""),
                    placeholder="e.g. Late Arrival",
                )
                _r_reset = st.number_input(
                    _t("Reset Period (days) *"),
                    min_value=1, max_value=365,
                    value=int(_edit_data.get("reset_days", 30)),
                )

            with _rf2:
                _r_desc = st.text_area(
                    _t("Description"),
                    value=_edit_data.get("description", ""),
                    height=80,
                )
                _r_hr_note = st.text_area(
                    _t("HR Note (Optional)"),
                    value=_edit_data.get("hr_note", ""),
                    height=80,
                )

            st.markdown(f"**{_t('Escalation Path')}** — {_t('Select penalty levels in order (1st offense → last)')}")

            _existing_esc = _edit_data.get("escalation", ["Yellow"])
            _n_steps = st.number_input(
                _t("Number of escalation steps"),
                min_value=1, max_value=10,
                value=max(1, len(_existing_esc)),
                key="esc_steps",
            )

            _esc_cols = st.columns(min(int(_n_steps), 5))
            _esc_vals: list[str] = []
            for i in range(int(_n_steps)):
                col_idx = i % min(int(_n_steps), 5)
                with _esc_cols[col_idx]:
                    _default_idx = (
                        _VALID_PENALTIES.index(_existing_esc[i])
                        if i < len(_existing_esc) and _existing_esc[i] in _VALID_PENALTIES
                        else 0
                    )
                    _step_val = st.selectbox(
                        f"Step {i + 1}",
                        _VALID_PENALTIES,
                        index=_default_idx,
                        format_func=lambda x: f"{PENALTY_MAP[x]['badge']} {_t(x)}",
                        key=f"esc_step_{i}",
                    )
                    _esc_vals.append(_step_val)

            _submitted_rule = st.form_submit_button(
                _t("💾 Save Rule") if not _editing else _t("💾 Update Rule"),
                use_container_width=True,
            )

        if _submitted_rule:
            _errors: list[str] = []
            if not _r_category.strip():
                _errors.append(_t("Category is required."))
            if not _r_incident.strip():
                _errors.append(_t("Incident Name is required."))
            if not _esc_vals:
                _errors.append(_t("At least one escalation step is required."))

            if _errors:
                for _e in _errors:
                    st.error(f"⚠️ {_e}")
            else:
                save_rule(
                    category=_r_category.strip(),
                    incident=_r_incident.strip(),
                    description=_r_desc.strip(),
                    hr_note=_r_hr_note.strip(),
                    reset_days=int(_r_reset),
                    escalation=_esc_vals,
                    rule_id=st.session_state.edit_rule_id if _editing else None,
                )
                if _editing:
                    st.success(f"✅ {_t('Rule updated successfully.')}")
                    st.session_state.edit_rule_id = None
                else:
                    st.success(f"✅ {_t('Rule added successfully.')}")
                st.rerun()

        if _editing:
            if st.button(_t("❌ Cancel Editing"), key="cancel_edit_btn"):
                st.session_state.edit_rule_id = None
                st.rerun()