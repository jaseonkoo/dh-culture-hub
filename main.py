import streamlit as st
import os
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
# 🛡️ 브라우저 고유 식별자 생성 (새로고침 방어용)
# ==========================================
def get_client_identifier():
    try:
        # IP와 접속 환경(User-Agent)을 조합하여 사용자만의 고유한 지문을 만듭니다.
        headers = st.context.headers
        ip = headers.get("X-Forwarded-For", "").split(",")[0].strip()
        ua = headers.get("User-Agent", "").strip()
        if not ip: ip = "UnknownIP"
        return f"{ip}_{ua}"
    except:
        return "UnknownClient"

# 전역(Global) 메모리: 새로고침을 해도 날아가지 않는 강력한 장바구니입니다.
@st.cache_resource
def get_visited_registry():
    return {} # 형태: {'2026-06-15': {'home': {'ip_ua_1', 'ip_ua_2'}, ...}}

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
    today_str = str(datetime.date.today())
    client_id = get_client_identifier()
    registry = get_visited_registry()
    
    # 자정이 지나면 어제 방문자 기록은 메모리에서 비워줍니다.
    for date_key in list(registry.keys()):
        if date_key != today_str:
            del registry[date_key]
            
    # 오늘 날짜 및 페이지 딕셔너리 구조 만들기
    if today_str not in registry:
        registry[today_str] = {}
    if page_name not in registry[today_str]:
        registry[today_str][page_name] = set()
        
    # 💡 핵심 방어막: 오늘 이미 이 페이지를 방문한 지문이라면 시트 연동을 즉시 멈춥니다!
    if client_id in registry[today_str][page_name]:
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
            
        # ✅ 구글 시트에 +1 기록이 완료되면 서버 메모리에 지문을 등록합니다. (도배 완벽 차단)
        registry[today_str][page_name].add(client_id)
        
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
