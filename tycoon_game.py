import streamlit as st
import pandas as pd
import gspread
import datetime
import json
import streamlit.components.v1 as components
from oauth2client.service_account import ServiceAccountCredentials


def run_tycoon_game():
    st.markdown("""
        <style>
        .rank-card { border: 2px solid #4CAF50; padding: 15px; border-radius: 10px; background-color: #F9FFF9; text-align: center; margin-bottom: 15px; }
        .gold { color: #D4AF37; font-size: 1.5em; font-weight: bold; }
        .silver { color: #C0C0C0; font-size: 1.3em; font-weight: bold; }
        .bronze { color: #CD7F32; font-size: 1.1em; font-weight: bold; }

        /* 로그인 카드 */
        .login-hero { border: 2px solid #4CAF50; border-radius: 16px; background: #F9FFF9;
            padding: 22px 24px; margin: 6px 0 18px; }
        .login-hero h3 { margin: 0 0 4px; color: #3F7D34; }
        .login-hero p { margin: 0; color: #64748b; font-size: 0.92em; }

        /* 로그인 상태 바 — 로그아웃 버튼과 높이·수직 정렬을 정확히 일치시킴 */
        .login-bar { display: flex; align-items: center; gap: 8px;
            height: 44px; min-height: 44px; box-sizing: border-box; margin: 0;
            background: #E8F5E9; border: 1px solid #A5D6A7; border-left: 5px solid #4CAF50;
            border-radius: 8px; padding: 0 16px; color: #1B5E20; font-weight: 600;
            font-size: 0.95em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        /* 버튼·입력칸 높이를 44px 로 통일 (Streamlit 버전과 무관하게 적용되는 선택자) */
        div[data-testid="stButton"] button,
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stFormSubmitButton"] button {
            height: 44px; min-height: 44px; box-sizing: border-box; margin: 0;
            display: inline-flex; align-items: center; justify-content: center; }
        /* 입력칸은 '테두리가 그려지는 래퍼'의 높이를 맞춰야 버튼과 정확히 같아집니다 */
        div[data-testid="stTextInput"] div:has(> input) {
            height: 44px; min-height: 44px; box-sizing: border-box; }
        div[data-testid="stTextInput"] input {
            height: 100%; box-sizing: border-box; }

        /* 의견(베타 피드백) 안내 카드 */
        .fb-hero { border: 2px dashed #A5D6A7; border-radius: 14px; background: #F9FFF9;
            padding: 16px 20px; margin: 16px 0 12px; }
        .fb-hero h4 { margin: 0 0 4px; color: #3F7D34; font-size: 1.05em; }
        .fb-hero p { margin: 0; color: #64748b; font-size: 0.9em; }
        /* 마크다운 컨테이너의 음수 여백(-16px) 때문에 바의 레이아웃 높이가 줄어드는 것을 방지 */
        div[data-testid="stMarkdownContainer"]:has(.login-bar) { margin: 0 !important; padding: 0 !important; }

        /* 스트림릿과 통신하기 위한 숨겨진 입력창 */
        div[data-testid="stTextInput"]:has(input[aria-label="hidden_tycoon_data"]) {
            position: absolute !important; left: -9999px !important; opacity: 0 !important; height: 0px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.header("🌾 대한사료 밸류체인 타이쿤 (Beta)")
    st.caption("원료 구매부터 농장 배송까지! 최고의 순이익을 달성해 보세요.")
    st.markdown("---")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

    # 관리자 비밀번호 — secrets.toml 에 tycoon_admin_password = "..." 를 넣으면 그 값이 우선 적용됩니다.
    try:
        ADMIN_PW = st.secrets.get("tycoon_admin_password", "dhfeed1947")
    except Exception:
        ADMIN_PW = "dhfeed1947"

    # =========================================================
    #  구글시트 연결 (서비스 계정 1개로 여러 파일을 함께 사용)
    #  - 로그인 정보 파일 : 대한사료_Members_DB  (읽기 전용)
    #  - 게임 기록 파일   : 대한사료_타이쿤_DB   (기록 누적)
    #  ※ 두 파일 모두 서비스 계정 이메일에 '공유'되어 있어야 합니다.
    # =========================================================
    @st.cache_resource
    def get_gspread_client():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        return gspread.authorize(creds)

    @st.cache_resource
    def open_members_db():
        # 로그인(인적정보) 대표 파일
        return get_gspread_client().open("대한사료_Members_DB")

    @st.cache_resource
    def open_tycoon_db():
        # 게임 기록 누적 파일
        return get_gspread_client().open("대한사료_타이쿤_DB")

    # ---------- 로그인(인적정보) ----------
    @st.cache_data(ttl=300, show_spinner=False)
    def get_members():
        try:
            ws = open_members_db().sheet1  # 첫 번째 시트: saban, name, team, gubun, position
            return ws.get_all_records()
        except Exception:
            return []

    def verify_login(saban, name):
        """사번 + 이름이 모두 일치하는 직원 1명을 찾아 반환. 없으면 None."""
        s = str(saban).strip()
        n = str(name).strip()
        if not s or not n:
            return None
        for m in get_members():
            if str(m.get("saban", "")).strip() == s and str(m.get("name", "")).strip() == n:
                return {
                    "saban": str(m.get("saban", "")).strip(),
                    "name": str(m.get("name", "")).strip(),
                    "team": str(m.get("team", "")).strip(),
                    "gubun": str(m.get("gubun", "")).strip(),
                    "position": str(m.get("position", "")).strip(),
                }
        return None

    # ---------- 게임 기록 ----------
    @st.cache_data(ttl=5, show_spinner=False)
    def get_tycoon_leaderboard():
        try:
            doc = open_tycoon_db()
            records = doc.worksheet("leaderboard").get_all_records()
            return records
        except Exception:
            return []

    def save_tycoon_score(saban, name, team, profit):
        try:
            ws = open_tycoon_db().worksheet("leaderboard")
            kst = datetime.timezone(datetime.timedelta(hours=9))
            today_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
            # 열 순서: 이름, 소속팀, 순이익(원), 달성일, 사번
            ws.append_row([name, team, int(profit), today_str, str(saban)])
            get_tycoon_leaderboard.clear()
            return True
        except Exception:
            return False

    # ---------- 참여자 의견(베타 피드백) ----------
    FEEDBACK_HEADER = ["사번", "이름", "소속팀", "만족도", "소감", "개선점", "작성일"]

    def _feedback_ws():
        """feedback 시트를 가져오고, 없으면 머리글과 함께 자동으로 만듭니다."""
        doc = open_tycoon_db()
        try:
            return doc.worksheet("feedback")
        except Exception:
            ws = doc.add_worksheet(title="feedback", rows=2000, cols=len(FEEDBACK_HEADER))
            ws.append_row(FEEDBACK_HEADER)
            return ws

    @st.cache_data(ttl=5, show_spinner=False)
    def get_feedback():
        try:
            return _feedback_ws().get_all_records()
        except Exception:
            return []

    def save_feedback(saban, name, team, rating, impression, improvement):
        try:
            ws = _feedback_ws()
            kst = datetime.timezone(datetime.timedelta(hours=9))
            now_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
            ws.append_row([str(saban), name, team, int(rating),
                           impression.strip(), improvement.strip(), now_str])
            get_feedback.clear()
            return True
        except Exception:
            return False

    def stars(v):
        try:
            n = max(1, min(5, int(str(v).strip())))
            return "⭐" * n
        except Exception:
            return "-"

    # =========================================================
    #  1) 로그인 게이트 — 로그인 전에는 게임을 보여주지 않음
    # =========================================================
    if "member" not in st.session_state:
        st.markdown("""
            <div class="login-hero">
                <h3>🔐 로그인</h3>
                <p>사번과 이름을 입력해 주세요. </p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("tycoon_login_form", clear_on_submit=False):
            # 사번 · 이름 · 로그인 버튼을 같은 너비(1:1:1)로 한 줄에 배치
            try:
                c_saban, c_name, c_btn = st.columns(3, vertical_alignment="center")
            except TypeError:
                c_saban, c_name, c_btn = st.columns(3)
            with c_saban:
                in_saban = st.text_input("사번", placeholder="사번 입력",
                                         label_visibility="collapsed")
            with c_name:
                in_name = st.text_input("이름", placeholder="이름 입력",
                                        label_visibility="collapsed")
            with c_btn:
                submitted = st.form_submit_button("로그인", use_container_width=True,
                                                  type="primary")

        if submitted:
            member = verify_login(in_saban, in_name)
            if member:
                st.session_state.member = member
                st.rerun()
            else:
                st.error("사번 또는 이름이 일치하지 않습니다. 다시 확인해 주세요.")

        st.info("사번은 등록되어 있는데 로그인이 안 된다면, 최근에 명단이 추가되어 잠시 반영이 늦을 수 있습니다. 잠시 후 다시 시도해 주세요.")
        return  # 로그인 전에는 여기서 종료

    # =========================================================
    #  로그인 완료 — 인사말 + 로그아웃
    # =========================================================
    member = st.session_state.member
    try:
        # 인사말 바와 로그아웃 버튼의 수직 중앙 정렬
        col_hi, col_out = st.columns([5, 1], vertical_alignment="center")
    except TypeError:
        # 구버전 Streamlit 호환 (vertical_alignment 미지원)
        col_hi, col_out = st.columns([5, 1])
    with col_hi:
        pos = f" · {member['position']}" if member.get("position") else ""
        st.markdown(
            f'<div class="login-bar"><span>👤</span>'
            f'<span><b>{member["name"]}</b>님 ({member["team"]}{pos}) 로그인됨</span></div>',
            unsafe_allow_html=True,
        )
    with col_out:
        if st.button("로그아웃", key="tycoon_logout", use_container_width=True):
            for k in ["member", "hidden_tycoon_data", "tycoon_score_saved",
                      "tycoon_feedback_saved", "tycoon_admin_ok"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["🎮 게임 플레이", "🏆 실시간 명예의 전당", "🔒 관리자"])

    with tab1:
        # 원본 HTML을 통째로 불러온 뒤, 로그인한 사람의 이름·팀을 게임에 자동 주입합니다.
        try:
            with open("feedtycoon_game.html", "r", encoding="utf-8") as f:
                original_html = f.read()

            # 로그인 정보를 게임 인트로에 주입 (이름·팀 자동 입력 + 입력칸 숨김)
            inject = """
<script>
(function(){
  try{
    var NAME = %s, TEAM = %s;
    function apply(){
      var t=document.getElementById('teamName');
      var p=document.getElementById('playerName');
      if(t){ t.value=TEAM; }
      if(p){ p.value=NAME; }
      var entry=document.querySelector('.entry');
      if(entry){ entry.style.display='none'; }  // 로그인으로 이미 확인됨 → 입력칸 숨김
    }
    if(document.readyState!=='loading'){ apply(); }
    else{ document.addEventListener('DOMContentLoaded', apply); }
  }catch(e){}
})();
</script>
""" % (json.dumps(member.get("name", "")), json.dumps(member.get("team", "")))

            original_html = original_html.replace("</body>", inject + "</body>")

            components.html(original_html, height=900, scrolling=True)
        except Exception as e:
            st.error(f"HTML 파일을 찾을 수 없습니다: {e}")

        # 자바스크립트가 보내는 순이익 데이터를 받는 투명한 박스
        js_data = st.text_input("hidden_tycoon_data", key="hidden_tycoon_data", label_visibility="collapsed")

        if js_data and 'tycoon_score_saved' not in st.session_state:
            try:
                data = json.loads(js_data)
                with st.spinner("📡 최종 경영 실적을 명예의 전당에 등록 중입니다..."):
                    # 신원(사번·이름·팀)은 로그인 정보에서 가져오고, 순이익만 게임에서 받습니다.
                    if save_tycoon_score(member.get("saban"), member.get("name"),
                                         member.get("team"), data.get("profit", 0)):
                        st.session_state.tycoon_score_saved = True
                        st.balloons()
                st.rerun()
            except Exception:
                pass

        if 'tycoon_score_saved' in st.session_state:
            st.success("✅ 실적이 성공적으로 명예의 전당에 등록되었습니다! [실시간 명예의 전당] 탭을 확인해보세요.")

            # ---------- 게임 종료 후 의견 남기기 ----------
            if 'tycoon_feedback_saved' not in st.session_state:
                st.markdown("""
                    <div class="fb-hero">
                        <h4>💬 베타 테스트 의견을 들려주세요</h4>
                        <p>남겨주신 의견은 관리자만 열람하며, 게임 개선에만 활용됩니다.</p>
                    </div>
                """, unsafe_allow_html=True)

                with st.form("tycoon_feedback_form"):
                    rating = st.radio("만족도", [1, 2, 3, 4, 5], index=3, horizontal=True,
                                      format_func=lambda x: "⭐" * x)
                    impression = st.text_area(
                        "소감",
                        placeholder="게임을 해보니 어떠셨나요? (재미, 난이도, 사료 밸류체인 이해에 도움이 되었는지 등)",
                        height=110)
                    improvement = st.text_area(
                        "개선점",
                        placeholder="불편했던 점이나 추가되면 좋을 기능을 자유롭게 적어주세요.",
                        height=110)
                    fb_submitted = st.form_submit_button("의견 제출", use_container_width=True)

                if fb_submitted:
                    if not impression.strip() and not improvement.strip():
                        st.warning("소감과 개선점 중 최소 한 가지는 입력해 주세요.")
                    else:
                        with st.spinner("의견을 저장하는 중입니다..."):
                            saved = save_feedback(member.get("saban"), member.get("name"),
                                                  member.get("team"), rating, impression, improvement)
                        if saved:
                            st.session_state.tycoon_feedback_saved = True
                            st.rerun()
                        else:
                            st.error("의견 저장에 실패했습니다. 잠시 후 다시 시도해 주세요.")
            else:
                st.info("💬 소중한 의견 감사합니다! 베타 개선에 반영하겠습니다.")

            if st.button("🔄 게임 초기화 (다시 하기)"):
                for k in ['hidden_tycoon_data', 'tycoon_score_saved', 'tycoon_feedback_saved']:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

    with tab2:
        st.subheader("🏆 밸류체인 최고 경영자 (Top 10)")
        if st.button("🔄 순위 새로고침"):
            get_tycoon_leaderboard.clear()
            st.rerun()

        board_data = get_tycoon_leaderboard()

        if not board_data:
            st.info("아직 등록된 경영 실적이 없습니다. 첫 번째 최고 경영자에 도전하세요!")
        else:
            try:
                # 순이익이 높은 순서대로 내림차순 정렬
                sorted_board = sorted(board_data, key=lambda x: int(str(x.get('순이익(원)', 0)).replace(',', '')), reverse=True)
            except Exception:
                sorted_board = board_data

            top3 = sorted_board[:3]
            c1, c2, c3 = st.columns(3)
            medals = [("🥇 1위", "gold"), ("🥈 2위", "silver"), ("🥉 3위", "bronze")]
            cols = [c1, c2, c3]

            for i in range(min(len(top3), 3)):
                profit_val = int(str(top3[i].get('순이익(원)', 0)).replace(',', ''))
                profit_str = f"{profit_val:+,}"

                with cols[i]:
                    st.markdown(f"""
                    <div style="border: 2px solid #efefef; padding: 25px 10px; border-radius: 15px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.08); text-align: center; display: block; width: 100%;">
                        <div class="{medals[i][1]}" style="width: 100%; text-align: center; margin-bottom: 12px;">{medals[i][0]}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.6em; font-weight: 800; color: #1e293b; margin-bottom: 4px;">{top3[i].get('이름', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.0em; color: #64748b; margin-bottom: 15px; font-weight: 500;">{top3[i].get('소속팀', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.5em; font-weight: bold; color: #4CAF50; background-color: #E8F5E9; border-radius: 8px; padding: 5px 0;">{profit_str}원</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if len(sorted_board) > 3:
                df = pd.DataFrame(sorted_board[3:10])
                df.index = range(4, 4 + len(df))
                df.index.name = "순위"
                df = df[['이름', '소속팀', '순이익(원)', '달성일']]
                df['순이익(원)'] = df['순이익(원)'].apply(lambda x: f"{int(str(x).replace(',', '')):+,}원")

                styled_df = df.style.set_properties(**{
                    'text-align': 'center', 'font-family': 'sans-serif'
                }).set_table_styles([
                    {'selector': 'th', 'props': [('text-align', 'center'), ('background-color', '#f8f9fa')]}
                ])
                st.dataframe(styled_df, use_container_width=True)

    # =========================================================
    #  관리자 전용 — 참여자 의견 열람 (비밀번호 필요)
    # =========================================================
    with tab3:
        st.subheader("🔒 관리자 — 참여자 의견")

        if not st.session_state.get("tycoon_admin_ok", False):
            st.caption("참여자가 남긴 의견은 관리자만 열람할 수 있습니다.")
            with st.form("tycoon_admin_form"):
                admin_pw = st.text_input("관리자 비밀번호", type="password")
                pw_submitted = st.form_submit_button("확인", use_container_width=True)
            if pw_submitted:
                if admin_pw == ADMIN_PW:
                    st.session_state.tycoon_admin_ok = True
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        else:
            try:
                col_ad, col_lock = st.columns([5, 1], vertical_alignment="center")
            except TypeError:
                col_ad, col_lock = st.columns([5, 1])
            with col_ad:
                st.markdown(
                    '<div class="login-bar"><span>🔓</span>'
                    '<span>관리자 모드 — 열람한 내용은 외부에 공유하지 마세요.</span></div>',
                    unsafe_allow_html=True,
                )
            with col_lock:
                if st.button("잠그기", key="tycoon_admin_lock", use_container_width=True):
                    st.session_state.tycoon_admin_ok = False
                    st.rerun()

            if st.button("🔄 의견 새로고침", key="tycoon_fb_refresh"):
                get_feedback.clear()
                st.rerun()

            fb_data = get_feedback()

            if not fb_data:
                st.info("아직 등록된 의견이 없습니다. 참여자가 게임을 마치고 의견을 남기면 이곳에 표시됩니다.")
            else:
                rating_vals = []
                for r in fb_data:
                    try:
                        rating_vals.append(int(str(r.get("만족도", "")).strip()))
                    except Exception:
                        pass

                m1, m2 = st.columns(2)
                m1.metric("총 응답 수", f"{len(fb_data)}건")
                m2.metric("평균 만족도",
                          f"{sum(rating_vals) / len(rating_vals):.2f} / 5" if rating_vals else "-")

                st.markdown("##### 📝 개별 의견 (최신순)")
                for idx, r in enumerate(reversed(fb_data), start=1):
                    title = (f"{idx}. {r.get('이름', '-')} ({r.get('소속팀', '-')}) · "
                             f"{stars(r.get('만족도'))} · {r.get('작성일', '')}")
                    with st.expander(title):
                        st.markdown(f"**소감**\n\n{r.get('소감', '') or '_(작성 없음)_'}")
                        st.markdown(f"**개선점**\n\n{r.get('개선점', '') or '_(작성 없음)_'}")
                        st.caption(f"사번 {r.get('사번', '-')}")

                df_fb = pd.DataFrame(fb_data)
                for col in FEEDBACK_HEADER:
                    if col not in df_fb.columns:
                        df_fb[col] = ""
                df_fb = df_fb[FEEDBACK_HEADER].iloc[::-1].reset_index(drop=True)
                df_fb.index = range(1, len(df_fb) + 1)
                df_fb.index.name = "No."

                with st.expander("📋 표로 한눈에 보기"):
                    st.dataframe(df_fb, use_container_width=True)

                st.download_button(
                    "⬇️ 의견 전체 CSV 내려받기",
                    data=df_fb.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"타이쿤_참여자의견_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="tycoon_fb_csv",
                )
