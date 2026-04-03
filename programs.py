import streamlit as st
import datetime
import uuid
from core_logic import get_ws, is_company_email, send_email_notification, WEEKS, ALLOWED_DOMAIN

# ✨ 각 프로그램별 구글 시트 파일 이름 설정 (중요!)
DB_FILES = {
    "mentoring": "대한사료_멘토링_DB",
    "leader": "대한사료_리더대화_DB",
    "class": "대한사료_원데이클래스_DB"
}

def fetch_program_data(p_type):
    # 각 파일 내의 'master' 시트에서 기본 정보(멘토 목록 등)를 가져온다고 가정
    ws = get_ws(DB_FILES[p_type], "master")
    try: return ws.get_all_records()
    except: return []

# 🤝 [1. 사내 멘토링 프로그램]
def run_mentoring():
    st.subheader("🗓️ 사내 멘토링 프로그램")
    # 예: 멘토링 신청 내역은 해당 파일의 'reservations' 시트에 저장
    # ws = get_ws(DB_FILES["mentoring"], "reservations")
    st.info(f"현재 '{DB_FILES['mentoring']}' 파일과 연결되어 있습니다.")
    # ... 이후 로직 동일 ...

# ☕ [2. 리더와의 대화]
def run_leader_talk():
    st.subheader("☕ 리더와의 대화")
    st.info(f"현재 '{DB_FILES['leader']}' 파일과 연결되어 있습니다.")

# 🎓 [3. 직무 원데이 클래스]
def run_class():
    st.subheader("🎓 직무 원데이 클래스")
    st.info(f"현재 '{DB_FILES['class']}' 파일과 연결되어 있습니다.")
