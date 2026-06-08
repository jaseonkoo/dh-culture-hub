import streamlit as st
import os
import programs

# 쪼개진 개별 파일(모듈)들을 통째로 불러옵니다.
import mentoring
import leader
import oneday
import typing_game

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# ==========================================
# 🛡️ 방문자 수 계산 로직 (중복 IP 방지)
# 🛡️ 방문자 수 계산 로직
# ==========================================
def get_client_ip():
    try:
        ip = st.context.headers.get("X-Forwarded-For", "")
        if ip:
            return ip.split(",")[0].strip()
        return "Unknown"
    except:
        if ip: return ip.split(",")[0].strip()
        return "Unknown"
    except: return "Unknown"

def update_visitor_count():
    ip_file = "visited_ips.txt" 
    current_ip = get_client_ip()
    
    if os.path.exists(ip_file):
        with open(ip_file, "r") as f:
            visited_ips = set(f.read().splitlines())
    else:
        visited_ips = set()
        with open(ip_file, "r") as f: visited_ips = set(f.read().splitlines())
    else: visited_ips = set()

    if current_ip != "Unknown" and current_ip not in visited_ips:
        visited_ips.add(current_ip)
        with open(ip_file, "w") as f:
            f.write("\n".join(visited_ips))
            
        with open(ip_file, "w") as f: f.write("\n".join(visited_ips))
    return len(visited_ips)

# 중복이 제외된 누적 방문자 수 계산
total_visitors = update_visitor_count()

# ==========================================
# 📱 메인 화면 및 페이지 이동 로직
# ==========================================
# 세션 상태 초기화
if "page" not in st.session_state:
    st.session_state.page = "home"
if "page" not in st.session_state: st.session_state.page = "home"

# 페이지 이동 함수
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
@@ -54,49 +48,41 @@ def go_to(page_name):
    st.title("🚀 조직문화 활성화 통합 플랫폼")
    st.markdown("---")

    # 📱 모바일 화면에서도 버튼이 넓고 깔끔하게 보이도록 2열 구조로 변경했습니다.
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)

    with row1_col1:
        st.markdown("### 🤝 동반성장 멘토링")
        if st.button("입장하기", key="btn_mentoring", use_container_width=True):
            go_to("mentoring")
        if st.button("입장하기", key="btn_mentoring", use_container_width=True): go_to("mentoring")

    with row1_col2:
        st.markdown("### ☕ 성장지원 1:1 코칭")
        if st.button("입장하기", key="btn_leader", use_container_width=True):
            go_to("leader")
        if st.button("입장하기", key="btn_leader", use_container_width=True): go_to("leader")

    with row2_col1:
        st.markdown("### 🎓 직무 원데이 클래스")
        if st.button("입장하기", key="btn_class", use_container_width=True):
            go_to("class")
        if st.button("입장하기", key="btn_class", use_container_width=True): go_to("class")

    # ✨ 4번째 빈칸에 핵심가치 게임을 새롭게 연결했습니다.
    with row2_col2:
        st.markdown("### 🎯 핵심가치 타자연습")
        if st.button("입장하기", key="btn_typing", use_container_width=True):
            go_to("typing")
        if st.button("입장하기", key="btn_typing", use_container_width=True): go_to("typing")

    st.markdown("---")
    # ✨ 방문자 수 디자인 (중복 제외된 숫자 반영)
    st.markdown(f"<span style='color: gray; font-size: 0.9em;'>📊 현재 누적 방문자 수: {total_visitors}명</span>", unsafe_allow_html=True)

# --- [각 프로그램 페이지 연결] ---
elif st.session_state.page == "mentoring":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_mentoring()
    mentoring.run_mentoring() 

elif st.session_state.page == "leader":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_leader_talk()
    leader.run_leader_talk()

elif st.session_state.page == "class":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_class()
    oneday.run_class()

# ✨ 메인에서 보내준 신호(typing)를 받아 게임 함수를 실행하는 통로입니다.
elif st.session_state.page == "typing":
    if st.button("⬅️ 메인으로"): go_to("home")
    programs.run_typing_game()
    typing_game.run_typing_game()
