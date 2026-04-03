import streamlit as st
import datetime
import uuid
import pandas as pd
from core_logic import get_ws, is_company_email, send_email_notification, ALLOWED_DOMAIN

DB_FILES = {"mentoring": "대한사료_멘토링_DB"}

def run_mentoring():
    st.header("🤝 사내 멘토링 프로그램")
    
    # 1. 멘토 명단 가져오기 (시트 이름이 'mentors'인지 확인하세요!)
    ws_master = get_ws(DB_FILES["mentoring"], "mentors")
    if ws_master:
        mentor_data = pd.DataFrame(ws_master.get_all_records())
    else:
        st.error("멘토 명단을 불러올 수 없습니다.")
        return

    # 2. 신청 양식 (이미지 속 컬럼들에 맞춤)
    with st.form("mentoring_form"):
        st.subheader("📝 멘토링 신청서 작성")
        
        c1, c2, c3 = st.columns(3)
        m_name = c1.text_input("신청자 성함")
        m_pos = c2.text_input("직급 (예: 대리)")
        m_team = c3.text_input("소속 팀 (예: 인사총무팀)")
        
        m_email = st.text_input("사내 이메일", placeholder=f"ID{ALLOWED_DOMAIN}")
        
        mentor_list = mentor_data['name'].tolist() if 'name' in mentor_data else []
        selected_m = st.selectbox("멘토 선택", ["선택하세요"] + mentor_list)
        
        topic = st.text_area("상담 주제", placeholder="상담하고 싶은 내용을 적어주세요.")
        
        # 날짜와 시간 설정 (기본값)
        c4, c5, c6 = st.columns(3)
        res_date = c4.date_input("희망 날짜", datetime.date.today())
        s_time = c5.time_input("시작 시간", datetime.time(12, 0))
        e_time = c6.time_input("종료 시간", datetime.time(13, 0))

        if st.form_submit_button("🚀 신청하기"):
            if is_company_email(m_email) and selected_m != "선택하세요" and m_name:
                ws_res = get_ws(DB_FILES["mentoring"], "reservations")
                
                # ✨ 이미지 속 표 순서와 동일하게 저장 (25번 행 기준)
                # id, mentor, mentee_name, mentee_position, mentee_team, mentee_email, date, start_time, end_time, topic, status, location
                new_id = str(uuid.uuid4())[:8] # 짧은 ID 생성
                new_row = [
                    new_id, selected_m, m_name, m_pos, m_team, m_email, 
                    str(res_date), str(s_time), str(e_time), topic, "대기중", "미정"
                ]
                
                ws_res.append_row(new_row)
                
                # 멘토에게 알림 메일 발송
                try:
                    m_email_addr = mentor_data[mentor_data['name'] == selected_m]['email'].values[0]
                    send_email_notification(m_email_addr, "mentoring", m_name, selected_m, str(res_date), f"{s_time}-{e_time}", topic, "미정")
                except: pass
                
                st.success("신청이 완료되었습니다!")
                st.balloons()
                st.rerun()
            else:
                st.error("입력 정보를 다시 확인해 주세요.")

    # 3. 최근 신청 현황 (이미지처럼 아래에 배치)
    st.markdown("---")
    st.subheader("📋 최근 신청 현황")
    ws_res = get_ws(DB_FILES["mentoring"], "reservations")
    if ws_res:
        res_data = pd.DataFrame(ws_res.get_all_records())
        if not res_data.empty:
            # 최신순으로 정렬해서 보여주기
            st.dataframe(res_data.tail(10), use_container_width=True)
