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
    
    @st.cache_resource
    def init_gspread_tycoon():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_타이쿤_DB")

    @st.cache_data(ttl=5, show_spinner=False)
    def get_tycoon_leaderboard():
        try:
            doc = init_gspread_tycoon()
            records = doc.worksheet("leaderboard").get_all_records()
            return records
        except:
            return []

    def save_tycoon_score(name, team, profit):
        try:
            doc = init_gspread_tycoon()
            ws = doc.worksheet("leaderboard")
            kst = datetime.timezone(datetime.timedelta(hours=9))
            today_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
            ws.append_row([name, team, profit, today_str])
            get_tycoon_leaderboard.clear() 
            return True
        except Exception as e:
            return False

    tab1, tab2 = st.tabs(["🎮 게임 플레이", "🏆 실시간 명예의 전당"])

    with tab1:
        # 💡 코드를 직접 넣지 않고 원본 HTML 파일을 통째로 불러옵니다!
        try:
            with open("daehan_feed_tycoon_23.html", "r", encoding="utf-8") as f:
                original_html = f.read()
            
            # HTML 화면 띄우기 (효과가 잘 보이도록 높이를 900으로 넉넉히 줍니다)
            components.html(original_html, height=900, scrolling=True)
        except Exception as e:
            st.error(f"HTML 파일을 찾을 수 없습니다: {e}")

        # [핵심] 자바스크립트가 보내는 순이익 데이터를 몰래 받아주는 투명한 박스
        js_data = st.text_input("hidden_tycoon_data", key="hidden_tycoon_data", label_visibility="collapsed")
        
        if js_data and 'tycoon_score_saved' not in st.session_state:
            try:
                data = json.loads(js_data)
                with st.spinner("📡 최종 경영 실적을 명예의 전당에 등록 중입니다..."):
                    if save_tycoon_score(data['name'], data['team'], data['profit']):
                        st.session_state.tycoon_score_saved = True
                        st.balloons()
                st.rerun()
            except Exception as e:
                pass
                
        if 'tycoon_score_saved' in st.session_state:
            st.success("✅ 실적이 성공적으로 명예의 전당에 등록되었습니다! [실시간 명예의 전당] 탭을 확인해보세요.")
            if st.button("🔄 게임 초기화 (다시 하기)"):
                del st.session_state['hidden_tycoon_data']
                del st.session_state['tycoon_score_saved']
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
                sorted_board = sorted(board_data, key=lambda x: int(str(x.get('순이익(원)', 0)).replace(',','')), reverse=True)
            except:
                sorted_board = board_data
                
            top3 = sorted_board[:3]
            c1, c2, c3 = st.columns(3)
            medals = [("🥇 1위", "gold"), ("🥈 2위", "silver"), ("🥉 3위", "bronze")]
            cols = [c1, c2, c3]
            
            for i in range(min(len(top3), 3)):
                profit_str = format(int(top3[i].get('순이익(원)', 0)), ',')
                with cols[i]:
                    st.markdown(f"""
                    <div style="border: 2px solid #efefef; padding: 25px 10px; border-radius: 15px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.08); text-align: center; display: block; width: 100%;">
                        <div class="{medals[i][1]}" style="width: 100%; text-align: center; margin-bottom: 12px;">{medals[i][0]}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.6em; font-weight: 800; color: #1e293b; margin-bottom: 4px;">{top3[i].get('이름', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.0em; color: #64748b; margin-bottom: 15px; font-weight: 500;">{top3[i].get('소속팀', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.5em; font-weight: bold; color: #4CAF50; background-color: #E8F5E9; border-radius: 8px; padding: 5px 0;">+{profit_str}원</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if len(sorted_board) > 3:
                df = pd.DataFrame(sorted_board[3:10])
                df.index = range(4, 4 + len(df))
                df.index.name = "순위"
                df = df[['이름', '소속팀', '순이익(원)', '달성일']]
                
                # 금액에 콤마 포맷 적용
                df['순이익(원)'] = df['순이익(원)'].apply(lambda x: f"{format(int(str(x).replace(',','')), ',')}원")
                
                styled_df = df.style.set_properties(**{
                    'text-align': 'center', 'font-family': 'sans-serif'
                }).set_table_styles([
                    {'selector': 'th', 'props': [('text-align', 'center'), ('background-color', '#f8f9fa')]}
                ])
                st.dataframe(styled_df, use_container_width=True)
