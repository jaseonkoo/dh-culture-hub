import streamlit as st
import datetime
import streamlit.components.v1 as components
import uuid
import pandas as pd
import gspread
import smtplib
import time
from email.mime.text import MIMEText
from email.header import Header
from oauth2client.service_account import ServiceAccountCredentials

# [공통 설정]
WEEKS = ['월', '화', '수', '목', '금', '토', '일']
SYSTEM_URL = "https://dhfeed-culture.streamlit.app" 

def is_company_email(email): 
    return email.strip().lower().endswith("@daehanfeed.co.kr")

def generate_time_slots(start_time, end_time):
    slots = []
    curr = datetime.datetime.combine(datetime.date.today(), start_time)
    end = datetime.datetime.combine(datetime.date.today(), end_time)
    while curr <= end: 
        slots.append(curr.time()); curr += datetime.timedelta(minutes=30)
    return slots

def send_email(to_email, subject, body):
    SMTP_S, SMTP_P = "smtp.dooray.com", 465
    try:
        U, P = st.secrets["email"]["smtp_user"], st.secrets["email"]["smtp_password"]
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'], msg['From'], msg['To'] = Header(subject, 'utf-8'), Header(U), to_email
        with smtplib.SMTP_SSL(SMTP_S, SMTP_P) as server: 
            server.login(U, P); server.sendmail(U, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"⚠️ 도어레이 메일 발송 오류 (비밀번호나 설정을 확인하세요): {e}")
        return False
