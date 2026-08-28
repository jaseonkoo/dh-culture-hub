from utils import *

# ==========================================================
# ⌨️ 114 프로젝트 타자왕 챌린지 (p114.py)
#   - 사번 + 이름으로 로그인합니다. (members 시트)
#   - 틀린 글자는 본문에서 바로 빨갛게 표시됩니다.
#   - 한 페이지에 여러 줄을 함께 입력합니다.
#   - DB : 구글 시트 "대한사료_114P Challenge_DB"
# ==========================================================

P_DB = "대한사료_114P Challenge_DB"
P_TAB = "leaderboard"                 # 순위표 (화면에 보이는 것)
P_MEMBER_TAB = "members"              # 사번·이름 명단
P_LOG_TAB = "attempts"                # 👈 개인별 도전 기록 (통계용, 자동 생성됩니다)

P_HEADERS = ["이름", "소속팀", "직급", "기록(초)", "달성일"]
P_LOG_HEADERS = ["도전일시", "사번", "이름", "소속팀", "구분", "직급",
                 "순위부문", "기록(초)", "분당타수", "도전회차"]

TOP_ALL = 5      # 👈 전체 순위에서 보여 줄 인원
TOP_GROUP = 3    # 👈 직급별로 보여 줄 인원

# 👇 순위를 나누는 7개 직급. (순서를 바꾸면 화면 순서도 바뀝니다)
RANK_GROUPS = [
    "일반직 부장",
    "일반직 차장",
    "일반직 과장",
    "일반직 대리",
    "일반직 사원",
    "지원직 대리·주임",
    "지원직 사원",
]

P_SCOPE = ["https://spreadsheets.google.com/feeds",
           "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/drive.file",
           "https://www.googleapis.com/auth/drive"]


# ==========================================================
# 챌린지에 들어갈 내용 (114 프로젝트)
#   한 페이지 안의 줄들은 '한 화면에 같이' 나옵니다.
#   그 페이지의 줄을 모두 정확히 치면 다음 페이지로 넘어갑니다.
# ==========================================================
P114_STEPS = [
    {"title": "🎯 1단계 : 우리의 목표",
     "lines": ["판매량 100만톤 매출 1조 영업이익 400억 달성을 향한 5대 핵심과제 114 프로젝트"]},

    {"title": "📊 2단계 : 핵심과제 ①",
     "lines": ["통합 경영 운영 체계 및 핵심지표 고도화",
               "부서별 회의체 중점 내용과 데이터를 핵심지표화, 데이터를 연동한 통합경영 운영체계 구축"]},

    {"title": "🌱 3단계 : 핵심과제 ②",
     "lines": ["성장을 가속화하는 문화 구축",
               "스타 인재들의 원팀 시너지를 바탕으로 114 프로젝트 달성을 위한 성장중심 조직구현"]},

    {"title": "📈 4단계 : 핵심과제 ③",
     "lines": ["영업경쟁력 강화 및 대리점 고도화",
               "축산시장 내 강력한 영업 경쟁력을 갖춘 지속 성장 가능한 영업 조직 구축"]},

    {"title": "🏅 5단계 : 핵심과제 ④",
     "lines": ["고객중심 품질 혁신",
               "고객이 만족하는 품질 전 직원이 함께 만드는 최적의 품질"]},

    {"title": "📣 6단계 : 핵심과제 ⑤",
     "lines": ["마케팅팀 구축",
               "사료를 판매하는 회사를 넘어 고객의 수익을 설계하고 증명하는 회사로의 전환"]},
]

TOTAL_LINES = sum(len(s["lines"]) for s in P114_STEPS)
TOTAL_CHARS = sum(len(ln) for s in P114_STEPS for ln in s["lines"])


class P114Busy(Exception):
    """구글 시트가 잠깐 응답하지 않을 때."""
    pass


def _p_retry(fn, *a, **kw):
    """503·429 같은 '잠깐 나는 오류'는 조금 기다렸다 다시 불러 봅니다."""
    last = None
    for i in range(3):
        try:
            return fn(*a, **kw)
        except gspread.exceptions.APIError as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (429, 500, 502, 503):
                last = e
                time.sleep(0.8 * (i + 1))
                continue
            raise
        except Exception as e:
            last = e
            if i >= 1:
                raise
            time.sleep(1.0)
    raise P114Busy(str(last))


@st.cache_resource(show_spinner=False)
def init_gspread_p114():
    """구글 로그인은 서버당 한 번만. 실패하면 기억하지 않습니다."""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], P_SCOPE)
    client = gspread.authorize(creds)
    return _p_retry(client.open, P_DB)


@st.cache_resource(show_spinner=False)
def get_p114_ws():
    """leaderboard 탭. 없으면 만들고, 열 이름도 없으면 넣어 줍니다."""
    doc = init_gspread_p114()
    try:
        ws = _p_retry(doc.worksheet, P_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = _p_retry(doc.add_worksheet, title=P_TAB, rows=2000, cols=10)
        _p_retry(ws.append_row, P_HEADERS)
        return ws
    try:
        first = _p_retry(ws.row_values, 1)
        if not first:
            _p_retry(ws.append_row, P_HEADERS)
    except Exception:
        pass
    return ws


@st.cache_resource(show_spinner=False)
def get_p114_log_ws():
    """attempts 탭(개인별 도전 기록). 없으면 자동으로 만듭니다."""
    doc = init_gspread_p114()
    try:
        ws = _p_retry(doc.worksheet, P_LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = _p_retry(doc.add_worksheet, title=P_LOG_TAB, rows=5000, cols=12)
        _p_retry(ws.append_row, P_LOG_HEADERS)
        return ws
    try:
        first = _p_retry(ws.row_values, 1)
        if not first:
            _p_retry(ws.append_row, P_LOG_HEADERS)
    except Exception:
        pass
    return ws


@st.cache_data(ttl=10, show_spinner=False)
def get_p114_attempts():
    """개인별 도전 기록 전체를 읽어 옵니다. (통계·회차 계산용)"""
    try:
        return _p_retry(get_p114_log_ws().get_all_records)
    except Exception:
        return []


def save_p114_attempt(user, score):
    """도전 한 번을 그대로 기록해 둡니다. (순위와 별개로 전부 남습니다)"""
    try:
        ws = get_p114_log_ws()
        kst = datetime.timezone(datetime.timedelta(hours=9))
        now_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

        # 이 사람이 몇 번째 도전인지 셉니다.
        saban = str(user.get("saban", "")).strip()
        nth = 1
        for r in get_p114_attempts():
            if str(r.get("사번", "")).strip() == saban:
                nth += 1

        sec = _p_float(score, 0)
        tpm = round(TOTAL_CHARS / sec * 60) if sec > 0 else 0

        _p_retry(ws.append_row, [
            now_str,
            saban,
            user.get("name", ""),
            user.get("team", ""),
            user.get("gubun", ""),
            user.get("position", ""),
            user.get("group", ""),
            sec,
            tpm,
            nth,
        ])
        get_p114_attempts.clear()
        return True
    except Exception:
        # 기록 저장이 실패해도 순위 등록은 그대로 진행합니다.
        return False


@st.cache_data(ttl=300, show_spinner=False)
def get_p114_members():
    """members 탭(사번·이름 명단)을 읽어 옵니다."""
    doc = init_gspread_p114()
    ws = _p_retry(doc.worksheet, P_MEMBER_TAB)
    return _p_retry(ws.get_all_records)


def _reset_p114_conn():
    for f in (init_gspread_p114, get_p114_ws, get_p114_board, get_p114_members,
              get_p114_log_ws, get_p114_attempts):
        try:
            f.clear()
        except Exception:
            pass


@st.cache_data(ttl=5, show_spinner=False)
def get_p114_board():
    """순위표를 읽어 옵니다. 실패는 기억하지 않습니다."""
    return _p_retry(get_p114_ws().get_all_records)


def save_p114_score(name, team, rank_group, score):
    try:
        ws = get_p114_ws()
        # 서버 시간이 아니라 '한국 시간(KST)'으로 기록합니다.
        kst = datetime.timezone(datetime.timedelta(hours=9))
        today_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
        _p_retry(ws.append_row, [name, team, rank_group, score, today_str])
        get_p114_board.clear()
        return True
    except Exception:
        st.error("⚠️ 기록 저장에 실패했습니다. 잠시 후 다시 시도하거나 관리자에게 문의하세요.")
        return False


def _p_float(v, default=999.0):
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _p_esc(x):
    """화면에 그대로 넣어도 안전하도록 특수문자를 바꿔 줍니다."""
    return (str(x if x is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col(row, *names):
    """열 이름이 조금씩 달라도 찾아 줍니다. (사번 / 사원번호 / saban ...)"""
    for n in names:
        for k in row.keys():
            if str(k).strip().lower() == n.lower():
                v = str(row[k]).strip()
                if v:
                    return v
    return ""


def _map_group(gubun, position):
    """구분(gubun) + 직급(position) 을 합쳐서 7개 순위 부문 중 하나로 맞춥니다.
       예) 일반직 + 부장  →  일반직 부장
           지원직 + 주임  →  지원직 대리·주임"""
    g = str(gubun or "").strip()
    p = str(position or "").strip()
    if not g and not p:
        return ""

    cand = ("%s %s" % (g, p)).strip()
    if cand in RANK_GROUPS:
        return cand

    # 띄어쓰기만 다른 경우도 찾아 줍니다.
    flat = cand.replace(" ", "")
    for r in RANK_GROUPS:
        if r.replace(" ", "") == flat:
            return r

    # 지원직의 대리·주임은 한 부문으로 묶습니다.
    if g.startswith("지원"):
        if p in ("대리", "주임", "대리·주임", "대리/주임", "주임·대리"):
            return "지원직 대리·주임"
        if p in ("사원",):
            return "지원직 사원"
    if g.startswith("일반"):
        if p in ("부장", "차장", "과장", "대리", "사원"):
            return "일반직 " + p

    # 구분 없이 직급만 적혀 있는 경우 (일반직으로 봅니다)
    if not g and p in ("부장", "차장", "과장", "대리", "사원"):
        return "일반직 " + p
    return ""


def find_member(saban, name):
    """members 시트에서 사번+이름이 맞는 사람을 찾습니다."""
    saban = str(saban).strip()
    name = str(name).strip()
    if not saban or not name:
        return None
    for r in get_p114_members():
        s = _col(r, "사번", "사원번호", "사번호", "saban", "employee_id", "id")
        n = _col(r, "이름", "성명", "name")
        if s == saban and n == name:
            gubun = _col(r, "gubun", "구분", "직군", "고용구분")
            position = _col(r, "position", "직급", "직위", "rank", "grade")
            group = _map_group(gubun, position)
            if not group:
                # 한 칸에 '일반직 부장' 처럼 통째로 적혀 있는 경우
                group = _map_group("", _col(r, "순위부문", "부문")) or \
                        _map_group(*(_col(r, "직급", "position").split(" ", 1) + [""])[:2])
            return {
                "saban": s,
                "name": n,
                "team": _col(r, "소속팀", "팀명", "부서", "team", "dept"),
                "gubun": gubun,
                "position": position,
                "group": group,
            }
    return None


def _target_html(text, idx, typed=""):
    """타이핑할 문장을 한 글자씩 쪼개서 보여 줍니다.
       치는 즉시 맞은 글자는 초록, 틀린 글자는 빨강으로 바뀝니다."""
    out = []
    for i, ch in enumerate(text):
        cls = "pch"
        if typed and i < len(typed):
            cls += " ok" if typed[i] == ch else " bad"
        shown = "&nbsp;" if ch == " " else _p_esc(ch)
        out.append("<span class='%s' data-ch=\"%s\">%s</span>" % (cls, _p_esc(ch), shown))
    extra = ""
    if typed and len(typed) > len(text):
        extra = "<span class='pch bad'>%s</span>" % _p_esc(typed[len(text):]).replace(" ", "&nbsp;")
    return "<div class='p-line' data-idx='%d'>%s%s</div>" % (idx, "".join(out), extra)


def run_114_challenge():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_114_challenge()
    except gspread.exceptions.WorksheetNotFound:
        st.markdown("### ⌨️ 114 프로젝트 타자왕 챌린지")
        st.error("구글 시트 `%s` 에 **%s** 탭이 없습니다. "
                 "사번·이름 명단이 담긴 탭 이름을 `%s` 로 만들어 주세요."
                 % (P_DB, P_MEMBER_TAB, P_MEMBER_TAB))
        if st.button("🔄 다시 시도", key="p_retry_btn2", type="primary"):
            _reset_p114_conn(); st.rerun()
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        st.markdown("### ⌨️ 114 프로젝트 타자왕 챌린지")
        if code in (429, 500, 502, 503) or isinstance(e, P114Busy):
            st.warning("⏳ 구글 시트가 잠시 응답하지 않고 있습니다. "
                       "**5~10초 뒤 아래 [다시 시도] 버튼을 눌러 주세요.**")
        elif code == 403:
            st.error("구글 시트 접근 권한이 없습니다. "
                     "`%s` 파일을 서비스 계정 이메일에 **편집자**로 공유했는지 확인해 주세요." % P_DB)
        else:
            st.error("자료를 불러오는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:200])
        if st.button("🔄 다시 시도", key="p_retry_btn", type="primary"):
            _reset_p114_conn()
            st.rerun()


P114_CSS = """
<style>
.stTextInput, .stSelectbox { margin-bottom: 12px !important; }
.p-rank-card { border: 2px solid #2F6FB5; padding: 15px; border-radius: 10px;
               background-color: #F5F9FF; text-align: center; margin-bottom: 15px; }
.p-gold { color: #D4AF37; font-size: 1.5em; font-weight: bold; }
.p-silver { color: #A9A9A9; font-size: 1.3em; font-weight: bold; }
.p-bronze { color: #CD7F32; font-size: 1.1em; font-weight: bold; }
.p-goal { background: linear-gradient(135deg,#1B3B6F,#2F6FB5); color:#fff;
          border-radius: 14px; padding: 22px 24px; margin-bottom: 18px; }
.p-goal h3 { margin:0 0 10px; font-size:1.25rem; }
.p-goal p { margin:0; font-size:.95rem; line-height:1.7; opacity:.92; }
.p-who { background:#EEF4FC; border:1px solid #CFE0F5; border-radius:10px;
         padding:12px 16px; font-size:.95rem; color:#1B3B6F; }

/* 타이핑할 문장 : 한 글자씩 색이 바뀝니다 */
.p-line { font-size:1.05rem; font-weight:700; line-height:2.0; color:#1B3B6F;
          background:#EEF4FC; border-left:5px solid #2F6FB5; border-radius:6px;
          padding:12px 14px; margin:4px 0 4px; word-break:break-all;
          letter-spacing:.2px; }
.p-line.done { background:#EAF7EF; border-left-color:#1E8449; }
.pch.ok  { color:#1E8449; }
.pch.bad { color:#ffffff; background:#E5484D; border-radius:3px; }

/* 숨김 입력칸 : 지우지 않고 화면 밖으로 밀어내어 기능은 100% 살려둡니다. */
div[data-testid="stTextInput"]:has(input[aria-label="p_hidden_time"]) {
    position: absolute !important;
    left: -9999px !important;
    opacity: 0 !important;
    height: 0px !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
"""


def _run_114_challenge():
    st.markdown(P114_CSS, unsafe_allow_html=True)

    st.header("⌨️ 114 프로젝트 타자왕 챌린지")
    st.caption("판매량 100만톤 · 매출 1조 · 영업이익 400억. 우리의 목표를 가장 빠르고 정확하게 새긴 주인공은?")
    st.markdown("---")

    tab1, tab2 = st.tabs(["🎮 챌린지 시작하기", "🏆 명예의 전당"])

    # =========================================================
    # 🎮 게임
    # =========================================================
    with tab1:
        if 'p_step' not in st.session_state: st.session_state.p_step = 0
        if 'p_is_playing' not in st.session_state: st.session_state.p_is_playing = False
        if 'p_user' not in st.session_state: st.session_state.p_user = None

        # ---------- 로그인 ----------
        if not st.session_state.p_user:
            st.markdown(
                "<div class='p-goal'><h3>🏁 114 프로젝트</h3>"
                "<p>판매량 <b>100만톤</b> · 매출 <b>1조</b> · 영업이익 <b>400억</b> 달성을 향한 "
                "<b>5대 핵심과제</b>입니다.<br>"
                "타이핑하면서 우리가 어디로 가고 있는지 함께 새겨 봅니다.</p></div>",
                unsafe_allow_html=True)

            st.subheader("🔒 로그인")
            st.caption("사번과 이름을 입력해 주세요. 회사 명단과 대조합니다.")

            with st.form("p_login_form", clear_on_submit=False):
                lc1, lc2 = st.columns(2)
                in_saban = lc1.text_input("사번", placeholder="사번 입력")
                in_name = lc2.text_input("이름", placeholder="이름 입력")
                go_login = st.form_submit_button("로그인", type="primary",
                                                 use_container_width=True)

            if go_login:
                if not str(in_saban).strip() or not str(in_name).strip():
                    st.warning("사번과 이름을 모두 입력해 주세요.")
                else:
                    with st.spinner("명단을 확인하는 중입니다..."):
                        who = find_member(in_saban, in_name)
                    if who:
                        st.session_state.p_user = who
                        st.rerun()
                    else:
                        st.error("사번 또는 이름이 명단과 맞지 않습니다. "
                                 "다시 확인해 주시고, 계속 안 되면 인사총무팀에 문의해 주세요.")
            return

        user = st.session_state.p_user

        # 명단에 직급이 없으면 직접 고르게 합니다.
        if user.get("group") not in RANK_GROUPS:
            st.markdown(
                "<div class='p-who'>👤 <b>%s</b> 님 (사번 %s)</div>"
                % (_p_esc(user["name"]), _p_esc(user["saban"])), unsafe_allow_html=True)
            st.warning("명단에 직급 정보가 없어 순위를 나눌 수 없습니다. 직급을 골라 주세요.")
            g = st.selectbox("직급", RANK_GROUPS, key="p_pick_group")
            if st.button("확인", type="primary", key="p_group_ok"):
                user["group"] = g
                st.session_state.p_user = user
                st.rerun()
            return

        # ---------- 로그인 이후 ----------
        wc1, wc2 = st.columns([4, 1])
        wc1.markdown(
            "<div class='p-who'>👤 <b>%s</b> 님 · %s · %s</div>"
            % (_p_esc(user["name"]), _p_esc(user.get("team") or "-"), _p_esc(user["group"])),
            unsafe_allow_html=True)
        if wc2.button("로그아웃", key="p_logout", use_container_width=True):
            for k in ('p_user', 'p_is_playing', 'p_step', 'p_hidden_time', 'p_score_saved'):
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

        st.markdown("")

        if not st.session_state.p_is_playing:
            # 지금까지의 내 도전 기록을 한 줄로 알려 줍니다.
            _mine = [r for r in get_p114_attempts()
                     if str(r.get("사번", "")).strip() == str(user.get("saban", "")).strip()]
            if _mine:
                _best = min(_p_float(r.get("기록(초)")) for r in _mine)
                st.success("📈 지금까지 **%d번** 도전하셨습니다. 최고 기록은 **%.2f초** 입니다."
                           % (len(_mine), _best))

            components.html(
                "<script>sessionStorage.removeItem('p114StartTime');"
                "sessionStorage.removeItem('p114EndTime');"
                "sessionStorage.removeItem('p114Sent');</script>", height=0)

            st.info("💡 **게임 규칙:** 첫 글자를 치는 순간부터 초시계가 작동합니다. "
                    "총 **%d줄**이며, 틀린 글자는 **빨갛게** 바로 표시됩니다. "
                    "한 페이지의 줄을 모두 정확히 치면 다음 페이지로 넘어갑니다." % TOTAL_LINES)

            if st.button("🚀 챌린지 시작하기", type="primary", use_container_width=True,
                         key="p_start_btn"):
                st.session_state.p_is_playing = True
                st.session_state.p_step = 0
                st.rerun()

        else:
            is_finished = st.session_state.p_step >= len(P114_STEPS)

            controller_html = f"""
            <html>
            <head>
            <style>
                body {{ margin: 0; font-family: sans-serif; display: flex; justify-content: center; align-items: center; }}
                .timer-box {{ font-size: 1.8rem; font-weight: bold; color: #ff4b4b; }}
                .success-box {{ font-size: 2.5rem; font-weight: bold; color: #2F6FB5; }}
            </style>
            </head>
            <body>
                <div id="display-box" class="{'success-box' if is_finished else 'timer-box'}">
                    {'🎉 타이핑 완료!' if is_finished else '⏱️ 진행 시간: '}<span id="stopwatch">0.00</span> 초
                </div>
                <script>
                    const isFinished = {'true' if is_finished else 'false'};
                    const parent = window.parent;
                    const timerDisplay = document.getElementById('stopwatch');

                    if (isFinished) {{
                        if (!sessionStorage.getItem('p114EndTime')) {{
                            sessionStorage.setItem('p114EndTime', Date.now());
                        }}
                        let start = parseInt(sessionStorage.getItem('p114StartTime') || Date.now());
                        let end = parseInt(sessionStorage.getItem('p114EndTime'));
                        let finalTime = ((end - start) / 1000).toFixed(2);
                        timerDisplay.innerText = finalTime;

                        let attempts = 0;
                        let trySend = setInterval(() => {{
                            const hiddenInput = parent.document.querySelector('input[aria-label="p_hidden_time"]');
                            if (hiddenInput) {{
                                clearInterval(trySend);
                                if (!sessionStorage.getItem('p114Sent')) {{
                                    let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    setter.call(hiddenInput, finalTime);
                                    hiddenInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    setTimeout(() => {{
                                        hiddenInput.focus();
                                        hiddenInput.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                                        hiddenInput.blur();
                                    }}, 100);
                                    sessionStorage.setItem('p114Sent', 'true');
                                }}
                            }}
                            attempts++;
                            if (attempts > 50) clearInterval(trySend);
                        }}, 100);

                    }} else {{
                        // 초시계
                        setInterval(() => {{
                            if (sessionStorage.getItem('p114StartTime')) {{
                                let start = parseInt(sessionStorage.getItem('p114StartTime'));
                                timerDisplay.innerText = ((Date.now() - start) / 1000).toFixed(2);
                            }}
                        }}, 50);

                        // 글자 맞춰 보기 + 커서 자동 이동
                        setInterval(() => {{
                            try {{
                                const doc = parent.document;
                                const tgts = doc.querySelectorAll('.p-line');
                                const ins  = doc.querySelectorAll('input[aria-label^="타이핑"]');
                                let focusIdx = -1;
                                let onMine = false;
                                let activeIdx = -1;
                                let okMap = [];

                                for (let k = 0; k < ins.length; k++) {{
                                    if (doc.activeElement === ins[k]) {{ onMine = true; activeIdx = k; }}

                                    if (!ins[k].dataset.setupDone) {{
                                        const block = e => {{ e.preventDefault(); alert("⚠️ 꼼수 금지! 직접 치세요."); }};
                                        ins[k].addEventListener('paste', block);
                                        ins[k].addEventListener('drop', block);
                                        ins[k].addEventListener('keydown', e => {{
                                            if (e.key === 'Enter') {{
                                                // 👉 엔터를 누르면 아래 입력칸으로 커서를 옮깁니다.
                                                const all = doc.querySelectorAll('input[aria-label^="타이핑"]');
                                                if (k + 1 < all.length) {{
                                                    setTimeout(() => {{ try {{ all[k + 1].focus(); }} catch(x) {{}} }}, 30);
                                                }}
                                            }} else if (e.key !== 'Tab') {{
                                                if (!sessionStorage.getItem('p114StartTime')) {{
                                                    sessionStorage.setItem('p114StartTime', Date.now());
                                                }}
                                            }}
                                        }});
                                        ins[k].dataset.setupDone = "true";
                                    }}

                                    if (k >= tgts.length) continue;
                                    const spans = tgts[k].querySelectorAll('.pch');
                                    const v = ins[k].value;
                                    let allok = (v.length === spans.length);

                                    for (let i = 0; i < spans.length; i++) {{
                                        if (i < v.length) {{
                                            const good = (v[i] === spans[i].dataset.ch);
                                            spans[i].className = 'pch ' + (good ? 'ok' : 'bad');
                                            if (!good) allok = false;
                                        }} else {{
                                            spans[i].className = 'pch';
                                        }}
                                    }}
                                    okMap[k] = allok;
                                    if (allok) tgts[k].classList.add('done');
                                    else {{ tgts[k].classList.remove('done'); if (focusIdx < 0) focusIdx = k; }}
                                }}

                                // ① 아직 우리 입력칸에 커서가 없으면 → 안 끝난 칸으로
                                if (!onMine && focusIdx >= 0 && ins[focusIdx]) {{
                                    ins[focusIdx].focus();
                                }}
                                // ② 이미 다 친 칸에 커서가 있으면 → 안 끝난 칸으로 옮깁니다.
                                else if (onMine && activeIdx >= 0 && okMap[activeIdx]
                                         && focusIdx >= 0 && ins[focusIdx]) {{
                                    ins[focusIdx].focus();
                                }}
                            }} catch(err) {{ }}
                        }}, 80);
                    }}
                </script>
            </body>
            </html>
            """

            components.html(controller_html, height=100)

            if not is_finished:
                cur = P114_STEPS[st.session_state.p_step]
                lines = cur["lines"]
                st.markdown(f"**{cur['title']}**")

                typed_all = []
                for li, line_text in enumerate(lines):
                    key = "p_in_%d_%d" % (st.session_state.p_step, li)
                    typed = str(st.session_state.get(key, "") or "")
                    st.markdown(_target_html(line_text, li, typed), unsafe_allow_html=True)
                    st.text_input("타이핑 %d" % (li + 1), key=key,
                                  label_visibility="collapsed",
                                  placeholder="위 문장을 그대로 입력하세요")
                    typed_all.append(str(st.session_state.get(key, "") or ""))

                # 이 페이지의 모든 줄이 정확하면 다음 페이지로
                if all(typed_all[i] == lines[i] for i in range(len(lines))):
                    st.session_state.p_step += 1
                    st.rerun()

                done_lines = (sum(len(s["lines"]) for s in P114_STEPS[:st.session_state.p_step])
                              + sum(1 for i in range(len(lines)) if typed_all[i] == lines[i]))
                st.progress(min(done_lines / TOTAL_LINES, 1.0),
                            text="%d / %d 줄" % (done_lines, TOTAL_LINES))
                st.caption("한 글자도 빠짐없이 그대로 입력하세요. "
                           "**빨간 글자**가 틀린 부분입니다. (띄어쓰기·쉼표 포함)")

            else:
                js_time = st.text_input("p_hidden_time", key="p_hidden_time",
                                        label_visibility="collapsed")

                if js_time and 'p_score_saved' not in st.session_state:
                    final_time_float = _p_float(js_time, 0.0)
                    with st.spinner("📡 최종 기록 확인 및 명예의 전당 등록 중... (약 2~3초 소요)"):
                        # ① 개인별 도전 기록 (attempts 탭) — 통계용으로 전부 남깁니다.
                        save_p114_attempt(user, final_time_float)
                        # ② 순위표 (leaderboard 탭)
                        if save_p114_score(user["name"], user.get("team", ""),
                                           user["group"], final_time_float):
                            st.session_state.p_score_saved = True
                    st.rerun()

                if 'p_score_saved' in st.session_state:
                    st.balloons()
                    st.markdown(f"""
                    <div class="p-rank-card">
                        <h2>🎉 {_p_esc(user['name'])}님, 완료를 축하합니다!</h2>
                        <h1 style="color: #2F6FB5;">⏱️ 최종 기록: {js_time}초</h1>
                        <p><b>{_p_esc(user['group'])}</b> 부문에 기록이 등록되었습니다.</p>
                        <p>114 프로젝트, 이제 손끝으로도 기억하시겠죠?</p>
                    </div>
                    """, unsafe_allow_html=True)

                    st.divider()
                    if st.button("🔄 처음부터 다시 도전하기", key="p_again_btn"):
                        st.session_state.p_is_playing = False
                        st.session_state.p_step = 0
                        for k in list(st.session_state.keys()):
                            if str(k).startswith("p_in_"):
                                del st.session_state[k]
                        for k in ('p_hidden_time', 'p_score_saved'):
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

    # =========================================================
    # 🏆 순위 (전체 5위 + 직급별 3위)
    # =========================================================
    with tab2:
        st.subheader("🏆 명예의 전당")

        if st.button("🔄 순위 새로고침", key="p_refresh_btn"):
            get_p114_board.clear()
            st.rerun()

        board = get_p114_board()

        if not board:
            st.info("아직 등록된 기록이 없습니다. 첫 번째 타자왕에 도전하세요!")
        else:
            # 한 사람이 여러 번 도전했으면 '가장 빠른 기록'만 남깁니다.
            best = {}
            for r in board:
                nm = str(r.get('이름', '')).strip()
                gp = str(r.get('직급', '')).strip()
                if not nm:
                    continue
                key = (gp, nm)
                sec = _p_float(r.get('기록(초)'))
                if key not in best or sec < _p_float(best[key].get('기록(초)')):
                    best[key] = r
            rows = sorted(best.values(), key=lambda x: _p_float(x.get('기록(초)')))

            # ---------- 전체 TOP 5 ----------
            st.markdown("#### 🥇 전체 순위 TOP %d" % TOP_ALL)
            top_all = rows[:TOP_ALL]
            medals = [("🥇 1위", "p-gold"), ("🥈 2위", "p-silver"), ("🥉 3위", "p-bronze")]
            cols = st.columns(3)
            for i in range(min(len(top_all), 3)):
                with cols[i]:
                    st.markdown(f"""
                    <div style="
                        border: 2px solid #efefef;
                        padding: 25px 10px;
                        border-radius: 15px;
                        background-color: #ffffff;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                        text-align: center;
                        display: block;
                        width: 100%;
                    ">
                        <div class="{medals[i][1]}" style="width: 100%; text-align: center; margin-bottom: 12px;">
                            {medals[i][0]}
                        </div>
                        <div style="width: 100%; text-align: center; font-size: 1.6em; font-weight: 800; color: #1e293b; margin-bottom: 4px;">
                            {_p_esc(top_all[i].get('이름', '-'))}
                        </div>
                        <div style="width: 100%; text-align: center; font-size: 0.95em; color: #64748b; margin-bottom: 4px; font-weight: 500;">
                            {_p_esc(top_all[i].get('소속팀', '-'))}
                        </div>
                        <div style="width: 100%; text-align: center; font-size: 0.85em; color: #2F6FB5; margin-bottom: 14px; font-weight: 700;">
                            {_p_esc(top_all[i].get('직급', '-'))}
                        </div>
                        <div style="width: 100%; text-align: center; font-size: 1.8em; font-weight: bold; color: #ff4b4b; background-color: #fff1f1; border-radius: 8px; padding: 5px 0;">
                            {_p_float(top_all[i].get('기록(초)'), 0):.2f}초
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if len(top_all) > 3:
                df = pd.DataFrame(top_all[3:])
                df.index = range(4, 4 + len(df))
                df.index.name = "순위"
                for c in ['이름', '소속팀', '직급', '기록(초)', '달성일']:
                    if c not in df.columns:
                        df[c] = "-"
                df = df[['이름', '소속팀', '직급', '기록(초)', '달성일']]
                df['기록(초)'] = df['기록(초)'].apply(lambda x: f"{_p_float(x, 0):.2f}초")
                styled_df = df.style.set_properties(**{
                    'text-align': 'center', 'font-family': 'sans-serif'
                }).set_table_styles([
                    {'selector': 'th', 'props': [('text-align', 'center'),
                                                 ('background-color', '#f8f9fa')]}
                ])
                st.dataframe(styled_df, use_container_width=True)

            # ---------- 직급별 참여 현황 (3위까지) ----------
            st.markdown("---")
            st.markdown("#### 📊 직급별 참여 현황 (TOP %d)" % TOP_GROUP)

            def _cell(item):
                if not item:
                    return "-"
                return "%s (%s) · %.2f초" % (item.get('이름', '-'),
                                            item.get('소속팀', '-'),
                                            _p_float(item.get('기록(초)'), 0))

            stat_rows = []
            for g in RANK_GROUPS:
                mine = [r for r in rows if str(r.get('직급', '')).strip() == g]
                grp = mine[:TOP_GROUP]
                stat_rows.append({
                    "직급": g,
                    "참여 인원": len(mine),
                    "🥇 1위": _cell(grp[0] if len(grp) > 0 else None),
                    "🥈 2위": _cell(grp[1] if len(grp) > 1 else None),
                    "🥉 3위": _cell(grp[2] if len(grp) > 2 else None),
                })
            st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)
            st.caption("※ 한 사람이 여러 번 도전한 경우 **가장 빠른 기록**만 순위에 반영됩니다.")
