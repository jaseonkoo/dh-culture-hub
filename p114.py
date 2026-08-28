from utils import *

# ==========================================================
# ⌨️ 114 프로젝트 타자왕 챌린지 (p114.py)
#   - 핵심가치 타자 릴레이와 똑같은 방식입니다.
#   - 순위는 전체 5위 + 직급별 3위로 보여 줍니다.
#   - DB : 구글 시트 "대한사료_114P Challenge_DB" 의 leaderboard 탭
# ==========================================================

P_DB = "대한사료_114P Challenge_DB"
P_TAB = "leaderboard"
P_HEADERS = ["이름", "소속팀", "직급", "기록(초)", "달성일"]

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
#   한 페이지 안에 여러 줄을 둘 수 있습니다.
#   한 줄을 정확히 치면 다음 줄, 그 페이지를 다 치면 다음 페이지로 넘어갑니다.
# ==========================================================
P114_STEPS = [
    {"title": "🎯 1단계 : 우리의 목표",
     "lines": ["판매량 100만톤 매출 1조 영업이익 400억 달성을 향한 5대 핵심과제 114 프로젝트"]},

    {"title": "📊 2단계 : 핵심과제 ①",
     "lines": ["통합 경영 운영 체계 및 핵심지표 고도화",
               "부서별 회의체 중점 내용과 데이터를 핵심지표화, 데이터를 연동한 통합경영운영체계 구축"]},

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


def _reset_p114_conn():
    for f in (init_gspread_p114, get_p114_ws, get_p114_board):
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


def _show_typo(target, typed):
    """어디서부터 틀렸는지 눈으로 보여 줍니다."""
    n = min(len(target), len(typed))
    i = 0
    while i < n and target[i] == typed[i]:
        i += 1

    def paint(txt, cut, bad_bg):
        okp = _p_esc(txt[:cut]).replace(" ", "&nbsp;")
        badp = _p_esc(txt[cut:]).replace(" ", "&nbsp;")
        if not badp:
            return "<span style='color:#1E8449'>%s</span>" % okp
        return ("<span style='color:#1E8449'>%s</span>"
                "<span style='background:%s;color:#B3261E;font-weight:700;"
                "border-radius:3px;padding:1px 2px'>%s</span>" % (okp, bad_bg, badp))

    if len(typed) < len(target) and i == len(typed):
        head = "아직 덜 입력하셨습니다. (%d / %d 글자)" % (len(typed), len(target))
    elif len(typed) > len(target) and i == len(target):
        head = "글자가 더 들어갔습니다. (%d / %d 글자)" % (len(typed), len(target))
    else:
        want = target[i] if i < len(target) else ""
        got = typed[i] if i < len(typed) else ""
        head = "%d번째 글자부터 다릅니다.  (정답 「%s」 ← 입력하신 글자 「%s」)" % (
            i + 1, want or "없음", got or "없음")

    st.markdown(
        "<div style='border:1px solid #F5C2C7;background:#FFF5F5;border-radius:8px;"
        "padding:12px 14px;margin:6px 0 10px;font-size:.95rem;line-height:1.9'>"
        "<div style='color:#B3261E;font-weight:700;margin-bottom:8px'>⚠️ %s</div>"
        "<div><span style='color:#8C806E;font-size:.85rem'>정 답 &nbsp;</span>%s</div>"
        "<div><span style='color:#8C806E;font-size:.85rem'>입력값 &nbsp;</span>%s</div>"
        "<div style='color:#8C806E;font-size:.82rem;margin-top:8px'>"
        "빨간 부분부터 다릅니다. 그 자리를 고치고 다시 Enter를 누르세요.</div>"
        "</div>" % (_p_esc(head), paint(target, i, "#FFE3E3"), paint(typed, i, "#FFD1D1")),
        unsafe_allow_html=True)


def run_114_challenge():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_114_challenge()
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


def _run_114_challenge():
    st.markdown("""
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
        .p-done { color:#1E8449; font-size:.95rem; line-height:1.7; margin:2px 0 10px; }
        .p-todo { color:#A8B0BA; font-size:.95rem; line-height:1.7; margin:2px 0 10px; }
        .p-now  { font-size:1.05rem; font-weight:700; color:#1B3B6F; line-height:1.75;
                  background:#EEF4FC; border-left:5px solid #2F6FB5; border-radius:6px;
                  padding:12px 14px; margin:4px 0 6px; }

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
    """, unsafe_allow_html=True)

    st.header("⌨️ 114 프로젝트 타자왕 챌린지")
    st.caption("판매량 100만톤 · 매출 1조 · 영업이익 400억. 우리의 목표를 가장 빠르고 정확하게 새긴 주인공은?")
    st.markdown("---")

    tab1, tab2 = st.tabs(["🎮 챌린지 시작하기", "🏆 명예의 전당"])

    # =========================================================
    # 🎮 게임
    # =========================================================
    with tab1:
        if 'p_step' not in st.session_state: st.session_state.p_step = 0
        if 'p_line' not in st.session_state: st.session_state.p_line = 0
        if 'p_is_playing' not in st.session_state: st.session_state.p_is_playing = False
        if 'p_name' not in st.session_state: st.session_state.p_name = ""
        if 'p_team' not in st.session_state: st.session_state.p_team = ""
        if 'p_group' not in st.session_state: st.session_state.p_group = RANK_GROUPS[0]

        if not st.session_state.p_is_playing:
            components.html(
                "<script>sessionStorage.removeItem('p114StartTime');"
                "sessionStorage.removeItem('p114EndTime');"
                "sessionStorage.removeItem('p114Sent');</script>", height=0)

            st.markdown(
                "<div class='p-goal'><h3>🏁 114 프로젝트</h3>"
                "<p>판매량 <b>100만톤</b> · 매출 <b>1조</b> · 영업이익 <b>400억</b> 달성을 향한 "
                "<b>5대 핵심과제</b>입니다.<br>"
                "타이핑하면서 우리가 어디로 가고 있는지 함께 새겨 봅니다.</p></div>",
                unsafe_allow_html=True)

            st.subheader("도전자 정보 입력")
            c1, c2 = st.columns(2)
            p_name = c1.text_input("성함 (예: 홍길동)", key="p_in_name")
            p_team = c2.text_input("소속팀 (예: 인사총무팀)", key="p_in_team")
            p_group = st.selectbox("직급 (순위는 직급별로도 매겨집니다)", RANK_GROUPS, key="p_in_group")

            st.info("💡 **게임 규칙:** 첫 글자를 치는 순간부터 초시계가 작동합니다. "
                    "총 **%d줄**이며, 한 줄을 정확히 치고 Enter를 누르면 다음 줄로 넘어갑니다. "
                    "완료 후 자동으로 커서가 이동하니 키보드에서 손을 떼지 마세요!" % TOTAL_LINES)

            if st.button("🚀 챌린지 시작하기", type="primary", use_container_width=True,
                         key="p_start_btn"):
                if p_name and p_team:
                    st.session_state.p_name = p_name
                    st.session_state.p_team = p_team
                    st.session_state.p_group = p_group
                    st.session_state.p_is_playing = True
                    st.session_state.p_step = 0
                    st.session_state.p_line = 0
                    st.rerun()
                else:
                    st.warning("성함과 소속팀을 입력해야 명예의 전당에 오를 수 있습니다!")

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
                                    let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    nativeInputValueSetter.call(hiddenInput, finalTime);

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
                        setInterval(() => {{
                            if (sessionStorage.getItem('p114StartTime')) {{
                                let start = parseInt(sessionStorage.getItem('p114StartTime'));
                                let elapsed = (Date.now() - start) / 1000;
                                timerDisplay.innerText = elapsed.toFixed(2);
                            }}
                        }}, 50);
                        setInterval(() => {{
                            try {{
                                const inputBox = parent.document.querySelector('input[aria-label="완벽히 입력하고 Enter를 누르세요"]');
                                if (inputBox) {{
                                    if (parent.document.activeElement !== inputBox) {{ inputBox.focus(); }}

                                    if (!inputBox.dataset.setupDone) {{
                                        const blockEvent = e => {{ e.preventDefault(); alert("⚠️ 꼼수 금지! 직접 치세요."); }};
                                        inputBox.addEventListener('paste', blockEvent);
                                        inputBox.addEventListener('drop', blockEvent);

                                        inputBox.addEventListener('keydown', e => {{
                                            if (e.key !== 'Enter' && e.key !== 'Tab') {{
                                                if (!sessionStorage.getItem('p114StartTime')) {{
                                                    sessionStorage.setItem('p114StartTime', Date.now());
                                                }}
                                            }}
                                        }});
                                        inputBox.dataset.setupDone = "true";
                                    }}
                                }}
                            }} catch(err) {{ }}
                        }}, 100);
                    }}
                </script>
            </body>
            </html>
            """

            components.html(controller_html, height=100)

            if not is_finished:
                cur = P114_STEPS[st.session_state.p_step]
                lines = cur["lines"]
                now = st.session_state.p_line

                st.markdown(f"**{cur['title']}**")

                for li, line_text in enumerate(lines):
                    if li < now:
                        # 이미 정확히 친 줄
                        st.markdown("<div class='p-done'>✅ %s</div>" % _p_esc(line_text),
                                    unsafe_allow_html=True)
                    elif li == now:
                        # 지금 쳐야 하는 줄
                        st.markdown("<div class='p-now'>📝 %s</div>" % _p_esc(line_text),
                                    unsafe_allow_html=True)
                        user_input = st.text_input(
                            "완벽히 입력하고 Enter를 누르세요",
                            key="p_in_%d_%d" % (st.session_state.p_step, li))

                        if user_input:
                            if user_input == line_text:
                                if li + 1 < len(lines):
                                    st.session_state.p_line += 1
                                else:
                                    st.session_state.p_step += 1
                                    st.session_state.p_line = 0
                                st.rerun()
                            else:
                                _show_typo(line_text, user_input)
                    else:
                        # 아직 차례가 오지 않은 줄
                        st.markdown("<div class='p-todo'>%s</div>" % _p_esc(line_text),
                                    unsafe_allow_html=True)

                done_lines = sum(len(s["lines"]) for s in P114_STEPS[:st.session_state.p_step]) + now
                st.progress(done_lines / TOTAL_LINES,
                            text="%d / %d 줄" % (done_lines, TOTAL_LINES))
                st.caption("한 글자도 빠짐없이 그대로 입력하세요. (띄어쓰기·쉼표 포함)")

            else:
                js_time = st.text_input("p_hidden_time", key="p_hidden_time",
                                        label_visibility="collapsed")

                if js_time and 'p_score_saved' not in st.session_state:
                    final_time_float = _p_float(js_time, 0.0)

                    with st.spinner("📡 최종 기록 확인 및 명예의 전당 등록 중... (약 2~3초 소요)"):
                        if save_p114_score(st.session_state.p_name,
                                           st.session_state.p_team,
                                           st.session_state.p_group,
                                           final_time_float):
                            st.session_state.p_score_saved = True
                    st.rerun()

                if 'p_score_saved' in st.session_state:
                    st.balloons()
                    st.markdown(f"""
                    <div class="p-rank-card">
                        <h2>🎉 {st.session_state.p_name}님, 완료를 축하합니다!</h2>
                        <h1 style="color: #2F6FB5;">⏱️ 최종 기록: {js_time}초</h1>
                        <p><b>{st.session_state.p_group}</b> 부문에 기록이 등록되었습니다.</p>
                        <p>114 프로젝트, 이제 손끝으로도 기억하시겠죠?</p>
                    </div>
                    """, unsafe_allow_html=True)

                    st.divider()
                    if st.button("🔄 처음부터 다시 도전하기", key="p_again_btn"):
                        st.session_state.p_is_playing = False
                        st.session_state.p_step = 0
                        st.session_state.p_line = 0
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
