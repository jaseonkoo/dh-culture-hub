import streamlit as st
# 엔진과 프로그램 공장에서 필요한 기능들을 불러옵니다.
from core_logic import handle_visitor_stats
import programs

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# 세션 상태 초기화
if "page" not in st.session_state:
    st.session_state.page = "home"

# 방문자 통계 처리
handle_visitor_stats()

# 페이지 이동 함수
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- [메인 화면] ---
if st.session_state.page == "home":
    st.title("🚀 조직문화 활성화 통합 플랫폼")
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🤝 사내 멘토링")
        if st.button("입장하기", key="btn_mentoring", use_container_width=True):
            go_to("mentoring")

    with col2:
        st.markdown("### ☕ 리더와의 대화")
        if st.button("입장하기", key="btn_leader", use_container_width=True):
            go_to("leader")

    with col3:
        st.markdown("### 🎓 직무 원데이 클래스")
        if st.button("입장하기", key="btn_class", use_container_width=True):
            go_to("class")

    st.markdown("---")
    st.caption(f"📊 현재 누적 방문자 수: {st.session_state.get('visitor_count', 0)}명")

# --- [각 프로그램 페이지 연결] ---
elif st.session_state.page == "mentoring":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_mentoring() # programs.py의 멘토링 함수 실행

elif st.session_state.page == "leader":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_leader_talk() # programs.py의 리더대화 함수 실행

elif st.session_state.page == "class":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_class() # programs.py의 원데이클래스 함수 실행
