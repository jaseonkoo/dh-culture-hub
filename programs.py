import streamlit as st
import datetime
import pandas as pd
from core_logic import get_ws, is_company_email, send_email_notification, ALLOWED_DOMAIN

# ✨ 새 플랫폼의 파일 관리 규칙
DB_FILES = {
    "mentoring": "대한사료_멘토링_DB", # 차장님이 만드신 새 파일명
}

def run_mentoring():
    st.header("🤝 사내 멘토링 프로그램")
    
    # 1. 기존과 동일한 시트 이름(예: mentors)에서 데이터를 가져옵니다.
    ws_master = get_ws(DB_FILES["mentoring"], "mentors") # 시트 이름이 다르면 수정하세요!
    if ws_master:
        mentor_data = pd.DataFrame(ws_master.get_all_records())
    else:
        st.error("데이터를 불러올 수 없습니다. 구글 시트 이름과 권한을 확인하세요.")
        return

    # --- 기존의 '버전 1' 신청 양식을 그대로 배치 ---
    with st.form("mentoring_form"):
        st.subheader("📝 멘토링 신청서")
        m_name = st.text_input("신청자 성함")
        m_email = st.text_input("사내 이메일")
        
        # 시트의 'name' 컬럼을 사용해 목록 생성
        mentor_list = mentor_data['name'].tolist()
        selected_m = st.selectbox("멘토 선택", ["선택하세요"] + mentor_list)
        
        topic = st.text_area("상담 주제")
        
        if st.form_submit_button("🚀 신청하기"):
            if is_company_email(m_email) and selected_m != "선택하세요" and m_name:
                # 2. 기존과 동일한 예약 시트(예: reservations)에 저장
                ws_res = get_ws(DB_FILES["mentoring"], "reservations")
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 시트 컬럼 순서에 맞게 데이터를 밀어넣습니다.
                ws_res.append_row([now, m_name, m_email, selected_m, topic, "신청완료"])
                
                # 3. 메일 발송 (이것도 기존과 동일)
                m_info = mentor_data[mentor_data['name'] == selected_m].iloc[0]
                send_email_notification(m_info['email'], "mentoring", m_name, selected_m, "조율 예정", "시간 미정", topic, "추후 결정")
                
                st.success("신청이 완료되었습니다!")
                st.balloons()
            else:
                st.error("입력 정보를 확인해 주세요.")

    # 하단에 신청 현황 보여주기 (기존 기능)
    st.markdown("---")
    st.subheader("📋 최근 신청 현황")
    ws_res = get_ws(DB_FILES["mentoring"], "reservations")
    if ws_res:
        df = pd.DataFrame(ws_res.get_all_records())
        st.dataframe(df.tail(5), use_container_width=True)
