import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import base64
from ..core.config import settings


def send_violation_email(
    emp_email: str,
    manager_email: str,
    emp_name: str,
    category: str,
    incident: str,
    penalty_color: str,
    comment: str,
    applied_days: float,
    proof_b64: str = "",
    smtp_config: dict = None,
) -> bool:
    cfg = smtp_config or {}
    smtp_server   = cfg.get("server")   or settings.SMTP_SERVER
    smtp_port     = int(cfg.get("port") or settings.SMTP_PORT)
    smtp_user     = cfg.get("user")     or settings.SMTP_USER
    smtp_password = cfg.get("password") or settings.SMTP_PASSWORD

    if not smtp_user or not smtp_password:
        print("❌ SMTP credentials missing — email skipped.")
        return False

    try:
        img_data = None
        if proof_b64:
            try:
                raw = proof_b64.split(",")[1] if "," in proof_b64 else proof_b64
                img_data = base64.b64decode(raw)
            except Exception as e:
                print(f"⚠️ Image decode failed: {e}")

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)

            if emp_email:
                msg = MIMEMultipart()
                msg["From"] = smtp_user
                msg["To"] = emp_email
                msg["Subject"] = f"Disciplinary Action: {penalty_color} Card"
                body = (
                    f"Dear {emp_name},\n\n"
                    f"A disciplinary action has been recorded on your file:\n\n"
                    f"  Incident : {incident} ({category})\n"
                    f"  Penalty  : {penalty_color}\n"
                    f"  HR Notes : {comment}\n\n"
                    f"Please adhere to company policies to avoid further escalation.\n\n"
                    f"Human Resources Department"
                )
                msg.attach(MIMEText(body, "plain"))
                if img_data:
                    msg.attach(MIMEImage(img_data, name="proof.jpg"))
                server.sendmail(smtp_user, emp_email, msg.as_string())
                print(f"✅ Email sent to employee: {emp_email}")

            if manager_email:
                msg = MIMEMultipart()
                msg["From"] = smtp_user
                msg["To"] = manager_email
                msg["Subject"] = f"Manager Alert — {emp_name} received {penalty_color}"
                body = (
                    f"Dear Manager,\n\n"
                    f"Your team member {emp_name} has received a disciplinary penalty.\n\n"
                    f"  Incident : {incident} ({category})\n"
                    f"  Penalty  : {penalty_color}\n"
                    f"  Notes    : {comment}"
                )
                msg.attach(MIMEText(body, "plain"))
                if img_data:
                    msg.attach(MIMEImage(img_data, name="proof.jpg"))
                server.sendmail(smtp_user, manager_email, msg.as_string())
                print(f"✅ Email sent to manager: {manager_email}")

        return True
    except Exception as e:
        print(f"❌ SMTP error: {e}")
        return False
