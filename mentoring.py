from utils import *

def run_mentoring():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .status-item { padding: 5px 10px; border-bottom: 1px solid #f0f2f6; line-height: 1.5; }
        /* 이중 탭 디자인을 조금 더 구분감 있게 만들어주는 CSS */
        div[data-testid="stTabs"] div[data-testid="stTabs"] button { font-size: 0.9em; padding-top: 5px; padding-bottom: 5px; }
        </style>
    """, unsafe_allow_html=True)

    st.header("🤝 동반성장 멘토링")
    st.caption("대한사료 임직원 간의 성장을 돕는 실시간 소통 플랫폼")
    st.markdown("---")

    if "admin_logged_in" not in st.session_state: st.session_state.admin_logged_in = False
    def reset_pw_t2():
        if "m_pw_t2" in st.session_state: st.session_state["m_pw_t2"] = ""
    def reset_pw_t3():
        if "m_pw_t3" in st.session_state: st.session_state["m_pw_t3"] = ""

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_멘토링_DB")

    @st.cache_data(ttl=60, show_spinner=False)
    def get_sheet_data(sheet_name):
        try:
            doc = init_gspread()
            return doc.worksheet(sheet_name).get_all_records()
        except Exception as e:
            st.error(f"⚠️ '{sheet_name}' 데이터를 불러오는 중 오류 발생: {e}")
            return []

    def fetch_latest_data(force=False):
        if force: st.cache_data.clear() 
        try:
            st.session_state.mentors_data = get_sheet_data("mentors")
            ad_list = get_sheet_data("admin")
            st.session_state.admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}
            
            raw_slots = get_sheet_data("slots")
            formatted_slots = []
            for s in raw_slots:
                if not s.get('date'): continue
                s['date'] = datetime.datetime.strptime(str(s['date']), "%Y-%m-%d").date()
                s['start'] = datetime.datetime.strptime(str(s['start']), "%H:%M:%S").time()
                s['end'] = datetime.datetime.strptime(str(s['end']), "%H:%M:%S").time()
                formatted_slots.append(s)
            st.session_state.available_slots = formatted_slots
            
            raw_res = get_sheet_data("reservations")
            formatted_res = []
            for r in raw_res:
                if not r.get('date'): continue
                r['date'] = datetime.datetime.strptime(str(r['date']), "%Y-%m-%d").date()
                r['start_time'] = datetime.datetime.strptime(str(r['start_time']), "%H:%M:%S").time()
                r['end_time'] = datetime.datetime.strptime(str(r['end_time']), "%H:%M:%S").time()
                r['status'] = str(r.get('status', '대기중')).strip()
                formatted_res.append(r)
            st.session_state.reservations = formatted_res
        except Exception as e: pass

    fetch_latest_data()

    def safe_save(ws_name, data_list):
        try:
            doc = init_gspread()
            ws = doc.worksheet(ws_name)
            ws.clear()
            if data_list:
                df = pd.DataFrame(data_list)
                for c in ['date', 'start', 'end', 'start_time', 'end_time']:
                    if c in df.columns: df[c] = df[c].astype(str)
                df = df.fillna("")
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data(force=True) 
            return True
        except Exception as e: 
            st.error(f"⚠️ 구글 시트 저장 오류 ({ws_name}): {e}")
            return False

    mentor_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('mentors_data', [])]

    # 🚀 1단계: 역할별 메인 메뉴 (Main Tabs)
    main_tab_mentee, main_tab_mentor, main_tab_admin = st.tabs(["🙋‍♂️ 멘티 공간", "💼 멘토 공간", "👑 관리자 메뉴"])

    # =========================================================
    # 🙋‍♂️ [메인 탭 1: 멘티 공간]
    # =========================================================
    with main_tab_mentee:
        st.subheader("🗓️ 멘토링 예약 신청")
        if st.button("🔄 최신 현황 불러오기"): fetch_latest_data(force=True); st.rerun()

        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            today_date = datetime.date.today()
            all_slots = [s for s in st.session_state.get('available_slots', []) if s['date'] >= today_date]
            
            if not all_slots: st.info("현재 등록된 신청 가능한 일정이 없습니다.")
            else:
                summ = {}
                for s in all_slots:
                    w_day = WEEKS[s['date'].weekday()]
                    info = f"📅 {s['date'].strftime('%m/%d')}({w_day}) ⏰ {s['start'].strftime('%H:%M')}~{s['end'].strftime('%H:%M')} [📍 {s.get('location','-')}]"
                    summ[s['mentor']] = summ.get(s['mentor'], []) + [info]
                for m, infos in summ.items():
                    st.markdown(f"✅ **{m} 멘토님**")
                    for single_info in sorted(infos): st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{single_info}")

        st.markdown("---")
        
        st.markdown("#### 1️⃣ 멘토 및 일정 선택")
        r_sel1, r_sel2 = st.columns(2)
        selected_m = r_sel1.selectbox("멘토 선택", mentor_names, key="m_s_t1")
        sel_date = r_sel2.date_input("날짜 선택", datetime.date.today() + datetime.timedelta(days=1), key="d_s_t1", format="YYYY/MM/DD")

        if selected_m != "선택해주세요":
            p = next((m for m in st.session_state.get('mentors_data', []) if m['name'] == selected_m), None)
            if p: 
                st.markdown(f"""
                <div style="border: 2px solid #4A90E2; padding: 18px; border-radius: 12px; background-color: #f0f7ff; margin-top: 10px; margin-bottom: 20px;">
                    <h4 style="margin-top:0; color: #1E3A8A;">🎖️ {p['name']} {p.get('position','')} 멘토</h4>
                    <p style="margin-bottom: 8px; font-size: 0.95em;">🏢 소속: {p.get('team','')}<br>🎯 전문분야: {p.get('expertise','')}</p>
                    <div style="background-color: white; padding: 10px; border-radius: 8px; border-left: 4px solid #4A90E2;">
                        <p style="font-size: 0.9em; margin: 0; color: #555;"><i>"{p.get('greeting','')}"</i></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            slots = [s for s in st.session_state.get('available_slots', []) if s['mentor']==selected_m and s['date']==sel_date]
            if slots:
                st.markdown("---")
                ts = slots[0]['start']
                te = slots[0]['end']
                loc = slots[0].get('location', '-')
                
                st.success(f"✅ **자동 배정된 멘토링 시간:** {ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')} (📍 장소: {loc})")

                st.markdown("#### 2️⃣ 신청자 정보 입력")
                with st.form(key="apply_form_mentoring"):
                    r1_c1, r1_c2 = st.columns(2)
                    m_n = r1_c1.text_input("신청자 성함")
                    m_t = r1_c2.text_input("팀명")

                    r2_c1, r2_c2 = st.columns(2)
                    m_p = r2_c1.text_input("직급")
                    m_e = r2_c2.text_input("사내 이메일", placeholder="example@daehanfeed.co.kr")

                    topic = st.text_area("상담 주제 (필수)")
                    
                    submit_btn = st.form_submit_button("🚀 예약 신청하기", use_container_width=True)

                    if submit_btn:
                        if not m_n or not topic or not is_company_email(m_e): 
                            st.warning("⚠️ 정보를 정확히 입력해 주세요. (이메일은 @daehanfeed.co.kr 필수)")
                        else:
                            with st.status("📡 매칭 처리 중..."):
                                new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": loc, "status": "대기중"}
                                st.session_state.reservations.append(new_res)
                                save1 = safe_save("reservations", st.session_state.reservations)
                                
                                slot_to_del = next((s for s in st.session_state.available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                                save2 = True
                                if slot_to_del:
                                    st.session_state.available_slots.remove(slot_to_del)
                                    save2 = safe_save("slots", st.session_state.available_slots)

                                m_info = next((m for m in st.session_state.mentors_data if m['name']==selected_m), None)
                                mail_ok = False
                                if m_info and m_info.get('email'):
                                    mail_subject = f"[대한사료 멘토링] 새로운 멘토링 신청이 접수되었습니다."
                                    mail_body = f"안녕하세요, {selected_m} 멘토님!\n\n{m_n}님께서 멘토링을 신청하셨습니다.\n\n- 일시: {sel_date} ({ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')})\n- 주제: {topic}\n\n▶ 시스템 접속: {SYSTEM_URL}"
                                    mail_ok = send_email(m_info['email'], mail_subject, mail_body)

                                if save1 and save2:
                                    status.update(label="처리 완료!", state="complete")
                                    st.balloons()
                                    if mail_ok:
                                        st.success("✅ 신청이 완료되었으며, 멘토님께 알림 메일이 발송되었습니다.")
                                    else:
                                        st.warning("⚠️ 예약은 정상 저장되었으나 메일 발송에 실패했습니다.")
                                    time.sleep(3)
                                    fetch_latest_data(force=True) 
                                    st.rerun()
                                else:
                                    status.update(label="처리 실패", state="error")
                                    st.error("⚠️ 데이터 저장에 실패하여 신청이 취소되었습니다.")

    # =========================================================
    # 💼 [메인 탭 2: 멘토 공간]
    # =========================================================
    with main_tab_mentor:
        # 🚀 2단계: 멘토 메인 메뉴 안의 이중 탭 (서브 메뉴)
        sub_tab_schedule, sub_tab_manage, sub_tab_pw = st.tabs(["🗓️ 일정 등록 및 관리", "📋 신청 현황 및 예약 관리", "🔑 비밀번호 변경"])
        
        # --- [서브 탭 1: 일정 관리] ---
        with sub_tab_schedule:
            st.subheader("💼 나의 멘토링 일정 관리")
            m_log2 = st.selectbox("본인 성함 선택", mentor_names, key="m_log_t2", on_change=reset_pw_t2)
            if m_log2 != "선택해주세요":
                minfo = next((m for m in st.session_state.get('mentors_data', []) if m['name']==m_log2), None)
                if minfo and st.text_input("비밀번호 입력", type="password", key="m_pw_t2") == str(minfo['pw']):
                    c2_1, c2_2, c2_3, c2_4 = st.columns(4)
                    dv, sv, ev, lv = c2_1.date_input("날짜", key="sd_t2"), c2_2.time_input("시작", datetime.time(0,0), key="ss_t2"), c2_3.time_input("종료", datetime.time(0,0), key="se_t2"), c2_4.text_input("장소", key="sl_t2")
                    
                    if st.button("🗓️ 일정 등록하기", type="primary", use_container_width=True, key="sb_t2"):
                        is_duplicate = False
                        for r in st.session_state.get('reservations', []):
                            if r['mentor'] == m_log2 and r['date'] == dv:
                                if not (ev <= r['start_time'] or sv >= r['end_time']): is_duplicate = True; break
                        if not is_duplicate:
                            for s in st.session_state.get('available_slots', []):
                                if s['mentor'] == m_log2 and s['date'] == dv:
                                    if not (ev <= s['start'] or sv >= s['end']): is_duplicate = True; break
                        
                        if is_duplicate: st.error("🚫 중복된 시간이 존재합니다.")
                        elif sv >= ev: st.error("🚫 시간 설정 오류")
                        else:
                            with st.status("📡 저장 중..."):
                                st.session_state.available_slots.append({"mentor": m_log2, "date": dv, "start": sv, "end": ev, "location": lv})
                                if safe_save("slots", st.session_state.available_slots):
                                    st.snow(); st.success("등록 완료!")
                                    time.sleep(1.5)
                                    fetch_latest_data(force=True)
                                    st.rerun()
                
                    st.divider(); st.markdown(f"#### 🗑️ {m_log2} 멘토님의 등록 일정")
                    my_slots = [x for x in st.session_state.get('available_slots', []) if x['mentor'] == m_log2]
                    for i, s in enumerate(my_slots):
                        col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                        col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                        if col_b.button("삭제", key=f"del_s_{i}"):
                            st.session_state.available_slots.remove(s)
                            if safe_save("slots", st.session_state.available_slots):
                                fetch_latest_data(force=True)
                                st.rerun()

        # --- [서브 탭 2: 예약 관리 및 후기] ---
        with sub_tab_manage:
            st.subheader("📋 멘티 신청 현황 및 후기 관리")
            m_sel3 = st.selectbox("본인 성함 선택", mentor_names, key="m_sel_t3", on_change=reset_pw_t3)
            if m_sel3 != "선택해주세요":
                minfo3 = next((m for m in st.session_state.get('mentors_data', []) if m['name']==m_sel3), None)
                if minfo3 and st.text_input("비번 확인", type="password", key="m_pw_t3") == str(minfo3['pw']):
                    my_res = [x for x in st.session_state.get('reservations', []) if x['mentor']==m_sel3]
                    my_res.sort(key=lambda x: 0 if x['status'] == "대기중" else (1 if x['status'] in ["승인됨", "완료(후기작성됨)"] else 2))
                    
                    for r in my_res:
                        with st.expander(f"[{r['status']}] {r['date']}({WEEKS[r['date'].weekday()]}) | {r['mentee_name']}님"):
                            col_r1, col_r2 = st.columns(2)
                            with col_r1:
                                st.write(f"- 성함: {r['mentee_name']} ({r.get('mentee_position','-')})\n- 팀명: {r.get('mentee_team','-')}\n- 이메일: {r.get('mentee_email','-')}")
                            with col_r2:
                                st.write(f"- 시간: {r['start_time']} ~ {r['end_time']}\n- 주제: {r['topic']}")
                            
                            if r['status'] == "대기중":
                                b1, b2 = st.columns(2)
                                if b1.button("✅ 승인", key=f"ok_{r['id']}", use_container_width=True):
                                    r['status']="승인됨"
                                    if safe_save("reservations", st.session_state.reservations):
                                        if r.get('mentee_email'):
                                            body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 멘토링 예약이 승인되었습니다.\n\n- 일시: {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 멘토: {m_sel3} 멘토님\n\n감사합니다."
                                            send_email(r['mentee_email'], "[대한사료 멘토링] 신청하신 예약이 승인되었습니다!", body)
                                        fetch_latest_data(force=True)
                                        st.rerun()
                                
                                if b2.button("❌ 거절", key=f"no_{r['id']}", use_container_width=True):
                                    r['status']="거절됨"
                                    if safe_save("reservations", st.session_state.reservations):
                                        if r.get('mentee_email'):
                                            send_email(r['mentee_email'], "[대한사료 멘토링] 예약 반려 안내", f"아쉽게도 {m_sel3} 멘토님이 예약을 반려하셨습니다.")
                                        st.session_state.available_slots.append({
                                            "mentor": r['mentor'], "date": r['date'], "start": r['start_time'], "end": r['end_time'], "location": r.get('location', '')
                                        })
                                        safe_save("slots", st.session_state.available_slots)
                                        fetch_latest_data(force=True)
                                        st.rerun()

                            elif r['status'] in ["승인됨", "완료(후기작성됨)"]:
                                st.divider()
                                if r.get('review_text'):
                                    st.success(f"**📝 작성된 멘토링 후기** (진행일: {r.get('review_date', '-')})")
                                    st.write(f"- **참석자**: {r.get('review_mentor', '-')} 멘토 & {r.get('review_mentee', '-')} 멘티")
                                    st.info(r['review_text'])
                                    if st.button("✏️ 후기 수정하기", key=f"edit_rev_{r['id']}"):
                                        r['status'] = "승인됨" 
                                        r['review_text'] = ""
                                        if safe_save("reservations", st.session_state.reservations): st.rerun()
                                else:
                                    with st.form(key=f"review_form_{r['id']}"):
                                        st.markdown("#### 📝 멘토링 진행 후기 작성")
                                        c1, c2, c3 = st.columns(3)
                                        rev_date = c1.date_input("실제 진행 일자", value=r['date'], key=f"rd_{r['id']}")
                                        rev_mentor = c2.text_input("멘토 이름", value=r['mentor'], key=f"rm_{r['id']}")
                                        rev_mentee = c3.text_input("멘티 이름", value=r['mentee_name'], key=f"rme_{r['id']}")
                                        rev_text = st.text_area("후기 내용", placeholder="멘토링에서 나눈 주요 내용, 피드백, 느낀 점을 자유롭게 남겨주세요.", key=f"rt_{r['id']}")
                                        
                                        if st.form_submit_button("💾 후기 저장하기", use_container_width=True):
                                            if rev_text.strip() == "":
                                                st.error("후기 내용을 입력해 주세요!")
                                            else:
                                                r['review_date'] = str(rev_date); r['review_mentor'] = rev_mentor
                                                r['review_mentee'] = rev_mentee; r['review_text'] = rev_text
                                                r['status'] = "완료(후기작성됨)" 
                                                if safe_save("reservations", st.session_state.reservations):
                                                    st.success("후기가 성공적으로 저장되었습니다!")
                                                    time.sleep(1.5)
                                                    st.rerun()

        # --- [서브 탭 3: 비밀번호 변경] ---
        with sub_tab_pw:
            st.subheader("🔑 멘토 비밀번호 변경")
            st.info("💡 안전한 플랫폼 이용을 위해 초기 지정된 암호는 본인만 아는 비밀번호로 수시 변경하여 관리해 주세요.")
            
            with st.form(key="change_password_form_mentoring"):
                c1, c2 = st.columns(2)
                cp_name = c1.selectbox("본인 성함 선택", mentor_names, key="cp_name_sel_m")
                current_pw_input = c1.text_input("현재 비밀번호 입력", type="password")
                
                new_pw_input = c2.text_input("새로운 비밀번호 입력", type="password")
                new_pw_confirm = c2.text_input("새로운 비밀번호 확인", type="password")
                
                submit_cp = st.form_submit_button("🔒 비밀번호 변경하기", use_container_width=True)
                
                if submit_cp:
                    if cp_name == "선택해주세요" or not current_pw_input or not new_pw_input or not new_pw_confirm:
                        st.warning("모든 항목을 정확하게 입력해 주세요.")
                    else:
                        cp_info = next((m for m in st.session_state.mentors_data if m['name'] == cp_name), None)
                        if not cp_info:
                            st.error("해당 이름의 멘토를 찾을 수 없습니다.")
                        elif str(cp_info['pw']) != current_pw_input:
                            st.error("🚫 현재 비밀번호가 일치하지 않습니다. 다시 확인해 주세요.")
                        elif new_pw_input != new_pw_confirm:
                            st.error("🚫 새로운 비밀번호와 확인용 비밀번호가 일치하지 않습니다.")
                        else:
                            with st.status("📡 비밀번호 변경 내용 동기화 중..."):
                                for idx, m in enumerate(st.session_state.mentors_data):
                                    if m['name'] == cp_name:
                                        st.session_state.mentors_data[idx]['pw'] = new_pw_input
                                        break
                                if safe_save("mentors", st.session_state.mentors_data):
                                    st.success("✅ 비밀번호가 안전하게 변경되었습니다!")
                                    time.sleep(1.5)
                                    st.rerun()

    # =========================================================
    # 👑 [메인 탭 3: 관리자 공간]
    # =========================================================
    with main_tab_admin:
        st.subheader("👑 인사총무팀 전용 관리 시스템")
        if not st.session_state.admin_logged_in:
            aid, apw = st.text_input("ID", key="ad_id"), st.text_input("PW", type="password", key="ad_pw")
            if st.button("로그인") and aid == st.session_state.admin_info['id'] and apw == str(st.session_state.admin_info['pw']):
                st.session_state.admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃"): st.session_state.admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 멘토 신규 등록"):
                r1, r2, r3, r4 = st.columns(4); nm, np, nt, n_pw = r1.text_input("성함",key="n1"), r2.text_input("직급",key="n2"), r3.text_input("팀명",key="n3"), r4.text_input("비번",key="n4")
                e1, e2 = st.columns(2); ne = e1.text_input("이메일",key="n5"); nx = e2.text_input("전문분야",key="n6"); ng = st.text_area("인사말", key="n7")
                if st.button("등록하기") and is_company_email(ne):
                    st.session_state.mentors_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "expertise":nx, "greeting":ng, "email":ne})
                    if safe_save("mentors", st.session_state.mentors_data):
                        fetch_latest_data(force=True); st.rerun()
            
            with st.expander("📋 기존 멘토 수정/삭제", expanded=True):
                for i, m in enumerate(st.session_state.get('mentors_data', [])):
                    st.markdown(f"#### 👤 {m['name']} 리더님 정보 수정")
                    er1, er2, er3, er4 = st.columns(4); un = er1.text_input("성함", m['name'], key=f"un_{i}"); up = er2.text_input("직급", m.get('position',''), key=f"up_{i}"); ut = er3.text_input("팀명", m.get('team',''), key=f"ut_{i}"); upw = er4.text_input("비번", m.get('pw',''), key=f"upw_{i}")
                    e1, e2 = st.columns(2); ue = e1.text_input("이메일", m.get('email',''), key=f"ue_{i}"); ux = e2.text_input("전문분야", m.get('expertise',''), key=f"ux_{i}"); ug = st.text_area("인사말", m.get('greeting',''), key=f"ug_{i}")
                    if st.button("💾 저장", key=f"sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.mentors_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue,"expertise":ux,"greeting":ug})
                            if safe_save("mentors", st.session_state.mentors_data): st.success("수정됨"); fetch_latest_data(force=True); st.rerun()
                    if st.button("❌ 삭제", key=f"dl_{i}"):
                        st.session_state.mentors_data.pop(i)
                        if safe_save("mentors", st.session_state.mentors_data): fetch_latest_data(force=True); st.rerun()
                    st.divider()
