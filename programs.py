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
# 🤝 [1. 사내 멘토링 프로그램]
# ==========================================
def run_mentoring():
    st.header("🤝 사내 멘토링 프로그램")
    st.caption("선배의 노하우를 전수받고 함께 성장하는 대한사료만의 멘토링 시간입니다.")
    
    # 1. 멘토 명단 불러오기
    ws_master = get_ws(DB_FILES["mentoring"], "mentors")
    if ws_master:
        mentor_data = pd.DataFrame(ws_master.get_all_records())
    else:
        st.error("멘토 명단을 불러올 수 없습니다. 구글 시트의 'mentors' 탭을 확인해 주세요.")
        return

    # 탭 구성
    tab_apply, tab_list = st.tabs(["🙋‍♂️ 멘토링 신청하기", "📋 전체 신청 현황"])

    with tab_apply:
        mentor_list = mentor_data['name'].tolist() if not mentor_data.empty else []
        selected_m = st.selectbox("먼저 상담받고 싶은 멘토를 선택하세요", ["선택하세요"] + mentor_list)

        if selected_m != "선택하세요":
            m_info = mentor_data[mentor_data['name'] == selected_m].iloc[0]
            with st.expander(f"✨ {selected_m} 멘토님 프로필 상세보기", expanded=True):
                col_a, col_b = st.columns([1, 2])
                # 시트 컬럼명에 맞게 데이터 표시
                col_a.metric("소속/직급", f"{m_info.get('team', 'N/A')} / {m_info.get('position', 'N/A')}")
                col_b.write(f"✅ **전문 분야:** {m_info.get('expertise', 'N/A')}")
                col_b.write(f"💬 **인사말:** {m_info.get('greeting', 'N/A')}")

        st.markdown("---")
        
        with st.form("mentoring_full_form"):
            st.subheader("📝 신청서 작성")
            
            row1_1, row1_2, row1_3 = st.columns(3)
            m_name = row1_1.text_input("신청자 성함")
            m_pos = row1_2.text_input("직급")
            m_team = row1_3.text_input("소속 팀")
            
            m_email = st.text_input("사내 이메일", placeholder=f"ID{ALLOWED_DOMAIN}")
            topic = st.text_area("상담받고 싶은 주제")
            
            row2_1, row2_2, row2_3 = st.columns(3)
            res_date = row2_1.date_input("희망 날짜", datetime.date.today())
            s_time = row2_2.time_input("시작 시간", datetime.time(10, 0))
            e_time = row2_3.time_input("종료 시간", datetime.time(11, 0))

            submit_btn = st.form_submit_button("🚀 멘토링 신청하기")
            
            if submit_btn:
                if not is_company_email(m_email):
                    st.error(f"❌ 이메일 형식을 확인하세요. ({ALLOWED_DOMAIN} 전용)")
                elif selected_m == "선택하세요":
                    st.error("❌ 상담받을 멘토를 선택해 주세요.")
                elif not m_name or not topic:
                    st.error("❌ 모든 항목을 입력해 주세요.")
                else:
                    ws_res = get_ws(DB_FILES["mentoring"], "reservations")
                    new_id = str(uuid.uuid4())[:8]
                    new_row = [
                        new_id, selected_m, m_name, m_pos, m_team, m_email, 
                        str(res_date), str(s_time), str(e_time), topic, "대기중", "추후결정"
                    ]
                    ws_res.append_row(new_row)
                    
                    # 멘토 메일 발송
                    m_email_addr = mentor_data[mentor_data['name'] == selected_m]['email'].values[0]
                    send_email_notification(
                        m_email_addr, "mentoring", m_name, selected_m, 
                        str(res_date), f"{s_time}-{e_time}", topic, "추후 결정"
                    )
                    
                    st.balloons()
                    st.success(f"✅ {selected_m} 멘토님께 신청 완료!")

    with tab_list:
        st.subheader("📋 최근 멘토링 신청 내역")
        ws_res = get_ws(DB_FILES["mentoring"], "reservations")
        if ws_res:
            res_all = pd.DataFrame(ws_res.get_all_records())
            if not res_all.empty:
                st.dataframe(res_all.tail(15), use_container_width=True)
            else:
                st.write("아직 신청 내역이 없습니다.")

# ==========================================
# ☕ [2. 리더와의 대화] / 🎓 [3. 원데이 클래스]
# ==========================================
def run_leader_talk():
    st.header("☕ 리더와의 대화")
    st.info("준비 중입니다.")

def run_class():
    st.header("🎓 직무 원데이 클래스")
    st.info("준비 중입니다.")
