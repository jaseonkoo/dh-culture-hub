import streamlit as st
import datetime
import uuid
import pandas as pd
import gspread
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from oauth2client.service_account import ServiceAccountCredentials

# [차장님 절대 규칙 1] 시스템 기본 설정
SYSTEM_URL = "https://dh-culture-hub.streamlit.app"
ALLOWED_DOMAIN = "@daehanfeed.co.kr"
WEEKS = ['월', '화', '수', '목', '금', '토', '일']

@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

# ✨ 수정됨: 파일 이름을 인자로 받아 해당 파일을 엽니다.
def get_db(file_name):
    client = get_gspread_client()
    try:
        return client.open(file_name)
    except:
        st.error(f"⚠️ 구글 드라이브에서 '{file_name}' 파일을 찾을 수 없습니다. 파일명과 공유 설정을 확인해주세요.")
        return None

# ✨ 수정됨: 파일명과 시트명을 모두 받아 워크시트를 반환합니다.
def get_ws(file_name, sheet_name):
    doc = get_db(file_name)
    if doc is None: return None
    
    titles = [w.title for w in doc.worksheets()]
    if sheet_name not in titles:
        if sheet_name == "stats":
            ws = doc.add_worksheet(sheet_name, 10, 2)
            ws.update([["visitor_count"], [0]])
        else:
            doc.add_worksheet(sheet_name, 100, 20)
    return doc.worksheet(sheet_name)

def is_company_email(email):
    return email.strip().lower().endswith(ALLOWED_DOMAIN)

def send_email_notification(to_email, p_type, mentee, mentor, date, time_range, topic, location):
    SMTP_S, SMTP_P = "smtp.dooray.com", 465
    U, P = st.secrets["email"]["smtp_user"], st.secrets["email"]["smtp_password"]
    
    titles = {"mentoring": "사내 멘토링", "leader": "리더와의 대화", "class": "직무 원데이 클래스"}
    display_name = titles.get(p_type, "조직문화 프로그램")
    
    subject = f"[대한사료 {display_name}] 새로운 신청이 접수되었습니다."
    body = (f"안녕하세요, {mentor} 님!\n\n[{display_name}] 프로그램에 {mentee} 님께서 참여를 신청하셨습니다.\n\n"
            f"- 일시: {date} ({time_range})\n- 장소: {location}\n- 주제: {topic}\n\n"
            f"시스템 접속: {SYSTEM_URL}\n\n감사합니다.")
    
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8'); msg['From'] = Header(U); msg['To'] = to_email
        with smtplib.SMTP_SSL(SMTP_S, SMTP_P) as server:
            server.login(U, P); server.sendmail(U, to_email, msg.as_string())
    except: pass

def handle_visitor_stats():
    if not st.session_state.get('visited', False):
        # 통계 데이터는 '대한사료_통합통계_DB' 파일에 따로 저장하도록 설정 가능
        ws = get_ws("대한사료_통합통계_DB", "stats")
        if ws:
            counts = ws.get_all_values()
            new_count = int(counts[1][0]) + 1
            ws.update_cell(2, 1, new_count)
            st.session_state.visited = True
            st.session_state.visitor_count = new_count
