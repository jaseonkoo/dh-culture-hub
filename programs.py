import streamlit as st
import datetime
import uuid
import pandas as pd
from core_logic import get_ws, is_company_email, send_email_notification, ALLOWED_DOMAIN

DB_FILES = {"mentoring": "대한사료_멘토링_DB"}

def run_mentoring():
    st.header("🤝 사내 멘토링 프로그램")
    
    # 1. 멘토 명단 가져오기 (차장님의 시트 컬럼명 반영)
    ws_master = get_ws(DB_FILES["mentoring"], "mentors")
    if ws_master:
        mentor_data = pd.DataFrame(ws_master.get_all_records())
    else:
        st.error("멘토 명단을 불러올 수 없습니다. 구글 시트 이름을 확인하세요.")
        return

    # 탭 구성: 신청하기 / 현황보기
    tab_apply, tab_list = st.tabs(["📝 신청하기", "📋 신청 현황"])

    with tab_apply:
        # 멘토 선택 시 상세 정보 미리보기 (차장님 데이터 기반)
        mentor_list = mentor_data['name'].tolist() if not mentor_data.empty else []
        selected_m = st.selectbox("상담받고 싶은 멘토를 선택하세요", ["선택하세요"] + mentor_list)

        if selected_m != "선택하세요":
            # 선택한 멘토의 상세 정보를 보여줍니다.
            m_info = mentor_data[mentor_data['name'] == selected_m].iloc[0]
            st.info(f"💡 **[{m_info['position']}] {selected_m} 멘토님** ({m_info['team']})\n\n"
                    f"🔹 **전문분야:** {m_info['expertise']}\n"
                    f"🔹 **인사말:** {m_info['greeting']}")

        st.markdown("---")
        
        with st.form("mentoring_form"):
            st.subheader("신청서 작성")
            c1, c2, c3 = st.columns(3)
            m_name = c1.text_input("신청자 성함")
            m_pos = c2.text_input("직급")
            m_team = c3.text_input("소속 팀")
            
            m_email = st.text_input("사내 이메일", placeholder=f"ID{ALLOWED_DOMAIN}")
            topic = st.text_area("상담받고 싶은 구체적인 내용")
            
            c4, c5, c6 = st.columns(3)
            res_date = c4.date_input("희망 날짜", datetime.date.today())
            s_time = c5.time_input("시작 시간", datetime.time(10, 0))
            e_time = c6.time_input("종료 시간", datetime.time(11, 0))

            if st.form_submit_button("🚀 신청하기"):
                if is_company_email(m_email) and selected_m != "선택하세요" and m_name:
                    ws_res = get_ws(DB_FILES["mentoring"], "reservations")
                    
                    new_id = str(uuid.uuid4())[:8]
                    # 예약 저장 시 순서: id, mentor, mentee_name, mentee_position, mentee_team, mentee_email, date, start_time, end_time, topic, status, location
                    new_row = [
                        new_id, selected_m, m_name, m_pos, m_team, m_email, 
                        str(res_date), str(s_time), str(e_time), topic, "대기중", "추후결정"
                    ]
                    
                    ws_res.append_row(new_row)
                    
                    # 멘토에게 메일 알림
                    m_email_addr = mentor_data[mentor_data['name'] == selected_m]['email'].values[0]
                    send_email_notification(m_email_addr, "mentoring", m_name, selected_m, str(res_date), f"{s_time}-{e_time}", topic, "미정")
                    
                    st.success(f"{selected_m} 멘토님께 신청이 완료되었습니다!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("모든 항목을 정확히 입력해 주세요.")

    with tab_list:
        st.subheader("최근 신청 현황")
        ws_res = get_ws(DB_FILES["mentoring"], "reservations")
        if ws_res:
            res_data = pd.DataFrame(ws_res.get_all_records())
            if not res_data.empty:
                st.dataframe(res_data.tail(10), use_container_width=True)
            else:
                st.write("아직 신청 내역이 없습니다.")
