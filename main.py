import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText

# --- 1. إعدادات الإيميل ---
SENDER_EMAIL = "yahiazakaria412@gmail.com"
SENDER_PASSWORD = "hhvn rral ywer awbb"

def send_email(employee_email, employee_name, infraction, penalty, comment):
    subject = f"إشعار إداري: {penalty}"
    body = f"""
    مرحباً {employee_name}،
    
    يرجى العلم بأنه تم تسجيل الملاحظة التالية:
    الخطأ: {infraction}
    القرار الإداري: {penalty}
    ملاحظات الـ HR: {comment}
    
    برجاء الالتزام بتعليمات العمل.
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = employee_email

    try:
        # إعدادات سيرفر الإيميل (مثال لـ Gmail)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        st.error(f"حدث خطأ أثناء إرسال الإيميل: {e}")

# --- 2. واجهة الويب للموارد البشرية ---
st.title("نظام إدارة إنذارات الموظفين 🟨⬛")

# تحميل السجل الحالي (أو إنشاء واحد جديد إذا لم يكن موجوداً)
try:
    log_df = pd.read_excel("penalties_log.xlsx")
except FileNotFoundError:
    log_df = pd.DataFrame(columns=["Employee", "Email", "Infraction", "Penalty", "Comment", "Date"])

# بيانات الموظفين (يمكن ربطها بقاعدة بيانات)
employees = {"yousef": "youssefeldakar5@gmail.com", "Sara": "sara@example.com"}
infractions_list = ["تأخير في الرد", "عدم عمل فولو اب", "الوصول متأخراً لمقر العمل"]

with st.form("penalty_form"):
    emp_name = st.selectbox("اختر الموظف", list(employees.keys()))
    infraction = st.selectbox("نوع الخطأ", infractions_list)
    comment = st.text_area("تعليق / ملاحظات")
    
    submitted = st.form_submit_button("Submit")

    if submitted:
        emp_email = employees[emp_name]
        current_date = datetime.now()
        thirty_days_ago = current_date - timedelta(days=30)
        
        # --- 3. تطبيق منطق الـ 30 يوم ---
        if not log_df.empty:
            # تحويل عمود التاريخ إلى صيغة datetime للمقارنة
            log_df['Date'] = pd.to_datetime(log_df['Date'])
            # جلب مخالفات الموظف في آخر 30 يوم فقط
            recent_penalties = log_df[(log_df['Employee'] == emp_name) & (log_df['Date'] >= thirty_days_ago)]
            penalty_count = len(recent_penalties)
        else:
            penalty_count = 0

        # تحديد العقوبة بناءً على العدد
        if penalty_count == 0:
            final_penalty = "Yellow Card (إنذار أول)"
        elif penalty_count == 1:
            final_penalty = "Yellow Card (إنذار ثاني)"
        else:
            final_penalty = "Black Card (خصم يومين + حرمان من الترقية 90 يوم)"

        # --- 4. تحديث ملف الإكسيل ---
        new_record = pd.DataFrame({
            "Employee": [emp_name],
            "Email": [emp_email],
            "Infraction": [infraction],
            "Penalty": [final_penalty],
            "Comment": [comment],
            "Date": [current_date.strftime("%Y-%m-%d")]
        })
        
        log_df = pd.concat([log_df, new_record], ignore_index=True)
        log_df.to_excel("penalties_log.xlsx", index=False)
        
        # --- 5. إرسال الإيميل ---
        send_email(emp_email, emp_name, infraction, final_penalty, comment)
        
        st.success(f"تم تسجيل الإجراء بنجاح كـ {final_penalty} وإرسال الإيميل للموظف وتحديث ملف الإكسيل.")