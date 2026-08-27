import streamlit as st
import datetime
import uuid
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 페이지 기본 설정
st.set_page_config(page_title="조직문화 활성화 Hub", page_icon="🏢", layout="wide")

# ==========================================
# ⚡ [속도 개선] 프로그램은 '누른 것만' 불러옵니다.
#   예전에는 6개 프로그램을 전부 미리 불러와서 첫 화면이 느렸습니다.
#   이제는 실제로 들어갈 때 그 프로그램 하나만 불러옵니다.
# ==========================================
def load_module(name):
    import importlib
    return importlib.import_module(name)


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
# ⚡ [속도 개선] 구글 시트 접속을 '한 번만' 합니다.
#   예전에는 화면을 열 때마다 구글에 새로 로그인했습니다. (한 번에 1~2초)
#   이제는 서버가 켜져 있는 동안 한 번만 로그인하고 그대로 다시 씁니다.
# ==========================================
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file",
         "https://www.googleapis.com/auth/drive"]

STAT_DB = "대한사료_통합통계_DB"
STAT_TAB = "접속통계"
STAT_HEADERS = ["날짜", "메인", "멘토링", "리더대화", "원데이클래스", "타자연습", "타이쿤", "도서관"]
COL_MAP = {"home": 2, "mentoring": 3, "leader": 4, "class": 5,
           "typing": 6, "tycoon": 7, "library": 8}


@st.cache_resource(show_spinner=False)
def get_gs_client():
    """구글 로그인은 서버당 한 번만."""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], SCOPE)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_stat_ws():
    """접속통계 탭 손잡이. 열 이름 점검도 여기서 딱 한 번만 합니다."""
    client = get_gs_client()
    doc = client.open(STAT_DB)
    try:
        ws = doc.worksheet(STAT_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = doc.add_worksheet(STAT_TAB, 1000, 10)
        ws.append_row(STAT_HEADERS)
        return ws
    # 예전 시트에는 '타이쿤', '도서관' 열이 없습니다. 없으면 만들어 줍니다.
    try:
        hdr = ws.row_values(1)
        if len(hdr) < len(STAT_HEADERS):
            for i in range(len(hdr), len(STAT_HEADERS)):
                ws.update_cell(1, i + 1, STAT_HEADERS[i])
    except Exception:
        pass
    return ws


@st.cache_data(ttl=1800, show_spinner=False)
def get_today_row(today_str):
    """오늘 날짜가 시트 몇 번째 줄인지. (없으면 0)
       ⚡ 예전에는 시트를 통째로 읽었는데, 이제 '날짜 열' 하나만 읽습니다."""
    try:
        dates = get_stat_ws().col_values(1)
    except Exception:
        return 0
    for i, d in enumerate(dates):
        if str(d).strip() == today_str:
            return i + 1          # 시트 줄 번호 (1부터)
    return 0


# ==========================================
# 📊 누적 접속 횟수
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def get_total_visitors():
    """⚡ 시트를 통째로 읽지 않고 '메인' 열 하나만 읽어서 더합니다."""
    try:
        col = get_stat_ws().col_values(COL_MAP["home"])
        total = 0
        for v in col[1:]:                     # 첫 줄은 열 이름
            s = str(v).strip().replace(",", "")
            if s.isdigit():
                total += int(s)
        return total
    except Exception:
        try:
            get_stat_ws.clear()
            get_gs_client.clear()
        except Exception:
            pass
        return 0


def log_page_visit(page_name):
    """오늘 이 사람이 이 화면을 처음 열었을 때만 1을 더합니다.
       ⚡ 구글 호출을 6번 → 2번으로 줄였습니다."""
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

    # 💡 오늘 이 페이지 출석부에 내 지문이 있으면 곧바로 패스! (구글 접속 안 함)
    if client_id in registry[today_str][page_name]:
        return

    # 🚀 구글 시트 통신(느림) 전에 무조건 출석부에 이름부터 올립니다. (F5 연타 차단)
    registry[today_str][page_name].add(client_id)

    col_idx = COL_MAP.get(page_name)
    if not col_idx:
        return

    try:
        ws = get_stat_ws()
        row_idx = get_today_row(today_str)

        if row_idx:
            current_val = ws.cell(row_idx, col_idx).value
            new_val = int(current_val) + 1 if str(current_val or "").strip().isdigit() else 1
            ws.update_cell(row_idx, col_idx, new_val)
        else:
            new_row = [today_str] + [0] * (len(STAT_HEADERS) - 1)
            new_row[col_idx - 1] = 1
            ws.append_row(new_row)
            get_today_row.clear()      # 새 줄이 생겼으니 줄 번호를 다시 찾게 합니다.

        if page_name == "home":
            get_total_visitors.clear()
    except Exception:
        # 구글 연결이 오래되어 끊겼을 수 있으니, 다음 번에 새로 연결하도록 비웁니다.
        try:
            get_stat_ws.clear()
            get_gs_client.clear()
            get_today_row.clear()
        except Exception:
            pass


# ==========================================
# 📱 페이지 이동 로직
# ==========================================
if "page" not in st.session_state:
    st.session_state.page = "home"


def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()


# ==========================================
# 🎨 공통 꾸미기
#   ⚡ [잔상 개선] 화면이 바뀌는 동안 옛 화면이 흐리게 남아 보이던 문제를
#      없애고, 배경색을 맨 처음부터 정해 둡니다.
# ==========================================
BASE_CSS = """
<style>
/* 화면을 다시 그리는 동안 옛 내용이 흐릿하게 겹쳐 보이지 않게 합니다. */
[data-stale="true"], .stale-element,
[data-testid="stAppViewContainer"] [data-stale="true"] {
  opacity: 1 !important; filter: none !important; transition: none !important;
}
/* 화면 전환 때 깜빡임을 줄입니다. */
[data-testid="stAppViewContainer"] { transition: none !important; }
</style>
"""

PLATFORM_CSS = """
<style>
/* ----- 바탕과 글꼴 ----- */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
.stApp { background:#F4F5F7; }
html, body, .stApp, [data-testid="stAppViewContainer"] {
  font-family:'Noto Sans KR','Malgun Gothic','맑은 고딕',sans-serif; }

/* ----- 머리말 ----- */
.pf-hero h1 { margin:0; font-size:1.9rem; font-weight:900; letter-spacing:-.02em; color:#1B1F24; }
.pf-hero p  { margin:10px 0 0; color:#5B6472; font-size:.98rem; }
.pf-hero .bar { height:4px; width:60px; margin:18px 0 6px; border-radius:99px;
  background:linear-gradient(90deg,#1F7A5A,#2F6FB5,#C8892A); }

/* ----- 묶음 제목 (Community / Learning / Gamification) ----- */
.pf-ghead { display:flex; align-items:center; gap:11px; margin:30px 0 12px; }
.pf-chip { font-size:.7rem; font-weight:700; letter-spacing:.16em; text-transform:uppercase;
  padding:5px 11px; border-radius:99px; white-space:nowrap; }
.pf-gko { font-size:.9rem; color:#6B7480; font-weight:500; white-space:nowrap; }
.pf-gline { flex:1; height:1px; background:#E1E4E9; }

/* ----- 카드 ----- */
.pf-card { position:relative; background:#fff; border:1px solid #E4E7EB; border-radius:14px;
  padding:22px 20px 16px; box-shadow:0 1px 2px rgba(16,24,40,.04);
  min-height:186px; margin-bottom:10px;
  transition:transform .15s ease, box-shadow .15s ease; }
.pf-card:hover { transform:translateY(-3px); box-shadow:0 12px 22px -12px rgba(16,24,40,.28); }
.pf-card::before { content:""; position:absolute; left:0; top:16px; bottom:16px; width:3px;
  border-radius:0 3px 3px 0; }
.pf-ico { width:44px; height:44px; border-radius:12px; display:flex; align-items:center;
  justify-content:center; font-size:1.35rem; margin-bottom:13px; }
.pf-tt { font-weight:700; font-size:1.06rem; letter-spacing:-.01em; color:#1B1F24; }
.pf-dd { margin-top:6px; color:#6B7480; font-size:.86rem; line-height:1.55; }
.pf-beta { margin-left:7px; font-size:.66rem; font-weight:700; color:#B0782A;
  background:#FAEFDC; padding:3px 7px; border-radius:99px; vertical-align:middle; }

/* ----- 묶음별 색 ----- */
.pf-a::before { background:#1F7A5A; } .pf-a .pf-ico { background:#E4F2EC; }
.pf-b::before { background:#2F6FB5; } .pf-b .pf-ico { background:#E6EEF8; }
.pf-c::before { background:#C8892A; } .pf-c .pf-ico { background:#FAEFDC; }
.pf-chip-a { background:#E4F2EC; color:#1F7A5A; }
.pf-chip-b { background:#E6EEF8; color:#2F6FB5; }
.pf-chip-c { background:#FAEFDC; color:#B0782A; }

/* ----- 카드 아래 [입장하기] 버튼 색 -----
   (이름표를 못 붙이는 옛 버전에서는 기본 버튼 모양으로 나옵니다) */
[class*="st-key-nav_a"] button, [class*="st-key-nav_b"] button,
[class*="st-key-nav_c"] button {
  color:#fff !important; font-weight:700 !important; border:0 !important;
  border-radius:9px !important; padding:10px !important; }
[class*="st-key-nav_a"] button { background:#1F7A5A !important; }
[class*="st-key-nav_b"] button { background:#2F6FB5 !important; }
[class*="st-key-nav_c"] button { background:#C8892A !important; }
[class*="st-key-nav_a"] button:hover { background:#19634A !important; }
[class*="st-key-nav_b"] button:hover { background:#265B95 !important; }
[class*="st-key-nav_c"] button:hover { background:#A87121 !important; }

/* ----- 바닥 ----- */
.pf-foot { margin-top:34px; padding-top:16px; border-top:1px solid #E1E4E9;
  color:#96A0AD; font-size:.84rem; }
</style>
"""

# 카드 내용 : (페이지이름, 아이콘, 제목, 한 줄 설명, 베타여부)
# 묶음 : (영문 이름, 우리말 설명, 색깔표시, 카드들)
PLATFORM_MENU = [
    ("Community", "함께 성장하기", "a", [
        ("mentoring", "🤝", "동반성장 멘토링", "선배와 후배가 짝을 이뤄 함께 성장합니다", False),
        ("leader", "☕", "성장지원 1:1 코칭", "리더와 구성원이 나누는 1:1 대화", False),
    ]),
    ("Learning", "배우고 나누기", "b", [
        ("class", "🎓", "직무 원데이 클래스", "동료의 직무 노하우를 배우는 사내 강의", False),
        ("library", "📚", "사내 도서관", "셀프로 직접 빌리고 반납하는 사내 도서관", False),
    ]),
    ("Gamification", "즐기며 익히기", "c", [
        ("typing", "🎯", "핵심가치 타자연습", "핵심가치를 타이핑하며 익혀 봅니다", False),
        ("tycoon", "🌾", "밸류체인 타이쿤", "사료 밸류체인을 직접 경영해 보는 게임", True),
    ]),
]

PLATFORM_COLS = 3      # 👈 한 줄에 카드 몇 개를 놓을지


def nav_box(name):
    """버튼에 이름표를 붙여 두는 상자. (색을 입히기 위한 것)
       이름표를 못 붙이는 옛 스트림릿에서도 오류 없이 넘어갑니다."""
    try:
        return st.container(key=name)
    except Exception:
        return st.container()


def draw_card(ico, title, desc, accent, beta=False):
    beta_html = "<span class='pf-beta'>Beta</span>" if beta else ""
    st.markdown(
        f"<div class='pf-card pf-{accent}'>"
        f"<div class='pf-ico'>{ico}</div>"
        f"<div class='pf-tt'>{title}{beta_html}</div>"
        f"<div class='pf-dd'>{desc}</div>"
        f"</div>", unsafe_allow_html=True)


def back_button(key=None):
    if st.button("⬅️ 플랫폼 메인으로 나가기", key=key):
        go_to("home")


# 어느 화면에서든 잔상 방지 꾸미기를 먼저 넣습니다.
st.markdown(BASE_CSS, unsafe_allow_html=True)

page = st.session_state.page

# --- [메인 화면] ---
if page == "home":
    st.markdown(PLATFORM_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='pf-hero'><h1>🚀 조직문화 활성화 통합 플랫폼</h1>"
        "<p>대한사료 구성원이 함께 배우고 성장하는 공간입니다.</p>"
        "<div class='bar'></div></div>", unsafe_allow_html=True)

    for label, ko, accent, cards in PLATFORM_MENU:
        st.markdown(
            f"<div class='pf-ghead'><span class='pf-chip pf-chip-{accent}'>{label}</span>"
            f"<span class='pf-gko'>{ko}</span><span class='pf-gline'></span></div>",
            unsafe_allow_html=True)

        cols = st.columns(PLATFORM_COLS)
        for i, (pg, ico, title, desc, beta) in enumerate(cards[:PLATFORM_COLS]):
            with cols[i]:
                draw_card(ico, title, desc, accent, beta)

                if pg == "tycoon":
                    # 타이쿤은 아직 테스트 중이라 비밀번호가 필요합니다.
                    # st.form 상자 안에 넣으면 '엔터'만 쳐도 입장합니다.
                    with st.form("tycoon_gate", clear_on_submit=False):
                        c_pw, c_btn = st.columns([2, 1])
                        test_pw = c_pw.text_input("비밀번호", type="password", key="tycoon_pw",
                                                  label_visibility="collapsed",
                                                  placeholder="비밀번호 입력")
                        go_tycoon = c_btn.form_submit_button("입장하기", use_container_width=True)
                    # 판정은 폼 밖에서 합니다. (폼 안에서는 화면 이동을 하면 안 됩니다)
                    if go_tycoon:
                        if test_pw == "dhfeedhr":   # 👈 타이쿤 테스트용 비밀번호
                            go_to("tycoon")
                        elif test_pw == "":
                            st.warning("비밀번호를 입력해 주세요.")
                        else:
                            st.error("비밀번호가 일치하지 않습니다.")
                else:
                    with nav_box("nav_%s_%s" % (accent, pg)):
                        if st.button("입장하기", key="btn_%s" % pg,
                                     use_container_width=True):
                            go_to(pg)

    st.markdown(
        f"<div class='pf-foot'>📊 현재 누적 접속 횟수 : {get_total_visitors()}회</div>",
        unsafe_allow_html=True)

# --- [각 프로그램 페이지] ---
elif page == "mentoring":
    back_button()
    load_module("mentoring").run_mentoring()

elif page == "leader":
    back_button()
    load_module("leader").run_leader_talk()

elif page == "class":
    back_button()
    load_module("oneday").run_class()

elif page == "typing":
    back_button()
    load_module("typing_game").run_typing_game()

elif page == "tycoon":
    back_button()
    load_module("tycoon_game").run_tycoon_game()

elif page == "library":
    # 도서관 안에도 '돌아가기' 버튼이 있어서, 이 버튼은 '플랫폼 메인으로
    # 나가는' 버튼이라고 분명히 적어 둡니다.
    back_button(key="btn_out_library")
    load_module("library").run_library()

# ==========================================
# ⚡ [속도 개선] 접속 기록은 화면을 다 그린 '뒤에' 남깁니다.
#   예전에는 기록을 먼저 하느라 화면이 그만큼 늦게 떴습니다.
# ==========================================
log_page_visit(page)
