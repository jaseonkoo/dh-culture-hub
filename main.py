import streamlit as st
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 쪼개진 개별 파일(모듈)들을 불러옵니다.
import mentoring
import leader
import oneday
import typing_game

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# ==========================================
# 📊 구글 시트 기반: 누적 방문자 수 가져오기
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def get_total_visitors():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        doc = client.open("대한사료_통합통계_DB")
        ws = doc.worksheet("접속통계")
        records = ws.get_all_records()
        
        # '메인' 열에 기록된 모든 일자의 접속자 수를 합산합니다.
        total = sum(int(r.get("메인", 0)) for r in records if str(r.get("메인", 0)).isdigit())
        return total
    except:
        return 0

# ==========================================
# 📊 구글 시트 일별/페이지별 실시간 통계 기록 로직
# ==========================================
def log_page_visit(page_name):
    # 한 세션 내에서 동일 페이지의 중복 카운트를 방지합니다.
    today_str = str(datetime.date.today())
    session_key = f"logged_{page_name}_{today_str}"
    if st.session_state.get(session_key, False):
        return

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        doc = client.open("대한사료_통합통계_DB")
        
        try:
            ws = doc.worksheet("접속통계")
        except gspread.exceptions.WorksheetNotFound:
            ws = doc.add_worksheet("접속통계", 1000, 10)
            ws.append_row(["날짜", "메인", "멘토링", "리더대화", "원데이클래스", "타자연습"])
            
        records = ws.get_all_records()
        col_map = {"home": 2, "mentoring": 3, "leader": 4, "class": 5, "typing": 6}
        col_idx = col_map.get(page_name)
        if not col_idx: return

        row_idx = None
        for i, rec in enumerate(records):
            if str(rec.get("날짜")) == today_str:
                row_idx = i + 2
                break
                
        if row_idx:
            current_val = ws.cell(row_idx, col_idx).value
            new_val = int(current_val) + 1 if current_val else 1
            ws.update_cell(row_idx, col_idx, new_val)
        else:
            new_row = [today_str, 0, 0, 0, 0, 0]
            new_row[col_idx - 1] = 1
            ws.append_row(new_row)
            
        # 성공적으로 기록 시 세션에 저장하여 새로고침 도배 방지
        st.session_state[session_key] = True
        
        # 메인 페이지 접속 시 방문자 수를 즉시 갱신하도록 캐시 클리어
        if page_name == "home":
            get_total_visitors.clear()
            
    except:
        pass

# ==========================================
# 📱 메인 화면 및 페이지 이동 로직
# ==========================================
if "page" not in st.session_state: st.session_state.page = "home"

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- [메인 화면] ---
if st.session_state.page == "home":
    log_page_visit("home")  # 📊 카운트 즉시 체크
    total_visitors = get_total_visitors() # 📊 구글 시트에서 누적 방문자 호출
    
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

# --- [각 프로그램 페이지 연결 및 통계 체크] ---
elif st.session_state.page == "mentoring":
    log_page_visit("mentoring")
    if st.button("⬅️ 메인으로"): go_to("home")
    mentoring.run_mentoring() 

elif st.session_state.page == "leader":
    log_page_visit("leader")
    if st.button("⬅️ 메인으로"): go_to("home")
    leader.run_leader_talk()

elif st.session_state.page == "class":
    log_page_visit("class")
    if st.button("⬅️ 메인으로"): go_to("home")
    oneday.run_class()

elif st.session_state.page == "typing":
    log_page_visit("typing")
    if st.button("⬅️ 메인으로"): go_to("home")
    typing_game.run_typing_game()
