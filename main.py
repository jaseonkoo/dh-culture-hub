import streamlit as st
import os

# 쪼개진 개별 파일(모듈)들을 통째로 불러옵니다.
import mentoring
import leader
import oneday
import typing_game

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# ==========================================
# 🛡️ 방문자 수 계산 로직
# ==========================================
def get_client_ip():
    try:
        ip = st.context.headers.get("X-Forwarded-For", "")
        if ip: return ip.split(",")[0].strip()
        return "Unknown"
    except: return "Unknown"

def update_visitor_count():
    ip_file = "visited_ips.txt" 
    current_ip = get_client_ip()
    if os.path.exists(ip_file):
        with open(ip_file, "r") as f: visited_ips = set(f.read().splitlines())
    else: visited_ips = set()
        
    if current_ip != "Unknown" and current_ip not in visited_ips:
        visited_ips.add(current_ip)
        with open(ip_file, "w") as f: f.write("\n".join(visited_ips))
    return len(visited_ips)

total_visitors = update_visitor_count()

# ==========================================
# 📱 메인 화면 및 페이지 이동 로직
# ==========================================
if "page" not in st.session_state: st.session_state.page = "home"

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- [메인 화면] ---
if st.session_state.page == "home":
    st.title("🚀 조직문화 활성화 통합 플랫폼")
    st.markdown("---")
    
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)
    
    with row1_col1:
        st.markdown("### 🤝 동반성장 멘토링")
        if st.button("입장하기", key="btn_mentoring", use_container_width=True): go_to("mentoring")

    with row1_col2:
        st.markdown("### ☕ 성장지원 1:1 코칭")
        if st.button("입장하기", key="btn_leader", use_container_width=True): go_to("leader")

    with row2_col1:
        st.markdown("### 🎓 직무 원데이 클래스")
        if st.button("입장하기", key="btn_class", use_container_width=True): go_to("class")
            
    with row2_col2:
        st.markdown("### 🎯 핵심가치 타자연습")
        if st.button("입장하기", key="btn_typing", use_container_width=True): go_to("typing")

    st.markdown("---")
    st.markdown(f"<span style='color: gray; font-size: 0.9em;'>📊 현재 누적 방문자 수: {total_visitors}명</span>", unsafe_allow_html=True)

# --- [각 프로그램 페이지 연결] ---
elif st.session_state.page == "mentoring":
    if st.button("⬅️ 메인으로"): go_to("home")
    mentoring.run_mentoring() 

elif st.session_state.page == "leader":
    if st.button("⬅️ 메인으로"): go_to("home")
    leader.run_leader_talk()

elif st.session_state.page == "class":
    if st.button("⬅️ 메인으로"): go_to("home")
    oneday.run_class()

elif st.session_state.page == "typing":
    if st.button("⬅️ 메인으로"): go_to("home")
    typing_game.run_typing_game()
