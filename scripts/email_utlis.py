import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Конфигурация электронной почты
EMAIL_USER = 'oleg.pytin@gmail.com'
EMAIL_PASSWORD = 'cemi zewp jzeu phun'
EMAIL_RECIPIENT = 'oleg.pytin@gmail.com'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, EMAIL_RECIPIENT, msg.as_string())
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")
