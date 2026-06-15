from utils import *

def run_typing_game():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox { margin-bottom: 12px !important; }
        .rank-card { border: 2px solid #4CAF50; padding: 15px; border-radius: 10px; background-color: #F9FFF9; text-align: center; margin-bottom: 15px; }
        .gold { color: #D4AF37; font-size: 1.5em; font-weight: bold; }
        .silver { color: #C0C0C0; font-size: 1.3em; font-weight: bold; }
        .bronze { color: #CD7F32; font-size: 1.1em; font-weight: bold; }
        
        /* ✨ 멈춤 해결: 아예 지우지 않고 화면 밖으로 멀리 밀어내어 기능은 100% 살려둡니다! */
        div[data-testid="stTextInput"]:has(input[aria-label="hidden_time"]) {
            position: absolute !important;
            left: -9999px !important;
            opacity: 0 !important;
            height: 0px !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.header("🎯 핵심가치 타자 릴레이")
    st.caption("대한사료의 핵심가치를 가장 빠르고 정확하게 마음에 새긴 주인공은 누구일까요?")
    st.markdown("---")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread_typing():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_핵심가치_DB")

    @st.cache_data(ttl=5, show_spinner=False)
    def get_leaderboard():
        try:
            doc = init_gspread_typing()
            records = doc.worksheet("leaderboard").get_all_records()
            return records
        except:
            return []

    def save_score(name, team, score):
        try:
            doc = init_gspread_typing()
            ws = doc.worksheet("leaderboard")
            
            # 💡 [핵심 수정] 서버 시간이 아닌 '한국 시간(KST)'으로 시계를 맞춥니다.
            # 전 세계 표준시에서 9시간을 더해 한국 시간으로 강제 고정하는 마법입니다.
            import datetime
            kst = datetime.timezone(datetime.timedelta(hours=9))
            today_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
            
            ws.append_row([name, team, score, today_str])
            get_leaderboard.clear() 
            return True
        except Exception as e:
            st.error(f"⚠️ 기록 저장에 실패했습니다. 관리자에게 문의하세요.")
            return False

    tab1, tab2 = st.tabs(["🎮 게임 시작하기", "🏆 실시간 명예의 전당"])

    with tab1:
        if 't_step' not in st.session_state: st.session_state.t_step = 0
        if 't_is_playing' not in st.session_state: st.session_state.t_is_playing = False
        if 't_player_name' not in st.session_state: st.session_state.t_player_name = ""
        if 't_player_team' not in st.session_state: st.session_state.t_player_team = ""

        values_data = [
            {"title": "🌟 1단계: 미션", "text": "인류행복과 생명의 가치를 창조하는 회사"},
            {"title": "🔭 2단계: 비전", "text": "사료에서 식품까지, 글로벌 1조 기업"},
            {"title": "💡 3단계: 핵심가치 [정직]", "text": "기본과 원칙을 준수하며 투명하게 일을 처리한다"},
            {"title": "🔥 4단계: 핵심가치 [열정]", "text": "현재에 안주하지 않고 맡은 일에 최선을 다한다"},
            {"title": "📚 5단계: 핵심가치 [전문성]", "text": "끊임없이 학습을 바탕으로 스스로의 전문성을 갈고 닦는다"},
            {"title": "🤝 6단계: 핵심가치 [협력]", "text": "적극적으로 소통하고 협력하여 시너지를 창출한다"}
        ]

        if not st.session_state.t_is_playing:
            components.html("<script>sessionStorage.removeItem('typingStartTime'); sessionStorage.removeItem('typingEndTime'); sessionStorage.removeItem('scoreSent');</script>", height=0)
            
            st.subheader("도전자 정보 입력")
            c1, c2 = st.columns(2)
            p_name = c1.text_input("성함 (예: 홍길동)")
            p_team = c2.text_input("소속팀 (예: 인사총무팀)")
            
            st.info("💡 **게임 규칙:** 첫 글자를 치는 순간부터 초시계가 작동합니다. 완료 후 자동으로 커서가 이동하니 키보드에서 손을 떼지 마세요!")
            
            if st.button("🚀 게임 시작하기", type="primary", use_container_width=True):
                if p_name and p_team:
                    st.session_state.t_player_name = p_name
                    st.session_state.t_player_team = p_team
                    st.session_state.t_is_playing = True
                    st.session_state.t_step = 0
                    st.rerun()
                else:
                    st.warning("이름과 소속팀을 입력해야 명예의 전당에 오를 수 있습니다!")

        else:
            is_finished = st.session_state.t_step >= len(values_data)
            
            controller_html = f"""
            <html>
            <head>
            <style>
                body {{ margin: 0; font-family: sans-serif; display: flex; justify-content: center; align-items: center; }}
                .timer-box {{ font-size: 1.8rem; font-weight: bold; color: #ff4b4b; }}
                .success-box {{ font-size: 2.5rem; font-weight: bold; color: #4CAF50; }}
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
                        if (!sessionStorage.getItem('typingEndTime')) {{
                            sessionStorage.setItem('typingEndTime', Date.now());
                        }}
                        let start = parseInt(sessionStorage.getItem('typingStartTime') || Date.now());
                        let end = parseInt(sessionStorage.getItem('typingEndTime'));
                        let finalTime = ((end - start) / 1000).toFixed(2);
                        timerDisplay.innerText = finalTime;
                        
                        let attempts = 0;
                        let trySend = setInterval(() => {{
                            const hiddenInput = parent.document.querySelector('input[aria-label="hidden_time"]');
                            if (hiddenInput) {{
                                clearInterval(trySend); 
                                
                                if (!sessionStorage.getItem('scoreSent')) {{
                                    let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    nativeInputValueSetter.call(hiddenInput, finalTime);
                                    
                                    hiddenInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    
                                    // ✨ 스트림릿 서버에 확실히 값을 넘기는 핵심 3단 콤보 (포커스 -> 엔터 -> 블러)
                                    setTimeout(() => {{
                                        hiddenInput.focus();
                                        hiddenInput.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                                        hiddenInput.blur(); 
                                    }}, 100);
                                    
                                    sessionStorage.setItem('scoreSent', 'true');
                                }}
                            }}
                            attempts++;
                            if (attempts > 50) clearInterval(trySend); 
                        }}, 100);

                    }} else {{
                        setInterval(() => {{
                            if (sessionStorage.getItem('typingStartTime')) {{
                                let start = parseInt(sessionStorage.getItem('typingStartTime'));
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
                                                if (!sessionStorage.getItem('typingStartTime')) {{
                                                    sessionStorage.setItem('typingStartTime', Date.now());
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
                current_item = values_data[st.session_state.t_step]
                
                st.markdown(f"**{current_item['title']}**")
                st.markdown(f"### 📝 {current_item['text']}")
                
                user_input = st.text_input("완벽히 입력하고 Enter를 누르세요", key=f"input_{st.session_state.t_step}")
                
                if user_input:
                    if user_input == current_item['text']:
                        st.session_state.t_step += 1
                        st.rerun()
                    else:
                        st.error("⚠️ 오타가 있습니다! 틀린 부분을 고치고 다시 Enter를 누르세요.")
                        
            else:
                js_time = st.text_input("hidden_time", key="hidden_time", label_visibility="collapsed")
                
                if js_time and 'score_saved' not in st.session_state:
                    final_time_float = float(js_time)
                    
                    with st.spinner("📡 최종 기록 확인 및 명예의 전당 등록 중... (약 2~3초 소요)"):
                        if save_score(st.session_state.t_player_name, st.session_state.t_player_team, final_time_float):
                            st.session_state.score_saved = True
                    st.rerun()
                            
                if 'score_saved' in st.session_state:
                    st.balloons()
                    st.markdown(f"""
                    <div class="rank-card">
                        <h2>🎉 {st.session_state.t_player_name}님, 완료를 축하합니다!</h2>
                        <h1 style="color: #E67E22;">⏱️ 최종 기록: {js_time}초</h1>
                        <p>대한사료의 핵심가치를 완벽히 내재화하셨습니다.</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.divider()
                    if st.button("🔄 처음부터 다시 도전하기"):
                        st.session_state.t_is_playing = False
                        st.session_state.t_step = 0
                        if 'hidden_time' in st.session_state: del st.session_state['hidden_time']
                        if 'score_saved' in st.session_state: del st.session_state['score_saved']
                        st.rerun()

    with tab2:
        st.subheader("🏆 타자왕 명예의 전당 (Top 10)")
        if st.button("🔄 순위 새로고침"):
            get_leaderboard.clear()
            st.rerun()
            
        board_data = get_leaderboard()
        
        if not board_data:
            st.info("아직 등록된 기록이 없습니다. 첫 번째 타자왕에 도전하세요!")
        else:
            # 안전하게 float 변환 후 정렬
            try:
                sorted_board = sorted(board_data, key=lambda x: float(x.get('기록(초)', 999)))
            except:
                sorted_board = board_data
                
            top3 = sorted_board[:3]
            c1, c2, c3 = st.columns(3)
            medals = [("🥇 1위", "gold"), ("🥈 2위", "silver"), ("🥉 3위", "bronze")]
            cols = [c1, c2, c3]
            
            for i in range(min(len(top3), 3)):
                with cols[i]:
                    # 💡 [해결 1] Flexbox 속성을 추가하여 이름/부서/기록을 한 치의 오차 없이 완벽한 가운데 정렬로 맞춥니다.
                    st.markdown(f"""
                    <div style="border: 1px solid #e0e0e0; padding: 20px; border-radius: 12px; background-color: #ffffff; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <div class="{medals[i][1]}" style="margin-bottom: 8px;">{medals[i][0]}</div>
                        <h3 style="margin: 0; font-weight: bold; color: #2c3e50;">{top3[i].get('이름', '-')}</h3>
                        <p style="color: #7f8c8d; margin: 5px 0 15px 0; font-size: 0.9em;">{top3[i].get('소속팀', '-')}</p>
                        <h3 style="color: #e74c3c; margin: 0;">{float(top3[i].get('기록(초)', 0)):.2f}초</h3>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if len(sorted_board) > 3:
                # 4위부터 10위까지 데이터프레임 생성
                df = pd.DataFrame(sorted_board[3:10])
                df.index = range(4, 4 + len(df))
                df.index.name = "순위"
                
                # 필요한 열만 추출
                df = df[['이름', '소속팀', '기록(초)', '달성일']]
                
                # 💡 [해결 3] 기록(초)를 문자열("OO.OO초")로 변환합니다. 
                # 이렇게 하면 숫자가 우측으로 쏠려서 달성일과 합쳐져 보이는 착시(오류) 현상이 완벽히 사라집니다.
                df['기록(초)'] = df['기록(초)'].apply(lambda x: f"{float(x):.2f}초")
                
                # 💡 [해결 2] Pandas Styler를 사용해 표의 내용(셀)과 제목(헤더)을 모두 예쁘게 가운데 정렬합니다.
                styled_df = df.style.set_properties(**{'text-align': 'center'}) \
                                    .set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
                
                st.dataframe(styled_df, use_container_width=True)
