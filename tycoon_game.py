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
 
    # =========================================================
    #  1) 로그인 게이트 — 로그인 전에는 게임을 보여주지 않음
    # =========================================================
    if "member" not in st.session_state:
        st.markdown("""
            <div class="login-hero">
                <h3>🔐 로그인</h3>
                <p>사번과 이름을 입력해 주세요. (인사 등록 정보와 일치해야 입장할 수 있습니다.)</p>
            </div>
        """, unsafe_allow_html=True)
 
        with st.form("tycoon_login_form", clear_on_submit=False):
            in_saban = st.text_input("사번", placeholder="예: 119204001")
            in_name = st.text_input("이름", placeholder="예: 홍길동")
            submitted = st.form_submit_button("로그인", use_container_width=True)
 
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
    col_hi, col_out = st.columns([5, 1])
    with col_hi:
        pos = f" · {member['position']}" if member.get("position") else ""
        st.success(f"👤 {member['name']}님 ({member['team']}{pos}) 로그인됨")
    with col_out:
        if st.button("로그아웃", use_container_width=True):
            for k in ["member", "hidden_tycoon_data", "tycoon_score_saved"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
 
    tab1, tab2 = st.tabs(["🎮 게임 플레이", "🏆 실시간 명예의 전당"])
 
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
            if st.button("🔄 게임 초기화 (다시 하기)"):
                for k in ['hidden_tycoon_data', 'tycoon_score_saved']:
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
