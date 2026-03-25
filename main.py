import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import plotly.express as px

# ==========================================
# 1. إعدادات النظام وقاموس العقوبات (مطابق للإكسيل)
# ==========================================
st.set_page_config(page_title="HR Disciplinary System", page_icon="⚖️", layout="wide")

PENALTY_MAP = {
    "Yellow": {"label": "Performance Notice", "deduction_hours": 0, "deduction_days": 0, "freeze_months": 0},
    "Orange": {"label": "Performance Flag + 4.5 hrs. 'Half Day' Deduction", "deduction_hours": 4.5, "deduction_days": 0, "freeze_months": 0},
    "Red": {"label": "Performance Alert + 2 Days Deduction", "deduction_hours": 0, "deduction_days": 2, "freeze_months": 0},
    "Black": {"label": "Performance Warning + 4 Days Deduction + 3 Months Freeze", "deduction_hours": 0, "deduction_days": 4, "freeze_months": 3},
    "Investigation": {"label": "Employee is suspended and transferred to Investigation on Spot", "deduction_hours": 0, "deduction_days": 0, "freeze_months": 0},
}

SENDER_EMAIL = st.secrets.get("EMAIL", "")
SENDER_PASSWORD = st.secrets.get("PASSWORD", "")
HR_MANAGER_EMAIL = st.secrets.get("HR_MANAGER_EMAIL", SENDER_EMAIL)
HR_ADMIN_PASSWORD = st.secrets.get("HR_ADMIN_PASSWORD", "1234")

# ==========================================
# 2. مصفوفة الأخطاء الكاملة (The Exact Excel Matrix)
# ==========================================
MATRIX_DATA = {
    "Attendance & adherance": {
        "Late Arrival": {"reset": 30, "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
        "No-show": {"reset": 90, "escalation": ["Red", "Red", "Black", "Investigation"]},
        "Exceed breaks": {"reset": 30, "escalation": ["Yellow", "Yellow", "Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
        "Un-scheduled breaks": {"reset": 30, "escalation": ["Yellow", "Red", "Black", "Investigation"]},
        "Out of working hours attendance": {"reset": 90, "escalation": ["Yellow", "Red", "Black", "Investigation"]},
        "Attendance manipulation": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Early leave": {"reset": 180, "escalation": ["Black", "Investigation"]},
    },
    "Personal Attitude": {
        "Use of abusive words": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Physical harm": {"reset": 180, "escalation": ["Investigation"]},
        "Sleeping on the floor": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Unprofessional behavior": {"reset": 180, "escalation": ["Black", "Investigation"]},
    },
    "Abusing": {
        "Company assets": {"reset": 180, "escalation": ["Investigation"]},
        "Routing calls / tickets": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Releasing calls / tickets": {"reset": 180, "escalation": ["Investigation"]},
        "Using other colleague's logins": {"reset": 180, "escalation": ["Investigation"]},
        "Aux system reports & tools": {"reset": 30, "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
    },
    "Policy": {
        "Medical examination": {"reset": 180, "escalation": ["Investigation"]},
        "Visitors": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Smoking": {"reset": 180, "escalation": ["Black", "Investigation"]},
        "Influence of Alcohol / drugs": {"reset": 180, "escalation": ["Investigation"]},
        "Harassment": {"reset": 180, "escalation": ["Investigation"]},
        "Stealing": {"reset": 180, "escalation": ["Investigation"]},
        "Social media": {"reset": 180, "escalation": ["Investigation"]},
        "Data confidentiality, ethical conduct, and damage control": {"reset": 180, "escalation": ["Investigation"]},
        "Mobile phones": {"reset": 30, "escalation": ["Red", "Black", "Investigation"]},
        "Food & beverage": {"reset": 30, "escalation": ["Orange", "Red", "Black", "Investigation"]},
        "Business process failure": {"reset": 30, "escalation": ["Orange", "Red", "Black", "Investigation"]},
        "End-user critical failure": {"reset": 60, "escalation": ["Black", "Investigation"]},
        "Cyber security": {"reset": 30, "escalation": ["Red", "Black", "Investigation"]},
        "Unprofessional behaviorss": {"reset": 30, "escalation": ["Orange", "Black", "Investigation"]},
    }
}

# ==========================================
# 3. إعداد قاعدة البيانات
# ==========================================
DB_FILE = "hr_system.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS employees 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, email TEXT, department TEXT, manager_email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS violations 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_name TEXT, category TEXT, 
                 incident TEXT, penalty_color TEXT, penalty_label TEXT, deduction_hours REAL, 
                 deduction_days INTEGER, freeze_months INTEGER, comment TEXT, 
                 submitted_by TEXT, created_at DATETIME)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

# ==========================================
# 4. دوال إرسال الإيميلات (مفصولة: للموظف وللمدير)
# ==========================================
def send_email(emp_email, manager_email, emp_name, category, incident, penalty_color, comment):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("⚠️ Email settings missing.")
        return False
        
    p_info = PENALTY_MAP.get(penalty_color, PENALTY_MAP["Yellow"])
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)

            # --- الإيميل الموجه للموظف ---
            msg_emp = MIMEMultipart()
            msg_emp['From'] = SENDER_EMAIL
            msg_emp['To'] = emp_email
            if penalty_color == "Investigation":
                msg_emp['Subject'] = f"URGENT: Suspension Notice - {emp_name}"
                body_emp = f"Dear {emp_name},\n\nYou are hereby suspended from work pending an investigation regarding:\nCategory: {category}\nIncident: {incident}\nHR Notes: {comment}\n\nHR will contact you shortly."
            else:
                msg_emp['Subject'] = f"Disciplinary Action: {penalty_color} Card"
                body_emp = f"Dear {emp_name},\n\nA disciplinary action has been recorded on your file:\n\n- Incident: {incident} ({category})\n- Penalty: {p_info['label']}\n- HR Notes: {comment}\n\nPlease adhere to company policies to avoid further escalation."
            
            msg_emp.attach(MIMEText(body_emp, 'plain', 'utf-8'))
            server.sendmail(SENDER_EMAIL, [emp_email], msg_emp.as_string())

            # --- الإيميل الموجه للمدير المباشر ---
            if manager_email:
                msg_mgr = MIMEMultipart()
                msg_mgr['From'] = SENDER_EMAIL
                msg_mgr['To'] = manager_email
                msg_mgr['Subject'] = f"Manager Notification: Penalty issued for {emp_name}"
                
                body_mgr = f"Dear Manager,\n\nThis is to notify you that your team member, {emp_name}, has received a disciplinary penalty.\n\nDetails:\n- Incident: {incident} ({category})\n- Penalty Given: {p_info['label']}\n- HR Alignment/Notes: {comment}\n\nPlease review and guide the employee accordingly."
                
                if penalty_color == "Investigation":
                    msg_mgr['Cc'] = HR_MANAGER_EMAIL
                    body_mgr += f"\n\n🚨 NOTE: The employee has been SUSPENDED pending investigation."
                    receivers_mgr = [manager_email, HR_MANAGER_EMAIL]
                else:
                    receivers_mgr = [manager_email]

                msg_mgr.attach(MIMEText(body_mgr, 'plain', 'utf-8'))
                server.sendmail(SENDER_EMAIL, receivers_mgr, msg_mgr.as_string())

        return True
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return False

# ==========================================
# 5. نظام الحماية
# ==========================================
def check_password(tab_id):
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        pwd = st.text_input("🔑 Enter HR Password:", type="password", key=f"pwd_input_{tab_id}")
        if st.button("Login", key=f"login_btn_{tab_id}"):
            if pwd == HR_ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect Password.")
        return False
    return True

# ==========================================
# 6. واجهة المستخدم (UI & Tabs)
# ==========================================
st.title("HR Disciplinary System 🟨⬛")

tab1, tab2, tab3 = st.tabs(["📝 Log Violation", "⚙️ Admin Dashboard", "📊 Reports & Payroll"])

# ---------------- Tab 1: تسجيل المخالفة ----------------
with tab1:
    conn = get_db_connection()
    employees_df = pd.read_sql_query("SELECT * FROM employees", conn)
    
    if employees_df.empty:
        st.warning("Please add employees from the Admin Dashboard first.")
    else:
        with st.form("penalty_form"):
            st.subheader("Violation Details")
            
            submitted_by = st.text_input("HR Rep Name (Audit):")
            emp_name = st.selectbox("Select Employee", employees_df['name'].tolist())
            
            col1, col2 = st.columns(2)
            with col1:
                # القوائم الديناميكية المربوطة ببعضها
                category = st.selectbox("Category", list(MATRIX_DATA.keys()))
            with col2:
                incident = st.selectbox("Incident", list(MATRIX_DATA[category].keys()))
            
            # عرض فترة السماح أوتوماتيكياً للـ HR
            reset_days = MATRIX_DATA[category][incident]["reset"]
            st.info(f"ℹ️ Reset Period for this incident is: **{reset_days} Days**")
            
            comment = st.text_area("HR Comments / Alignment details")
            submitted = st.form_submit_button("Submit & Notify")

            if submitted:
                if not submitted_by:
                    st.error("⚠️ HR Rep Name is required.")
                else:
                    emp_data = employees_df[employees_df['name'] == emp_name].iloc[0]
                    emp_email = emp_data['email']
                    manager_email = emp_data['manager_email']
                    current_date = datetime.now()
                    cutoff_date = current_date - timedelta(days=reset_days)
                    
                    # حساب عدد المخالفات لنفس الخطأ خلال فترة السماح
                    c = conn.cursor()
                    c.execute('''SELECT COUNT(*) FROM violations 
                                 WHERE employee_name=? AND incident=? AND created_at >= ? AND penalty_color != 'Investigation' ''', 
                              (emp_name, incident, cutoff_date.strftime("%Y-%m-%d %H:%M:%S")))
                    penalty_count = c.fetchone()[0]
                    
                    escalation_list = MATRIX_DATA[category][incident]["escalation"]
                    
                    # تحديد لون العقوبة بناءً على سلم التصعيد الخاص بالخطأ
                    if penalty_count >= len(escalation_list):
                        final_color = escalation_list[-1] # الوصول للحد الأقصى (غالباً تحقيق)
                    else:
                        final_color = escalation_list[penalty_count]

                    p_info = PENALTY_MAP[final_color]
                    c = conn.cursor()
                    c.execute('''INSERT INTO violations 
                                 (employee_name, category, incident, penalty_color, penalty_label, 
                                 deduction_hours, deduction_days, freeze_months, comment, submitted_by, created_at) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (emp_name, category, incident, final_color, p_info['label'], 
                               p_info['deduction_hours'], p_info['deduction_days'], p_info['freeze_months'], 
                               comment, submitted_by, current_date.strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    
                    email_sent = send_email(emp_email, manager_email, emp_name, category, incident, final_color, comment)
                    
                    if email_sent:
                        st.success(f"✅ Action Logged: {final_color} ({p_info['label']}). Emails sent to Employee & Manager.")
                    else:
                        st.warning(f"Action Logged: {final_color}, but email failed.")
    conn.close()

# ---------------- Tab 2: لوحة الإدارة ----------------
with tab2:
    if check_password("tab2"):
        conn = get_db_connection()
        st.subheader("👥 Manage Employees")
        
        with st.form("add_emp_form"):
            e_name = st.text_input("Employee Name")
            e_email = st.text_input("Employee Email")
            e_dept = st.text_input("Department")
            e_manager = st.text_input("Manager Email (For CC)")
            if st.form_submit_button("Add / Update Employee"):
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO employees (name, email, department, manager_email) VALUES (?, ?, ?, ?)", 
                          (e_name, e_email, e_dept, e_manager))
                conn.commit()
                st.success("Employee Saved.")
                st.rerun()
                
        st.write("---")
        st.subheader("❌ Delete Penalty Record")
        v_df = pd.read_sql_query("SELECT id, employee_name, incident, penalty_label, created_at FROM violations", conn)
        if not v_df.empty:
            st.dataframe(v_df, use_container_width=True)
            v_id = st.selectbox("Select Record ID to Delete:", v_df['id'])
            if st.button("Delete Permanently"):
                conn.cursor().execute("DELETE FROM violations WHERE id=?", (v_id,))
                conn.commit()
                st.success("Deleted successfully.")
                st.rerun()
        conn.close()
        
        if st.button("Logout", key="logout_tab2"):
            st.session_state.authenticated = False
            st.rerun()

# ---------------- Tab 3: التقارير والإحصائيات ----------------
with tab3:
    if check_password("tab3"):
        conn = get_db_connection()
        st.header("📊 HR & Payroll Reports")
        
        violations_df = pd.read_sql_query("SELECT * FROM violations", conn)
        
        if violations_df.empty:
            st.info("No data available.")
        else:
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                fig1 = px.pie(violations_df, names='category', title='Violations by Category')
                st.plotly_chart(fig1, use_container_width=True)
            with col_chart2:
                emp_counts = violations_df['employee_name'].value_counts().reset_index()
                emp_counts.columns = ['employee_name', 'count']
                fig2 = px.bar(emp_counts, x='employee_name', y='count', title='Top Violators')
                st.plotly_chart(fig2, use_container_width=True)
            
            st.write("---")
            st.subheader("⚠️ Payroll Deductions & Promotion Freezes")
            
            violations_df['created_at'] = pd.to_datetime(violations_df['created_at'])
            violations_df['freeze_end_date'] = violations_df.apply(
                lambda row: (row['created_at'] + pd.DateOffset(months=int(row['freeze_months']))) if row['freeze_months'] > 0 else None, axis=1
            )
            violations_df['is_frozen'] = violations_df['freeze_end_date'].apply(
                lambda d: "Yes" if pd.notnull(d) and d > datetime.now() else "No"
            )
            
            export_df = violations_df[['employee_name', 'incident', 'penalty_label', 'deduction_days', 'deduction_hours', 'freeze_end_date', 'is_frozen', 'created_at']]
            st.dataframe(export_df, use_container_width=True)
            
            csv = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 Export to CSV", data=csv, file_name="payroll_report.csv", mime="text/csv")
            
        if st.button("Logout", key="logout_tab3"):
            st.session_state.authenticated = False
            st.rerun()
            
        conn.close()