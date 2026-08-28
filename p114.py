from utils import *

# ==========================================================
# ⌨️ 114 프로젝트 타자왕 챌린지 (p114.py)
#   - 핵심가치 타자 릴레이와 똑같은 방식입니다.
#   - 순위는 7개 직급으로 나누어 매깁니다.
#   - DB : 구글 시트 "대한사료_114P Challenge_DB" 의 leaderboard 탭
# ==========================================================

P_DB = "대한사료_114P Challenge_DB"
P_TAB = "leaderboard"
P_HEADERS = ["이름", "소속팀", "직급", "기록(초)", "달성일"]

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


# ==========================================================
# 챌린지에 들어갈 내용 (114 프로젝트)
#   한 단계에 '과제 제목 + 설명'을 한 줄로 묶어 두었습니다.
#   text 안의 글자를 그대로 다 입력해야 다음 단계로 넘어갑니다.
# ==========================================================
P114_STEPS = [
    {"title": "🎯 1단계 : 우리의 목표",
     "text": "판매량 100만톤 매출 1조 영업이익 400억 달성을 향한 5대 핵심과제 114 프로젝트"},
    {"title": "📊 2단계 : 핵심과제 ①",
     "text": "1.통합 경영 운영 체계 및 핵심지표 고도화 부서별 회의체 중점 내용과 데이터를 핵심지표화, "
             "데이터를 연동한 통합경영운영체계 구축"},
    {"title": "🌱 3단계 : 핵심과제 ②",
     "text": "2.성장을 가속화하는 문화 구축 스타 인재들의 원팀 시너지를 바탕으로 "
             "114 프로젝트 달성을 위한 성장중심 조직구현"},
    {"title": "📈 4단계 : 핵심과제 ③",
     "text": "3.영업경쟁력 강화 및 대리점 고도화 축산시장 내 강력한 영업 경쟁력을 갖춘 "
             "지속 성장 가능한 영업 조직 구축"},
    {"title": "🏅 5단계 : 핵심과제 ④",
     "text": "4.고객중심 품질 혁신 고객이 만족하는 품질 전 직원이 함께 만드는 최적의 품질"},
    {"title": "📣 6단계 : 핵심과제 ⑤",
     "text": "5.마케팅팀 구축 사료를 판매하는 회사를 넘어 고객의 수익을 설계하고 증명하는 회사로의 전환"},
]


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

    tab1, tab2 = st.tabs(["🎮 챌린지 시작하기", "🏆 직급별 명예의 전당"])

    # =========================================================
    # 🎮 게임
    # =========================================================
    with tab1:
        if 'p_step' not in st.session_state: st.session_state.p_step = 0
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
            p_group = st.selectbox("직급 (순위는 직급별로 매겨집니다)", RANK_GROUPS, key="p_in_group")

            st.info("💡 **게임 규칙:** 첫 글자를 치는 순간부터 초시계가 작동합니다. "
                    "완료 후 자동으로 커서가 이동하니 키보드에서 손을 떼지 마세요!")

            if st.button("🚀 챌린지 시작하기", type="primary", use_container_width=True,
                         key="p_start_btn"):
                if p_name and p_team:
                    st.session_state.p_name = p_name
                    st.session_state.p_team = p_team
                    st.session_state.p_group = p_group
                    st.session_state.p_is_playing = True
                    st.session_state.p_step = 0
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

                st.markdown(f"**{cur['title']}**")
                st.markdown(f"### 📝 {cur['text']}")
                st.caption("한 글자도 빠짐없이 그대로 입력하세요. (띄어쓰기·마침표 포함)")

                user_input = st.text_input("완벽히 입력하고 Enter를 누르세요",
                                           key=f"p_input_{st.session_state.p_step}")

                if user_input:
                    if user_input == cur['text']:
                        st.session_state.p_step += 1
                        st.rerun()
                    else:
                        st.error("⚠️ 오타가 있습니다! 틀린 부분을 고치고 다시 Enter를 누르세요.")

                st.progress(st.session_state.p_step / len(P114_STEPS),
                            text="%d / %d 단계" % (st.session_state.p_step, len(P114_STEPS)))

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
                        for k in ('p_hidden_time', 'p_score_saved'):
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

    # =========================================================
    # 🏆 직급별 순위
    # =========================================================
    with tab2:
        st.subheader("🏆 직급별 명예의 전당")
        st.caption("순위는 **직급별로 따로** 매겨집니다. 아래에서 보고 싶은 직급을 골라 주세요.")

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
            rows = list(best.values())

            counts = {}
            for r in rows:
                g = str(r.get('직급', '')).strip()
                counts[g] = counts.get(g, 0) + 1

            opts = ["🏅 전체 (%d명)" % len(rows)] + \
                   ["%s (%d명)" % (g, counts.get(g, 0)) for g in RANK_GROUPS]
            pick = st.selectbox("직급 선택", opts, key="p_group_pick")

            if pick == opts[0]:
                shown = rows
                title_txt = "전체"
                limit = 5          # 👈 전체 순위는 5명까지
            else:
                g = RANK_GROUPS[opts.index(pick) - 1]
                shown = [r for r in rows if str(r.get('직급', '')).strip() == g]
                title_txt = g
                limit = 3          # 👈 직급별 순위는 3명까지

            shown = sorted(shown, key=lambda x: _p_float(x.get('기록(초)')))[:limit]

            if not shown:
                st.info("**%s** 부문에는 아직 도전자가 없습니다. 1등의 주인공이 되어 보세요!" % title_txt)
            else:
                st.markdown("#### 🏆 %s 부문 TOP %d" % (title_txt, limit))
                top3 = shown[:3]
                cols = st.columns(3)
                medals = [("🥇 1위", "p-gold"), ("🥈 2위", "p-silver"), ("🥉 3위", "p-bronze")]

                for i in range(min(len(top3), 3)):
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
                                {top3[i].get('이름', '-')}
                            </div>
                            <div style="width: 100%; text-align: center; font-size: 0.95em; color: #64748b; margin-bottom: 4px; font-weight: 500;">
                                {top3[i].get('소속팀', '-')}
                            </div>
                            <div style="width: 100%; text-align: center; font-size: 0.85em; color: #2F6FB5; margin-bottom: 14px; font-weight: 700;">
                                {top3[i].get('직급', '-')}
                            </div>
                            <div style="width: 100%; text-align: center; font-size: 1.8em; font-weight: bold; color: #ff4b4b; background-color: #fff1f1; border-radius: 8px; padding: 5px 0;">
                                {_p_float(top3[i].get('기록(초)'), 0):.2f}초
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                if len(shown) > 3:
                    df = pd.DataFrame(shown[3:limit])
                    df.index = range(4, 4 + len(df))
                    df.index.name = "순위"
                    for c in ['이름', '소속팀', '직급', '기록(초)', '달성일']:
                        if c not in df.columns:
                            df[c] = "-"
                    df = df[['이름', '소속팀', '직급', '기록(초)', '달성일']]
                    df['기록(초)'] = df['기록(초)'].apply(lambda x: f"{_p_float(x, 0):.2f}초")

                    styled_df = df.style.set_properties(**{
                        'text-align': 'center',
                        'font-family': 'sans-serif'
                    }).set_table_styles([
                        {'selector': 'th', 'props': [('text-align', 'center'),
                                                     ('background-color', '#f8f9fa')]}
                    ])
                    st.dataframe(styled_df, use_container_width=True)

            st.markdown("---")
            st.markdown("#### 📊 직급별 참여 현황")
            stat_rows = []
            for g in RANK_GROUPS:
                grp = [r for r in rows if str(r.get('직급', '')).strip() == g]
                grp = sorted(grp, key=lambda x: _p_float(x.get('기록(초)')))
                stat_rows.append({
                    "직급": g,
                    "참여 인원": len(grp),
                    "1위": grp[0].get('이름', '-') if grp else "-",
                    "최고 기록": ("%.2f초" % _p_float(grp[0].get('기록(초)'), 0)) if grp else "-",
                })
            st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)
            st.caption("※ 한 사람이 여러 번 도전한 경우 **가장 빠른 기록**만 순위에 반영됩니다.")
