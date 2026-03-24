import streamlit as st
import pandas as pd
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os
import json

# --- إعدادات الإيميل ---
SENDER_EMAIL = st.secrets["EMAIL"]
SENDER_PASSWORD = st.secrets["PASSWORD"]

def send_email(employee_email, employee_name, incident, penalty, comment):
    subject = "Disciplinary Action Notice"
    body = f"""
    Dear {employee_name},
    
    Please be advised that the following note has been recorded:
    Incident: {incident}
    Disciplinary Action: {penalty}
    HR Comments: {comment}
    
    Please ensure compliance with company policies.
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = employee_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        st.error(f"Error sending email: {e}")

# --- إدارة الملفات ---
st.set_page_config(page_title="HR Disciplinary System", page_icon="⚖️", layout="centered")
st.title("نظام إدارة الإجراءات التأديبية ⚖️")

EXCEL_FILE = "penalties_log.xlsx"
MATRIX_FILE = "matrix.xlsx"
EMP_FILE = "employees.json"

# تحميل مصفوفة العقوبات
try:
    matrix_df = pd.read_excel(MATRIX_FILE)
    categories = matrix_df['Category'].unique().tolist()
except FileNotFoundError:
    st.error("⚠️ ملف matrix.xlsx غير موجود. يرجى رفعه أولاً.")
    st.stop()

# تحميل سجل العقوبات
if os.path.exists(EXCEL_FILE):
    log_df = pd.read_excel(EXCEL_FILE)
else:
    log_df = pd.DataFrame(columns=["Employee", "Email", "Category", "Incident", "Penalty", "Comment", "Date"])

# تحميل الموظفين
if os.path.exists(EMP_FILE):
    with open(EMP_FILE, "r", encoding="utf-8") as f:
        employees = json.load(f)
else:
    employees = {"yousef": "youssefeldakar5@gmail.com"}
    with open(EMP_FILE, "w", encoding="utf-8") as f: json.dump(employees, f)

# --- دالة حساب مستوى الخطأ ---
def calculate_infraction_level(emp_name, incident_name, reset_days):
    if log_df.empty:
        return 0
    
    history = log_df[(log_df['Employee'] == emp_name) & (log_df['Incident'] == incident_name)].copy()
    if history.empty:
        return 0
        
    history['Date'] = pd.to_datetime(history['Date'])
    history = history.sort_values(by='Date')
    dates = history['Date'].tolist()
    
    level = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days <= reset_days:
            level += 1
        else:
            level = 1 
            
    if (datetime.now() - dates[-1]).days > reset_days:
        level = 0 
        
    return level

# --- تقسيم الموقع لصفحتين ---
tab1, tab2 = st.tabs(["📝 تسجيل مخالفة", "⚙️ لوحة تحكم الإدارة (HR)"])

# ==========================================
# الصفحة الأولى: تسجيل المخالفات
# ==========================================
with tab1:
    if "success_message" in st.session_state:
        st.success(st.session_state.success_message)
        del st.session_state.success_message

    # تم إزالة st.form لكي تتحدث القوائم تلقائياً
    if not employees:
        st.warning("برجاء إضافة موظفين أولاً من لوحة التحكم.")
        emp_name = None
    else:
        emp_name = st.selectbox("اختر الموظف", list(employees.keys()))
        
    selected_category = st.selectbox("القسم (Category)", categories)
    
    # تحديث الخطأ بناءً على القسم المختار فوراً
    incidents_in_cat = matrix_df[matrix_df['Category'] == selected_category]['Incident'].tolist()
    incident = st.selectbox("نوع الخطأ (Incident)", incidents_in_cat)
    
    incident_row = matrix_df[(matrix_df['Category'] == selected_category) & (matrix_df['Incident'] == incident)]
    details = incident_row['Details'].values[0]
    
    # حماية من خطأ تحويل الإكسيل للأرقام إلى تواريخ
    raw_days = incident_row['Within (Days)'].values[0]
    try:
        reset_days = int(float(raw_days))
        if reset_days > 365: # لو الرقم بالملايين بسبب الإكسيل
            st.warning("⚠️ تنبيه: عمود الأيام في الإكسيل محفوظ بصيغة 'تاريخ'. تم اعتباره 30 يوم مؤقتاً، يرجى تعديله في ملف الإكسيل.")
            reset_days = 30
    except:
        reset_days = 30
    
    st.info(f"**Details:** {details}\n\n**Reset Period:** {reset_days} Days")
    
    comment = st.text_area("تعليق / ملاحظات")
    submitted = st.button("إرسال الإشعار (Submit)") # تحول لزرار عادي

    if submitted and emp_name:
        current_level = calculate_infraction_level(emp_name, incident, reset_days)
        next_action_index = current_level + 1 
        
        action_columns = ["1st time", "2nd time", "3rd time", "4th time", "5th time", "6th time", "7th time", "8th time"]
        
        if next_action_index > len(action_columns):
            st.error("❌ لا يمكن تسجيل هذه المخالفة! الموظف استنفذ جميع الإجراءات التأديبية لهذا الخطأ.")
        else:
            action_col_name = action_columns[next_action_index - 1]
            
            temp_penalty = incident_row[action_col_name]
            if isinstance(temp_penalty, pd.DataFrame): 
                final_penalty = temp_penalty.iloc[0, 0]
            elif isinstance(temp_penalty, pd.Series): 
                final_penalty = temp_penalty.iloc[0]
            else:
                final_penalty = temp_penalty
            
            if pd.isna(final_penalty) or str(final_penalty).strip() == "":
                st.error("❌ لا يمكن إعطاء عقوبة إضافية. الموظف استنفذ الحد الأقصى للإجراءات في هذه المخالفة المحددة.")
            else:
                emp_email = employees[emp_name]
                current_date = datetime.now()
                
                new_record = pd.DataFrame({
                    "Employee": [emp_name],
                    "Email": [emp_email],
                    "Category": [selected_category],
                    "Incident": [incident],
                    "Penalty": [final_penalty],
                    "Comment": [comment],
                    "Date": [current_date.strftime("%Y-%m-%d")]
                })
                
                log_df = pd.concat([log_df, new_record], ignore_index=True)
                log_df.to_excel(EXCEL_FILE, index=False)
                
                send_email(emp_email, emp_name, incident, final_penalty, comment)
                
                st.session_state.success_message = f"✅ تم تسجيل المخالفة ({action_col_name}): {final_penalty}"
                st.rerun()

# ==========================================
# الصفحة الثانية: لوحة التحكم 
# ==========================================
with tab2:
    st.subheader("👥 إدارة الموظفين")
    col_emp1, col_emp2 = st.columns(2)
    with col_emp1:
        new_emp_name = st.text_input("اسم الموظف:")
        new_emp_email = st.text_input("إيميل الموظف:")
        if st.button("➕ إضافة موظف"):
            if new_emp_name and new_emp_email:
                employees[new_emp_name] = new_emp_email
                with open(EMP_FILE, "w", encoding="utf-8") as f: json.dump(employees, f)
                st.success("تم الإضافة!")
                st.rerun()
                
    with col_emp2:
        if employees:
            emp_to_remove = st.selectbox("مسح موظف:", list(employees.keys()))
            if st.button("🗑️ مسح"):
                del employees[emp_to_remove]
                with open(EMP_FILE, "w", encoding="utf-8") as f: json.dump(employees, f)
                st.success("تم المسح!")
                st.rerun()

    st.write("---")
    st.subheader("❌ إدارة وإلغاء العقوبات المسجلة")
    st.info("لحذف عقوبة مسجلة (لإلغاء تأثيرها)، اختر 'رقم الصف' من الجدول واضغط حذف.")
    
    if not log_df.empty:
        st.dataframe(log_df, use_container_width=True)
        record_to_delete = st.selectbox("اختر رقم الصف (Index) للحذف:", log_df.index)
        if st.button("حذف العقوبة نهائياً 🗑️"):
            log_df = log_df.drop(index=record_to_delete)
            log_df.to_excel(EXCEL_FILE, index=False)
            st.success("تم الحذف بنجاح!")
            st.rerun()
            
        st.write("---")
        with open(EXCEL_FILE, "rb") as file:
            st.download_button(label="📥 تحميل السجل بالكامل (Excel)", data=file, file_name="penalties_log.xlsx")
    else:
        st.warning("لا توجد عقوبات مسجلة.")