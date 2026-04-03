import streamlit as st
# [연결] 아까 만든 엔진 파일에서 필요한 기능들만 가져옵니다.
from core_logic import handle_visitor_stats, WEEKS

# 1. 페이지 기본 설정 (대한사료 전용 브랜딩)
st.set_page_config(page_title="대한사료 조직문화 Hub", page_icon="🏢", layout="wide")

# 2. 세션 상태 초기화 (어떤 페이지를 보여줄지 결정)
if "page" not in st.session_state:
    st.session_state.page = "home"

# 3. 방문자 통계 처리 (엔진 호출)
handle_visitor_stats()

# 4. 상단 헤더 및 디자인 (차장님의 요청대로 세련되게!)
st.title("🚀 대한사료 조직문화 활성화 플랫폼")
st.caption("임직원의 성장과 소통을 돕는 통합 디지털 창구입니다.")
st.markdown("---")

# 5. 페이지 이동 함수 (버튼 클릭 시 호출)
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 🏠 [메인 화면] 아이콘 버튼 3개 배치
# ==========================================
if st.session_state.page == "home":
    st.subheader("원하시는 프로그램을 선택해 주세요.")
    st.write("") # 간격 조절

    # 3개 컬럼으로 아이콘 배치
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🤝 사내 멘토링")
        st.write("선후배 간의 지식 공유와 조직 적응을 돕는 매칭 프로그램")
        if st.button("입장하기", key="btn_mentoring", use_container_width=True):
            go_to("mentoring")

    with col2:
        st.markdown("### ☕ 리더와의 대화")
        st.write("경영진/팀장님과 가벼운 커피 한 잔하며 나누는 소통의 시간")
        if st.button("입장하기", key="btn_leader", use_container_width=True):
            go_to("leader")

    with col3:
        st.markdown("### 🎓 직무 원데이 클래스")
        st.write("부서별 전문 지식을 실시간으로 공유하고 학습하는 교육 창구")
        if st.button("입장하기", key="btn_class", use_container_width=True):
            go_to("class")

    st.markdown("---")
    # 관리자 전용 메뉴 이동 버튼 (구석에 작게 배치)
    col_a, col_b = st.columns([8, 2])
    with col_b:
        if st.button("👑 시스템 관리자 로그인", use_container_width=True):
            go_to("admin")
    
    st.caption(f"📊 현재 누적 방문자 수: {st.session_state.get('visitor_count', 0)}명")

# ==========================================
# 🔄 [각 프로그램 화면 연결] 
# (이 부분은 나중에 programs.py와 연결될 핵심 부위입니다!)
# ==========================================
elif st.session_state.page == "mentoring":
    if st.button("⬅️ 메인으로 돌아가기"): go_to("home")
    st.header("🤝 사내 멘토링 프로그램")
    st.info("준비 중입니다. 곧 기존 멘토링 기능을 이식할 예정입니다.")

elif st.session_state.page == "leader":
    if st.button("⬅️ 메인으로 돌아가기"): go_to("home")
    st.header("☕ 리더와의 대화 (Coffee Chat)")
    st.info("준비 중입니다. 리더분들의 일정을 곧 공개합니다.")

elif st.session_state.page == "class":
    if st.button("⬅️ 메인으로 돌아가기"): go_to("home")
    st.header("🎓 직무 원데이 클래스")
    st.info("준비 중입니다. 함께 배우고 성장할 강의를 신청해 보세요.")

elif st.session_state.page == "admin":
    if st.button("⬅️ 메인으로 돌아가기"): go_to("home")
    st.header("👑 통합 시스템 관리")
    st.info("인사총무팀 전용 관리 페이지입니다.")
