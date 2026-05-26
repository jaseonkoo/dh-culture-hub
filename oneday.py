from utils import *

def run_class():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .class-card { border: 2px solid #F39C12; padding: 20px; border-radius: 12px; background-color: #FFF9F0; margin-bottom: 15px; }
        .my-res-card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background-color: #f9f9f9; margin-bottom: 10px; }
        </style>
    """, unsafe_allow_html=True)

    st.header("🎓 직무 원데이 클래스")
    st.caption("사내 전문가에게 직접 배우는 실무 노하우, 함께 성장하는 직무 교육 플랫폼")
    st.markdown("---")

    if "c_admin_logged_in" not in st.session_state: st.session_state.c_admin_logged_in = False
    def reset_pw_c2():
        if "c_pw_t2" in st.session_state: st.session_state["c_pw_t2"] = ""

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread_class():
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
            client = gspread.authorize(creds)
            return client.open("대한사료_원데이클래스_DB")
        except Exception as e:
            st.error(f"❌ 구글 시트 파일을 열 수 없습니다: {e}")
            return None

    @st.cache_data(ttl=60, show_spinner=False)
    def get_sheet_data_class(sheet_name):
        try: 
            doc = init_gspread_class()
            if doc: return doc.worksheet(sheet_name).get_all_records()
            return []
        except Exception as e:
            st.error(f"⚠️ '{sheet_name}' 탭을 읽는 중 오류 발생: {e}")
            return []

    def fetch_latest_data_class(force=False):
        if force: st.cache_data.clear()
        try:
            st.session_state.classes_data = get_sheet_data_class("classes")
            st.session_state.c_reservations = get_sheet_data_class("applications")
            st.session_state.instructors_data = get_sheet_data_class("instructors")
            ad_list = get_sheet_data_class("admin")
            st.session_state.c_admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}
        except Exception as e:
            st.error(f"⚠️ 데이터 초기화 중 오류: {e}")

    fetch_latest_data_class()

    def safe_save_class(ws_name, data_list):
        try:
            doc = init_gspread_class(); ws = doc.worksheet(ws_name); ws.clear()
            if data_list:
                df = pd.DataFrame(data_list)
                df = df.fillna("")
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data_class(force=True)
            return True
        except: 
            st.error("⚠️ 데이터 저장 오류")
            return False

    instructor_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('instructors_data', [])]

    tab1, tab2, tab3 = st.tabs(["📖 수강 신청", "👨‍🏫 강사 전용 (개설/관리)", "👑 관리자 메뉴"])

    with tab1:
        sub_tab_apply, sub_tab_cancel = st.tabs(["✨ 신규 수강 신청", "🔍 내 신청 확인/취소"])

        with sub_tab_apply:
            st.subheader("📚 모집 중인 클래스")
            active_classes = [c for c in st.session_state.get('classes_data', []) if c.get('status') == '모집중']
            
            if not active_classes:
                st.info("현재 모집 중인 클래스가 없습니다.")
            else:
                for c in active_classes:
                    with st.container():
                        current_apps = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == c['id']]
                        count = len(current_apps)
                        capa = int(c['capacity'])
                        
                        st.markdown(f"""
                        <div class="class-card">
                            <h3 style="color: #E67E22; margin-top:0;">{c['title']}</h3>
                            <p>👤 <b>강사:</b> {c['instructor']} | 📅 <b>일시:</b> {c['date']} {c['time']}<br>
                            📍 <b>장소:</b> {c['location']} | 👥 <b>정원:</b> {count}/{capa}명</p>
                            <p style="font-size: 0.9em; color: #666;">{c['description']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if count >= capa:
                            st.warning("⚠️ 정원이 초과되었습니다. (마감)")
                        else:
                            with st.expander(f"🙋‍♂️ '{c['title']}' 수강 신청하기"):
                                with st.form(key=f"form_{c['id']}"):
                                    c1, c2 = st.columns(2)
                                    u_n = c1.text_input("성함"); u_p = c1.text_input("직급")
                                    u_t = c2.text_input("팀명"); u_e = c2.text_input("사내 이메일")
                                    
                                    if st.form_submit_button("신청서 제출"):
                                        if u_n and is_company_email(u_e):
                                            is_dup = any(a['class_id'] == c['id'] and a['user_email'] == u_e for a in st.session_state.c_reservations)
                                            if is_dup:
                                                st.error("이미 신청하신 클래스입니다.")
                                            else:
                                                new_app = {
                                                    "id": str(uuid.uuid4())[:8], "class_id": c['id'], "class_title": c['title'],
                                                    "user_name": u_n, "user_pos": u_p, "user_team": u_t, "user_email": u_e, "status": "신청완료"
                                                }
                                                st.session_state.c_reservations.append(new_app)
                                                if safe_save_class("applications", st.session_state.c_reservations):
                                                    st.balloons(); st.success("신청이 완료되었습니다!"); time.sleep(1.5); st.rerun()
                                        else:
                                            st.error("정보를 정확히 입력해 주세요.")

        with sub_tab_cancel:
            st.subheader("🔍 내 신청 내역 조회")
            search_email = st.text_input("신청 시 입력했던 이메일을 입력하세요", placeholder="example@daehanfeed.co.kr")
            
            if search_email:
                my_apps = [a for a in st.session_state.get('c_reservations', []) if a['user_email'].strip().lower() == search_email.strip().lower()]
                if not my_apps:
                    st.warning("해당 이메일로 신청된 내역이 없습니다.")
                else:
                    st.info(f"총 {len(my_apps)}건의 신청 내역이 있습니다.")
                    for a in my_apps:
                        with st.container():
                            st.markdown(f"""
                            <div class="my-res-card">
                                <b>📌 클래스명:</b> {a['class_title']}<br>
                                👤 <b>신청자:</b> {a['user_name']} ({a['user_pos']})<br>
                                ⏳ <b>상태:</b> {a['status']}
                            </div>
                            """, unsafe_allow_html=True)
                            if st.button("❌ 신청 취소하기", key=f"cancel_{a['id']}"):
                                st.session_state.c_reservations.remove(a)
                                if safe_save_class("applications", st.session_state.c_reservations):
                                    st.success(f"'{a['class_title']}' 신청이 취소되었습니다."); time.sleep(1.5); st.rerun()

    with tab2:
        st.subheader("🔒 강사 전용 클래스 관리")
        c_log = st.selectbox("본인 성함 선택", instructor_names, key="c_log_t2", on_change=reset_pw_c2)
        if c_log != "선택해주세요":
            minfo = next((m for m in st.session_state.get('instructors_data', []) if m['name']==c_log), None)
            if minfo and st.text_input("비밀번호 입력", type="password", key="c_pw_t2") == str(minfo['pw']):
                mode = st.radio("작업 선택", ["신규 클래스 오픈하기", "내 클래스 신청자 명단 보기"], horizontal=True)
                
                if mode == "신규 클래스 오픈하기":
                    with st.form("new_class_form"):
                        title = st.text_input("강의명 (예: 실무 엑셀 마스터)"); st.info(f"👨‍🏫 강사: **{c_log}**")
                        c1, c2 = st.columns(2); d_val = c1.date_input("강의 날짜")
                        t1, t2 = c1.columns(2); start_time = t1.time_input("시작 시간", datetime.time(14, 0)); end_time = t2.time_input("종료 시간", datetime.time(16, 0))
                        loc = c2.text_input("장소"); capa = c2.number_input("모집 정원", min_value=1, value=15)
                        desc = st.text_area("설명 및 준비물")
                        
                        if st.form_submit_button("클래스 오픈하기"):
                            if not title: st.error("⚠️ 강의명을 입력해 주세요!")
                            elif start_time >= end_time: st.error("⚠️ 종료 시간은 시작 시간보다 늦어야 합니다.")
                            else:
                                with st.status("📡 개설 중..."):
                                    t_val = f"{start_time.strftime('%H:%M')} ~ {end_time.strftime('%H:%M')}"
                                    new_class = {
                                        "id": str(uuid.uuid4())[:8], "title": title, "instructor": c_log, "date": str(d_val), "time": t_val,
                                        "location": loc, "capacity": capa, "description": desc, "status": "모집중"
                                    }
                                    st.session_state.classes_data.append(new_class)
                                    safe_save_class("classes", st.session_state.classes_data)
                                st.balloons(); st.success("오픈되었습니다!"); time.sleep(1.5); st.rerun()
                else:
                    my_classes = [c for c in st.session_state.get('classes_data', []) if c['instructor'] == c_log]
                    if not my_classes: st.info("개설 내역이 없습니다.")
                    else:
                        sel_class = st.selectbox("확인할 클래스 선택", [c['title'] for c in my_classes])
                        target_class = next(c for c in my_classes if c['title'] == sel_class)
                        applicants = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == target_class['id']]
                        st.write(f"### 📋 신청자 리스트 ({len(applicants)}명)")
                        if applicants:
                            df_app = pd.DataFrame(applicants)[['user_name', 'user_pos', 'user_team', 'user_email']]
                            df_app.columns = ['성함', '직급', '소속팀', '이메일']
                            st.dataframe(df_app, use_container_width=True)
                        else: st.info("신청자가 없습니다.")

    with tab3:
        st.subheader("👑 원데이 클래스 통합 관리 시스템")
        if not st.session_state.c_admin_logged_in:
            aid, apw = st.text_input("ID", key="c_ad_id"), st.text_input("PW", type="password", key="c_ad_pw")
            if st.button("로그인", key="c_login_btn") and aid == st.session_state.c_admin_info['id'] and apw == str(st.session_state.c_admin_info['pw']):
                st.session_state.c_admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃", key="c_logout_btn"): st.session_state.c_admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 강사 신규 등록"):
                r1, r2, r3, r4 = st.columns(4); nm = r1.text_input("성함",key="c_n1"); np = r2.text_input("직급",key="c_n2"); nt = r3.text_input("팀명",key="c_n3"); n_pw = r4.text_input("초기 비번",key="c_n4")
                ne = st.text_input("사내 이메일",key="c_n5")
                if st.button("강사 등록", key="c_reg_btn") and is_company_email(ne):
                    st.session_state.instructors_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "email":ne})
                    safe_save_class("instructors", st.session_state.instructors_data); st.success("등록됨"); st.rerun()

            with st.expander("📋 등록된 강사 현황 및 관리", expanded=True):
                instructors = st.session_state.get('instructors_data', [])
                if not instructors: st.info("현재 등록된 사내 강사가 없습니다.")
                else:
                    for i, m in enumerate(instructors):
                        st.markdown(f"#### 👤 {m['name']} 강사님")
                        er1, er2, er3, er4 = st.columns(4)
                        un = er1.text_input("성함", m['name'], key=f"c_un_{i}"); up = er2.text_input("직급", m.get('position',''), key=f"c_up_{i}")
                        ut = er3.text_input("팀명", m.get('team',''), key=f"c_ut_{i}"); upw = er4.text_input("비번", m.get('pw',''), key=f"c_upw_{i}")
                        ue = st.text_input("사내 이메일", m.get('email',''), key=f"c_ue_{i}")
                        col_btn1, col_btn2 = st.columns(2)
                        if col_btn1.button("💾 정보 수정", key=f"c_sv_{i}", use_container_width=True):
                            if is_company_email(ue):
                                st.session_state.instructors_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue})
                                safe_save_class("instructors", st.session_state.instructors_data); st.success("수정 완료!"); st.rerun()
                            else: st.error("이메일 형식을 확인해주세요.")
                        if col_btn2.button("❌ 강사 권한 삭제", key=f"c_dl_{i}", use_container_width=True):
                            st.session_state.instructors_data.pop(i)
                            safe_save_class("instructors", st.session_state.instructors_data); st.rerun()
                        st.divider()

            with st.expander("📚 전체 클래스 및 신청 명단", expanded=False):
                for i, c in enumerate(st.session_state.get('classes_data', [])):
                    current_apps = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == c['id']]
                    col_info, col_btn1, col_btn2 = st.columns([3, 1, 1])
                    col_info.markdown(f"**[{c['status']}] {c['title']}** (신청: {len(current_apps)}/{c['capacity']}명)")
                    if col_btn1.button("상태 전환", key=f"c_tog_{i}"):
                        c['status'] = '마감' if c['status'] == '모집중' else '모집중'
                        safe_save_class("classes", st.session_state.classes_data); st.rerun()
                    if col_btn2.button("삭제", key=f"c_del_{i}"):
                        st.session_state.classes_data.pop(i)
                        safe_save_class("classes", st.session_state.classes_data); st.rerun()
                    if current_apps:
                        df_adm = pd.DataFrame(current_apps)[['user_name', 'user_pos', 'user_team', 'user_email']]
                        st.dataframe(df_adm, use_container_width=True)
                    st.markdown("---")
