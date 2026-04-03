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
SYSTEM_URL = "https://dh-culture-hub.streamlit.app" # 나중에 배포 후 주소 확인 필요
ALLOWED_DOMAIN = "@daehanfeed.co.kr"
WEEKS = ['월', '화', '수', '목', '금', '토', '일']

# --- 구글 스프레드시트 연동 엔진 ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

def get_db():
    client = get_gspread_client()
    return client.open("멘토링예약DB") # 기존 시트 이름을 그대로 쓰거나 새로 만드셔도 됩니다.

def get_ws(name):
    doc = get_db()
    # 시트가 없으면 자동 생성하는 방어 로직
    titles = [w.title for w in doc.worksheets()]
    if name not in titles:
        if name == "stats":
            ws = doc.add_worksheet(name, 10, 2)
            ws.update([["visitor_count"], [0]])
        else:
            # 기본 헤더 설정 (필요시 확장)
            doc.add_worksheet(name, 100, 20)
    return doc.worksheet(name)

# [차장님 절대 규칙 2] 이메일 도메인 체크 함수
def is_company_email(email):
    return email.strip().lower().endswith(ALLOWED_DOMAIN)

# [차장님 절대 규칙 3 & 4] 통합 알림 메일 발송 로직
def send_email_notification(to_email, p_type, mentee, mentor, date, time_range, topic, location):
    SMTP_S, SMTP_P = "smtp.dooray.com", 465
    U, P = st.secrets["email"]["smtp_user"], st.secrets["email"]["smtp_password"]
    
    # 프로그램별 맞춤 제목
    titles = {"mentoring": "사내 멘토링", "leader": "리더와의 대화", "class": "직무 원데이 클래스"}
    display_name = titles.get(p_type, "조직문화 프로그램")
    
    subject = f"[대한사료 {display_name}] 새로운 신청이 접수되었습니다."
    body = (f"안녕하세요, {mentor} 님!\n\n[{display_name}] 프로그램에 {mentee} 님께서 참여를 신청하셨습니다.\n\n"
            f"- 일시: {date} ({time_range})\n"
            f"- 장소: {location}\n"
            f"- 주제: {topic}\n\n"
            f"시스템에 접속하여 상세 내용을 확인해 주세요.\n"
            f"▶ 접속 주소: {SYSTEM_URL}\n\n감사합니다.")
    
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = Header(U)
        msg['To'] = to_email
        with smtplib.SMTP_SSL(SMTP_S, SMTP_P) as server:
            server.login(U, P)
            server.sendmail(U, to_email, msg.as_string())
    except:
        pass # 운영 중 에러로 멈추지 않게 방어

# --- 방문자 통계 관리 ---
def handle_visitor_stats():
    if not st.session_state.get('visited', False):
        ws = get_ws("stats")
        counts = ws.get_all_values()
        new_count = int(counts[1][0]) + 1
        ws.update_cell(2, 1, new_count)
        st.session_state.visited = True
        st.session_state.visitor_count = new_count
