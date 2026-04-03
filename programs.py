import streamlit as st
import datetime
import uuid
# 엔진(core_logic)에서 차장님의 금쪽같은 규칙들을 불러옵니다.
from core_logic import get_ws, is_company_email, send_email_notification, WEEKS, ALLOWED_DOMAIN

# --- 공통 데이터 로드 함수 ---
def fetch_program_data(p_type):
    # p_type에 따라 다른 시트를 참조합니다 (mentors, leaders, teachers 등)
    sheet_map = {"mentoring": "mentors", "leader": "leaders", "class": "teachers"}
    try:
        data = get_ws(sheet_map[p_type]).get_all_records()
        return data
    except: return []

# ==========================================
# 🤝 [1. 사내 멘토링 프로그램 로직]
# ==========================================
def run_mentoring():
    st.subheader("🗓️ 멘토링 예약 신청")
    
    # 멘토 데이터 및 슬롯 데이터 가져오기 (기존 로직 유지)
    mentors = fetch_program_data("mentoring")
    mentor_names = ["선택해주세요"] + [m['name'] for m in mentors]
    
    tab_apply, tab_manage = st.tabs(["🙋‍♂️ 멘티 신청", "💼 멘토 관리"])

    with tab_apply:
        st.info("선배 멘토님을 선택하고 상담 일정을 예약하세요.")
        c1, c2 = st.columns(2)
        m_name = c1.text_input("신청자 성함", key="mentee_n")
        m_email = c2.text_input("사내 이메일", key="mentee_e", placeholder=f"example{ALLOWED_DOMAIN}")
        
        selected_m = st.selectbox("멘토 선택", mentor_names)
        
        if st.button("🚀 멘토링 신청하기"):
            if is_company_email(m_email) and m_name and selected_m != "선택해주세요":
                # 여기에 예약 저장 및 엔진(core_logic)의 메일 발송 호출!
                # send_email_notification(m_email, "mentoring", m_name, selected_m, ...)
                st.success(f"{selected_m} 멘토님께 신청 메일이 발송되었습니다!")
            else:
                st.error(f"정보를 정확히 입력해주세요. (이메일은 {ALLOWED_DOMAIN} 전용)")

    with tab_manage:
        st.write("멘토 전용 관리 화면입니다.")

# ==========================================
# ☕ [2. 리더와의 대화 로직]
# ==========================================
def run_leader_talk():
    st.subheader("☕ 경영진/팀장님과의 커피챗")
    st.markdown("---")
    st.write("리더분들과의 격식 없는 소통을 신청해 보세요.")
    # 리더 전용 데이터 로직 (멘토링과 유사하게 확장 가능)
    st.warning("현재 리더분들의 일정을 조율 중입니다.")

# ==========================================
# 🎓 [3. 직무 원데이 클래스 로직]
# ==========================================
def run_class():
    st.subheader("🎓 부서별 직무 원데이 클래스")
    st.markdown("---")
    st.write("동료들의 전문 지식을 배우고 함께 성장하는 교육 마당입니다.")
    # 클래스 전용 데이터 로직
    st.warning("개설 예정인 강의 목록을 준비 중입니다.")
