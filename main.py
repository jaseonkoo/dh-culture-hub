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
# 📊 구글 시트 일별/페이지별 실시간 통계 로직
# ==========================================
def log_page_visit(page_name):
    # 동일한 세션 내에서 같은 날짜에 중복 카운트되는 것을 방지합니다.
    today_str = str(datetime.date.today())
    session_key = f"logged_{page_name}_{today_str}"
    if st.session_state.get(session_key, False):
        return

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        
        # '대한사료_통합통계_DB' 구글 시트를 안전하게 엽니다.
        doc = client.open("대한사료_통합통계_DB")
        
        # '접속통계' 탭이 없으면 자동으로 생성해 줍니다.
        try:
            ws = doc.worksheet("접속통계")
        except gspread.exceptions.WorksheetNotFound:
            ws = doc.add_worksheet("접속통계", 1000, 10)
            ws.append_row(["날짜", "메인", "멘토링", "리더대화", "원데이클래스", "타자연습"])
            
        records = ws.get_all_records()
        
        # 페이지별 열 위치 매핑
        col_map = {
            "home": 2,
            "mentoring": 3,
            "leader": 4,
            "class": 5,
            "typing": 6
        }
        col_idx = col_map.get(page_name)
        if not col_idx: return

        row_idx = None
        for i, rec in enumerate(records):
            if str(rec.get("날짜")) == today_str:
                row_idx = i + 2  # 헤더행을 고려하여 실제 행 번호 계산
                break
                
        if row_idx:
            # 오늘 날짜의 행이 이미 기록되어 있다면 카운트만 +1 업데이트
            current_val = ws.cell(row_idx, col_idx).value
            new_val = int(current_val) + 1 if current_val else 1
            ws.update_cell(row_idx, col_idx, new_val)
        else:
            # 오늘 첫 접속 날짜라면 새 행을 추가하고 해당 페이지 칸만 1로 시작
            new_row = [today_str, 0, 0, 0, 0, 0]
            new_row[col_idx - 1] = 1
            ws.append_row(new_row)
            
        # 성공적으로 기록 완료 시 세션 상태에 플래그 설정하여 중복 카운트 방지
        st.session_state[session_key] = True
    except:
        # 시트 통계 연동에 일시적 지연이나 에러가 나더라도 메인 기능이 멈추지 않도록 안전망 구성
        pass

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
        with open(ip_file, "r") as f: 
            visited_ips = set(f.read().splitlines())
    else: 
        visited_ips = set()
        
    if current_ip != "Unknown" and current_ip not in visited_ips:
        visited_ips.add(current_ip)
        with open(ip_file, "w") as f: 
            f.write("\n".join(visited_ips))
            
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
    log_page_visit("home")  # 📊 메인페이지 카운트 체크
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
    log_page_visit("mentoring")  # 📊 멘토링 페이지 카운트 체크
    if st.button("⬅️ 메인으로"): go_to("home")
    mentoring.run_mentoring() 

elif st.session_state.page == "leader":
    log_page_visit("leader")  # 📊 리더대화 페이지 카운트 체크
    if st.button("⬅️ 메인으로"): go_to("home")
    leader.run_leader_talk()

elif st.session_state.page == "class":
    log_page_visit("class")  # 📊 원데이클래스 페이지 카운트 체크
    if st.button("⬅️ 메인으로"): go_to("home")
    oneday.run_class()

elif st.session_state.page == "typing":
    log_page_visit("typing")  # 📊 타자연습 페이지 카운트 체크
    if st.button("⬅️ 메인으로"): go_to("home")
    typing_game.run_typing_game()
