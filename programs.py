import streamlit as st
import datetime
import uuid
import pandas as pd
# 엔진(core_logic)에서 차장님의 규칙들을 불러옵니다.
from core_logic import get_ws, is_company_email, send_email_notification, ALLOWED_DOMAIN

# 프로그램별 구글 시트 파일 이름 설정
DB_FILES = {
    "mentoring": "대한사료_멘토링_DB",
    "leader": "대한사료_리더대화_DB",
    "class": "대한사료_원데이클래스_DB"
}

# ==========================================
# 🤝 [1. 사내 멘토링 프로그램] - 버전 1 완벽 재현
# ==========================================
def run_mentoring():
    st.header("🤝 사내 멘토링 프로그램")
    st.caption("선배의 노하우를 전수받고 함께 성장하는 대한사료만의 멘토링 시간입니다.")
    
    # 1. 멘토 명단 불러오기 (차장님의 'mentors' 시트 기준)
    ws_master = get_ws(DB_FILES["mentoring"], "mentors")
    if ws_master:
        mentor_data = pd.DataFrame(ws_master.get_all_records())
    else:
        st.error("멘토 명단을 불러올 수 없습니다. 구글 시트의 'mentors' 탭을 확인해 주세요.")
        return

    # 탭 구성: 신청하기 / 신청 현황
    tab_apply, tab_list = st.tabs(["🙋‍♂️ 멘토링 신청하기", "📋 전체 신청 현황"])

    with tab_apply:
        # 멘토 선택 드롭다운
        mentor_list = mentor_data['name'].tolist() if not mentor_data.empty else []
        selected_m = st.selectbox("먼저 상담받고 싶은 멘토를 선택하세요", ["선택하세요"] + mentor_list)

        # 멘토를 선택하면 프로필 정보를 예쁘게 보여줍니다.
        if selected_m != "선택하세요":
            m_info = mentor_data[mentor_data['name'] == selected_m].iloc[0]
            with st.expander(f"✨ {selected_m} 멘토님 프로필 상세보기", expanded=True):
                col_a, col_b = st.columns([1, 2])
                col_a.metric("소속/직급", f"{m_info['team']} / {m_info['position']}")
                col_b.write(f"✅ **전문 분야:** {m_info['expertise']}")
                col_b.write(f"💬 **인사말:** {m_info['greeting']}")

        st.markdown("---")
        
        # 신청서 폼
        with st.form("mentoring_full_form"):
            st.subheader("📝 신청서 작성")
            
            row1_1, row1_2, row1_3 = st.columns(3)
            m_name = row1_1.text_input("신청자 성함", placeholder="성함을 입력하세요")
            m_pos = row1_2.text_input("직급", placeholder="예: 대리")
            m_team = row1_3.text_input("소속 팀", placeholder="예: 생산1팀")
            
            m_email = st.text_input("사내 이메일", placeholder=f"반
