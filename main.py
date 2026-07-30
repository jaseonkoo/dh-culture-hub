import streamlit as st
import os
import datetime
import uuid
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 쪼개진 개별 파일(모듈)들을 불러옵니다.
import mentoring
import leader
import oneday
import typing_game
import tycoon_game
import library

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")


# ==========================================
# 🛡️ 세션(접속) 고유 식별자 생성 (새로고침 도배 방어용)
# ==========================================
def get_client_identifier():
    # 스트림릿의 URL에 'uid'라는 꼬리표가 있는지 확인합니다. (새로고침해도 유지됨!)
    if "uid" in st.query_params:
        return st.query_params["uid"]
    else:
        # 없다면 새로운 접속(세션)이므로 고유 번호를 발급해 URL에 붙여줍니다.
        new_uid = str(uuid.uuid4())[:8]
        st.query_params["uid"] = new_uid
        return new_uid


# 서버가 꺼지기 전까지 절대 지워지지 않는 강력한 출석부입니다.
@st.cache_resource
def get_visited_registry():
    return {}


# ==========================================
# 📊 구글 시트 기반: 누적 접속 횟수 가져오기
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

        # '메인' 열에 기록된 모든 일자의 접속 횟수를 합산합니다.
        total = sum(int(r.get("메인", 0)) for r in records if str(r.get("메인", 0)).isdigit())
        return total
    except:
        return 0


# ==========================================
# 📊 구글 시트 일별/페이지별 실시간 통계 기록 로직
# ==========================================
# ✅ [수정] 통계 시트의 열 이름을 한 곳에 모아 두었습니다.
#          아래 col_map 의 순서와 반드시 같아야 합니다.
STAT_HEADERS = ["날짜", "메인", "멘토링", "리더대화", "원데이클래스", "타자연습", "타이쿤", "도서관"]


def log_page_visit(page_name):
    today_str = str(datetime.date.today())
    client_id = get_client_identifier()
    registry = get_visited_registry()

    # 자정이 지나면 어제 출석부는 메모리에서 지워줍니다.
    for date_key in list(registry.keys()):
        if date_key != today_str:
            del registry[date_key]

    if today_str not in registry:
        registry[today_str] = {}
    if page_name not in registry[today_str]:
        registry[today_str][page_name] = set()

    # 💡 철벽 방어 1단계: 오늘 이 페이지 출석부에 내 지문이 있으면 곧바로 패스!
    if client_id in registry[today_str][page_name]:
        return

    # 🚀 철벽 방어 2단계: 구글 시트 통신(느림) 전에 무조건 출석부에 이름부터 올립니다! (F5 연타 차단)
    registry[today_str][page_name].add(client_id)

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
            ws.append_row(STAT_HEADERS)

        # ✅ [수정] 예전에 만든 시트에는 '타이쿤', '도서관' 열이 없습니다.
        #          없으면 맨 오른쪽에 자동으로 만들어 줍니다. (기존 값은 그대로)
        try:
            hdr = ws.row_values(1)
            if len(hdr) < len(STAT_HEADERS):
                for i in range(len(hdr), len(STAT_HEADERS)):
                    ws.update_cell(1, i + 1, STAT_HEADERS[i])
        except:
            pass

        records = ws.get_all_records()
        col_map = {"home": 2, "mentoring": 3, "leader": 4, "class": 5, "typing": 6, "tycoon": 7, "library": 8}
        col_idx = col_map.get(page_name)
        if not col_idx:
            return

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
            # ✅ [수정] 예전에는 칸이 6개뿐이라 타이쿤·도서관 기록이 저장되지 않았습니다.
            new_row = [today_str] + [0] * (len(STAT_HEADERS) - 1)
            new_row[col_idx - 1] = 1
            ws.append_row(new_row)

        if page_name == "home":
            get_total_visitors.clear()

    except:
        pass


# ==========================================
# 📱 메인 화면 및 페이지 이동 로직
# ==========================================
if "page" not in st.session_state:
    st.session_state.page = "home"


def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()


# --- [메인 화면] ---
if st.session_state.page == "home":
    log_page_visit("home")
    total_visitors = get_total_visitors()

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

    row3_col1, row3_col2 = st.columns(2)

    with row3_col1:
        st.markdown("### 🌾 밸류체인 타이쿤 (Beta)")
        st.caption("현재 테스트 중입니다. 비밀번호를 입력하고 **엔터**를 누르세요.")

        # ✅ [수정] st.form 상자 안에 넣으면 '엔터'만 쳐도 입장합니다.
        with st.form("tycoon_gate", clear_on_submit=False):
            c_pw, c_btn = st.columns([2, 1])
            test_pw = c_pw.text_input("비밀번호", type="password", key="tycoon_pw",
                                      label_visibility="collapsed", placeholder="비밀번호 입력")
            go_tycoon = c_btn.form_submit_button("입장하기", use_container_width=True)

        # 판정은 폼 밖에서 합니다. (폼 안에서는 화면 이동을 하면 안 됩니다)
        if go_tycoon:
            if test_pw == "dhfeedhr":  # 👈 여기에 원하시는 테스트용 비밀번호를 적어주세요.
                go_to("tycoon")
            elif test_pw == "":
                st.warning("비밀번호를 입력해 주세요.")
            else:
                st.error("비밀번호가 일치하지 않습니다.")

    with row3_col2:
        st.markdown("### 📚 사내 도서관")
        st.caption("비밀번호를 입력하고 **엔터**를 누르세요.")

        # ✅ [수정] st.form 상자 안에 넣으면 '엔터'만 쳐도 입장합니다.
        with st.form("library_gate", clear_on_submit=False):
            l_pw, l_btn = st.columns([2, 1])
            lib_pw = l_pw.text_input("비밀번호", type="password", key="library_pw",
                                     label_visibility="collapsed", placeholder="비밀번호 입력")
            go_library = l_btn.form_submit_button("입장하기", use_container_width=True)

        if go_library:
            if lib_pw == "dhfeedhr":  # 👈 타이쿤과 동일한 비밀번호 (원하면 여기만 바꾸면 됩니다)
                go_to("library")
            elif lib_pw == "":
                st.warning("비밀번호를 입력해 주세요.")
            else:
                st.error("비밀번호가 일치하지 않습니다.")

    # -----------------------------------------------------------------------------------
    # ✅ [수정] 이 구분선이 오른쪽 칸(도서관) 안에 들어가 있었습니다. 밖으로 빼냈습니다.
    st.markdown("---")

    # ✨ 명칭을 '누적 접속 횟수'로 변경하고, 단위도 '명'에서 '회'로 변경했습니다.
    st.markdown(f"<span style='color: gray; font-size: 0.9em;'>📊 현재 누적 접속 횟수: {total_visitors}회</span>", unsafe_allow_html=True)

# --- [각 프로그램 페이지 연결 및 통계 체크] ---
elif st.session_state.page == "mentoring":
    log_page_visit("mentoring")
    if st.button("⬅️ 플랫폼 메인으로 나가기"): go_to("home")
    mentoring.run_mentoring()

elif st.session_state.page == "leader":
    log_page_visit("leader")
    if st.button("⬅️ 플랫폼 메인으로 나가기"): go_to("home")
    leader.run_leader_talk()

elif st.session_state.page == "class":
    log_page_visit("class")
    if st.button("⬅️ 플랫폼 메인으로 나가기"): go_to("home")
    oneday.run_class()

elif st.session_state.page == "typing":
    log_page_visit("typing")
    if st.button("⬅️ 플랫폼 메인으로 나가기"): go_to("home")
    typing_game.run_typing_game()

elif st.session_state.page == "tycoon":
    log_page_visit("tycoon")
    if st.button("⬅️ 플랫폼 메인으로 나가기"): go_to("home")
    tycoon_game.run_tycoon_game()

elif st.session_state.page == "library":
    log_page_visit("library")
    # ✅ [수정] 도서관 안에도 '돌아가기' 버튼이 있어서 헷갈렸습니다.
    #          이 버튼은 '플랫폼 메인으로 나가는' 버튼이라고 분명히 적어 둡니다.
    if st.button("⬅️ 플랫폼 메인으로 나가기", key="btn_out_library"): go_to("home")
    library.run_library()
