from utils import *

# ==========================================================
# 🎓 직무 원데이 클래스 (oneday.py)
#  v2 : 구글 시트가 잠깐 말썽일 때(503 등) 스스로 다시 시도하고,
#       실패를 기억해 두지 않도록 고쳤습니다.
# ==========================================================

SCOPE_C = ["https://spreadsheets.google.com/feeds",
           "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/drive.file",
           "https://www.googleapis.com/auth/drive"]


class ClassBusy(Exception):
    """구글 시트가 잠깐 응답하지 않을 때."""
    pass


def _gs_retry(fn, *a, **kw):
    """구글 시트 호출을 몇 번 다시 시도합니다.
       503(잠시 사용 불가)·429(요청 몰림) 같은 '잠깐 나는 오류'는
       조금 기다렸다 다시 부르면 대부분 됩니다."""
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
            # 네트워크가 잠깐 끊긴 경우도 한 번은 더 해 봅니다.
            last = e
            if i >= 1:
                raise
            time.sleep(1.0)
    raise ClassBusy(str(last))


@st.cache_resource(show_spinner=False)
def init_gspread_class():
    """구글 시트 문서 손잡이.
       ⚠️ 예전에는 실패했을 때 'None'을 돌려주고 그걸 그대로 기억해 버려서,
          한 번 오류가 나면 앱을 다시 켜기 전까지 계속 오류가 났습니다.
          이제는 실패하면 기억하지 않고 다음에 새로 연결합니다."""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], SCOPE_C)
    client = gspread.authorize(creds)
    return _gs_retry(client.open, "대한사료_원데이클래스_DB")


def _reset_class_conn():
    """연결과 읽어 둔 자료를 모두 비웁니다. (다시 시도할 때)"""
    try:
        init_gspread_class.clear()
    except Exception:
        pass
    try:
        get_sheet_data_class.clear()
    except Exception:
        pass


@st.cache_data(ttl=60, show_spinner=False)
def get_sheet_data_class(sheet_name):
    """탭 하나를 읽어 옵니다. 실패하면 기억하지 않고 위로 알립니다."""
    doc = init_gspread_class()
    ws = _gs_retry(doc.worksheet, sheet_name)
    return _gs_retry(ws.get_all_records)


def _to_int_c(v, default=0):
    try:
        return int(str(v).strip())
    except Exception:
        return default


def run_class():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_class()
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        st.markdown("### 🎓 직무 원데이 클래스")
        if code in (429, 500, 502, 503) or isinstance(e, ClassBusy):
            st.warning("⏳ 구글 시트가 잠시 응답하지 않고 있습니다. "
                       "구글 쪽 일시적인 문제라 조금 기다리면 대부분 정상으로 돌아옵니다.\n\n"
                       "**5~10초 뒤 아래 [다시 시도] 버튼을 눌러 주세요.**")
        elif code == 403:
            st.error("구글 시트 접근 권한이 없습니다. "
                     "시트를 서비스 계정 이메일에 **편집자**로 공유했는지 확인해 주세요.")
        else:
            st.error("구글 시트를 여는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:200])
        if st.button("🔄 다시 시도", key="c_retry_btn", type="primary"):
            _reset_class_conn()
            st.rerun()


def _run_class():
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

    if "c_admin_logged_in" not in st.session_state:
        st.session_state.c_admin_logged_in = False

    def reset_pw_c2():
        if "c_pw_t2" in st.session_state:
            st.session_state["c_pw_t2"] = ""

    def fetch_latest_data_class(force=False):
        if force:
            get_sheet_data_class.clear()
        st.session_state.classes_data = get_sheet_data_class("classes")
        st.session_state.c_reservations = get_sheet_data_class("applications")
        st.session_state.instructors_data = get_sheet_data_class("instructors")
        ad_list = get_sheet_data_class("admin")
        st.session_state.c_admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}

    fetch_latest_data_class()

    def safe_save_class(ws_name, data_list):
        try:
            doc = init_gspread_class()
            ws = _gs_retry(doc.worksheet, ws_name)
            _gs_retry(ws.clear)
            if data_list:
                df = pd.DataFrame(data_list).fillna("")
                _gs_retry(ws.update, values=[df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data_class(force=True)
            return True
        except Exception as e:
            st.error("⚠️ 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:160])
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
                        capa = _to_int_c(c.get('capacity'), 1)

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

    # --- [👨‍🏫 Tab 2: 강사 전용 공간] ---
    with tab2:
        st.subheader("🔒 강사 전용 클래스 관리")
        c_log = st.selectbox("본인 성함 선택", instructor_names, key="c_log_t2", on_change=reset_pw_c2)
        if c_log != "선택해주세요":
            minfo = next((m for m in st.session_state.get('instructors_data', []) if m['name'] == c_log), None)
            if minfo and st.text_input("비밀번호 입력", type="password", key="c_pw_t2") == str(minfo['pw']):
                mode = st.radio("작업 선택", ["신규 클래스 오픈하기", "내 클래스 정보 수정하기", "내 클래스 신청자 명단 보기"], horizontal=True)

                if mode == "신규 클래스 오픈하기":
                    with st.form("new_class_form"):
                        title = st.text_input("강의명 (예: 실무 엑셀 마스터)"); st.info(f"👨‍🏫 강사: **{c_log}**")
                        c1, c2 = st.columns(2); d_val = c1.date_input("강의 날짜")
                        t1, t2 = c1.columns(2); start_time = t1.time_input("시작 시간", datetime.time(14, 0)); end_time = t2.time_input("종료 시간", datetime.time(16, 0))
                        loc = c2.text_input("장소"); capa = c2.number_input("모집 정원", min_value=1, value=15)
                        desc = st.text_area("설명 및 준비물")

                        if st.form_submit_button("클래스 오픈하기"):
                            if not title:
                                st.error("⚠️ 강의명을 입력해 주세요!")
                            elif start_time >= end_time:
                                st.error("⚠️ 종료 시간은 시작 시간보다 늦어야 합니다.")
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

                elif mode == "내 클래스 정보 수정하기":
                    my_classes = [c for c in st.session_state.get('classes_data', []) if c['instructor'] == c_log]
                    if not my_classes:
                        st.info("개설된 클래스가 없습니다.")
                    else:
                        sel_class = st.selectbox("수정할 클래스 선택", [c['title'] for c in my_classes], key="edit_sel_class")
                        target_class = next(c for c in my_classes if c['title'] == sel_class)

                        # 기존 날짜 및 시간 텍스트 분리 분석
                        try:
                            curr_date = datetime.datetime.strptime(str(target_class['date']), "%Y-%m-%d").date()
                        except Exception:
                            curr_date = datetime.date.today()

                        try:
                            start_str, end_str = target_class['time'].split(" ~ ")
                            curr_start = datetime.datetime.strptime(start_str, "%H:%M").time()
                            curr_end = datetime.datetime.strptime(end_str, "%H:%M").time()
                        except Exception:
                            curr_start = datetime.time(14, 0); curr_end = datetime.time(16, 0)

                        with st.form("edit_class_form"):
                            edit_title = st.text_input("강의명", value=target_class['title'])
                            c1, c2 = st.columns(2)
                            edit_d_val = c1.date_input("강의 날짜", value=curr_date)
                            t1, t2 = c1.columns(2)
                            edit_start_time = t1.time_input("시작 시간", value=curr_start)
                            edit_end_time = t2.time_input("종료 시간", value=curr_end)
                            edit_loc = c2.text_input("장소", value=target_class['location'])
                            edit_capa = c2.number_input("모집 정원", min_value=1, value=_to_int_c(target_class.get('capacity'), 1))
                            edit_desc = st.text_area("설명 및 준비물", value=target_class['description'])

                            if st.form_submit_button("💾 변경사항 저장하기", use_container_width=True):
                                if not edit_title:
                                    st.error("⚠️ 강의명을 입력해 주세요!")
                                elif edit_start_time >= edit_end_time:
                                    st.error("⚠️ 종료 시간은 시작 시간보다 늦어야 합니다.")
                                else:
                                    with st.status("📡 강의 정보 수정 중..."):
                                        edit_t_val = f"{edit_start_time.strftime('%H:%M')} ~ {edit_end_time.strftime('%H:%M')}"
                                        title_changed = (edit_title != target_class['title'])

                                        # 1. classes_data 원본 업데이트
                                        for idx, idx_c in enumerate(st.session_state.classes_data):
                                            if idx_c['id'] == target_class['id']:
                                                st.session_state.classes_data[idx].update({
                                                    "title": edit_title, "date": str(edit_d_val), "time": edit_t_val,
                                                    "location": edit_loc, "capacity": edit_capa, "description": edit_desc
                                                })
                                                break
                                        save_ok1 = safe_save_class("classes", st.session_state.classes_data)

                                        # 2. 강의명이 바뀐 경우 기존 신청서 명단 데이터도 동기화
                                        save_ok2 = True
                                        if title_changed:
                                            for idx, idx_a in enumerate(st.session_state.c_reservations):
                                                if idx_a['class_id'] == target_class['id']:
                                                    st.session_state.c_reservations[idx]['class_title'] = edit_title
                                            save_ok2 = safe_save_class("applications", st.session_state.c_reservations)

                                    if save_ok1 and save_ok2:
                                        st.balloons(); st.success("성공적으로 변경되었습니다!"); time.sleep(1.5); st.rerun()

                else:
                    my_classes = [c for c in st.session_state.get('classes_data', []) if c['instructor'] == c_log]
                    if not my_classes:
                        st.info("개설 내역이 없습니다.")
                    else:
                        sel_class = st.selectbox("확인할 클래스 선택", [c['title'] for c in my_classes])
                        target_class = next(c for c in my_classes if c['title'] == sel_class)
                        applicants = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == target_class['id']]
                        st.write(f"### 📋 신청자 리스트 ({len(applicants)}명)")
                        if applicants:
                            df_app = pd.DataFrame(applicants)[['user_name', 'user_pos', 'user_team', 'user_email']]
                            df_app.columns = ['성함', '직급', '소속팀', '이메일']
                            st.dataframe(df_app, use_container_width=True)
                        else:
                            st.info("신청자가 없습니다.")

    # --- [👑 Tab 3: 관리자 메뉴] ---
    with tab3:
        st.subheader("👑 원데이 클래스 통합 관리 시스템")
        if not st.session_state.c_admin_logged_in:
            aid, apw = st.text_input("ID", key="c_ad_id"), st.text_input("PW", type="password", key="c_ad_pw")
            if st.button("로그인", key="c_login_btn") and aid == st.session_state.c_admin_info['id'] and apw == str(st.session_state.c_admin_info['pw']):
                st.session_state.c_admin_logged_in = True; st.rerun()
        else:
            col_out, col_ref = st.columns(2)
            if col_out.button("로그아웃", key="c_logout_btn"):
                st.session_state.c_admin_logged_in = False; st.rerun()
            if col_ref.button("🔄 시트 연결 새로고침", key="c_reset_conn",
                              help="구글 시트가 말썽일 때 눌러 주세요."):
                _reset_class_conn(); st.success("연결을 새로 읽었습니다."); st.rerun()

            with st.expander("👨‍🏫 강사 신규 등록"):
                r1, r2, r3, r4 = st.columns(4); nm = r1.text_input("성함", key="c_n1"); np = r2.text_input("직급", key="c_n2"); nt = r3.text_input("팀명", key="c_n3"); n_pw = r4.text_input("초기 비번", key="c_n4")
                ne = st.text_input("사내 이메일", key="c_n5")
                if st.button("강사 등록", key="c_reg_btn") and is_company_email(ne):
                    st.session_state.instructors_data.append({"name": nm, "position": np, "team": nt, "pw": n_pw, "email": ne})
                    safe_save_class("instructors", st.session_state.instructors_data); st.success("등록됨"); st.rerun()

            with st.expander("📋 등록된 강사 현황 및 관리", expanded=True):
                instructors = st.session_state.get('instructors_data', [])
                if not instructors:
                    st.info("현재 등록된 사내 강사가 없습니다.")
                else:
                    for i, m in enumerate(instructors):
                        st.markdown(f"#### 👤 {m['name']} 강사님")
                        er1, er2, er3, er4 = st.columns(4)
                        un = er1.text_input("성함", m['name'], key=f"c_un_{i}"); up = er2.text_input("직급", m.get('position', ''), key=f"c_up_{i}")
                        ut = er3.text_input("팀명", m.get('team', ''), key=f"c_ut_{i}"); upw = er4.text_input("비번", m.get('pw', ''), key=f"c_upw_{i}")
                        ue = st.text_input("사내 이메일", m.get('email', ''), key=f"c_ue_{i}")
                        col_btn1, col_btn2 = st.columns(2)
                        if col_btn1.button("💾 정보 수정", key=f"c_sv_{i}", use_container_width=True):
                            if is_company_email(ue):
                                st.session_state.instructors_data[i].update({"name": un, "position": up, "team": ut, "pw": upw, "email": ue})
                                safe_save_class("instructors", st.session_state.instructors_data); st.success("수정 완료!"); st.rerun()
                            else:
                                st.error("이메일 형식을 확인해주세요.")
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
