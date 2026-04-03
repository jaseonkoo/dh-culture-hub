import streamlit as st
# 엔진과 프로그램 공장에서 필요한 기능들을 불러옵니다.
from core_logic import handle_visitor_stats
import programs

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")
import streamlit as st
import os

# 1. 방문자의 IP(출입증 번호)를 확인하는 함수
def get_client_ip():
    try:
        # 스트림릿 클라우드 환경에서 방문자의 실제 IP를 가져옵니다.
        ip = st.context.headers.get("X-Forwarded-For", "")
        if ip:
            return ip.split(",")[0].strip()
        return "Unknown"
    except:
        return "Unknown"

# 2. 중복을 검사하고 방문자 수를 계산하는 함수
def update_visitor_count():
    ip_file = "visited_ips.txt" # 방문한 IP들을 적어둘 메모장 파일
    
    # 지금 접속한 사람의 IP 가져오기
    current_ip = get_client_ip()
    
    # 기존 메모장(visited_ips.txt)이 있으면 읽어오고, 없으면 새로 만들기
    if os.path.exists(ip_file):
        with open(ip_file, "r") as f:
            # set()을 사용하면 중복을 자동으로 걸러줍니다.
            visited_ips = set(f.read().splitlines())
    else:
        visited_ips = set()
        
    # 새로운 IP(처음 온 사람)라면? 메모장에 적고 저장!
    if current_ip != "Unknown" and current_ip not in visited_ips:
        visited_ips.add(current_ip)
        with open(ip_file, "w") as f:
            f.write("\n".join(visited_ips))
            
    # 메모장에 적힌 IP의 총 개수가 곧 '누적 방문자 수'가 됩니다.
    return len(visited_ips)

# ---------------------------------------------------------
# ✨ 실제 화면에 방문자 수 띄우기 (차장님이 원하시는 위치에 넣으세요)
total_visitors = update_visitor_count()

# 예쁘게 보여주기 (예시)
st.metric(label="현재 누적 방문자 수 (중복 제외)", value=f"{total_visitors} 명")



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
