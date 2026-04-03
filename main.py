import streamlit as st
import os
import programs

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# ==========================================
# 🛡️ 방문자 수 계산 로직 (중복 IP 방지)
# ==========================================
def get_client_ip():
    try:
        ip = st.context.headers.get("X-Forwarded-For", "")
        if ip:
            return ip.split(",")[0].strip()
        return "Unknown"
    except:
        return "Unknown"

def update_visitor_count():
    ip_file = "visited_ips.txt" 
    current_ip = get_client_ip()
    
    if os.path.exists(ip_file):
        with open(ip_file, "r") as f:
            visited_ips = set(f.read().splitlines())
    else:
        visited_ips = set()
        
    if current_ip != "Unknown" and current_ip not in visited_ips:
        visited_ips.add(current_ip)
        with open(ip_file, "w") as f:
            f.write("\n".join(visited_ips))
            
    return len(visited_ips)

# 중복이 제외된 누적 방문자 수 계산
total_visitors = update_visitor_count()

# ==========================================
# 📱 메인 화면 및 페이지 이동 로직
# ==========================================
# 세션 상태 초기화
if "page" not in st.session_state:
    st.session_state.page = "home"

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
    # ✨ 차장님이 요청하신 하단 방문자 수 디자인 (중복 제외된 숫자 반영)
    st.markdown(f"<span style='color: gray; font-size: 0.9em;'>📊 현재 누적 방문자 수: {total_visitors}명</span>", unsafe_allow_html=True)

# --- [각 프로그램 페이지 연결] ---
elif st.session_state.page == "mentoring":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_mentoring()

elif st.session_state.page == "leader":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_leader_talk()

elif st.session_state.page == "class":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_class()
