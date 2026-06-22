import requests
import json
import streamlit as st
import datetime
import uuid
import pandas as pd
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from utils import *

def run_leader_talk():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .status-item { padding: 5px 10px; border-bottom: 1px solid #f0f2f6; line-height: 1.5; }
        /* 이중 탭 디자인을 구분감 있게 만들어주는 CSS */
        div[data-testid="stTabs"] div[data-testid="stTabs"] button { font-size: 0.9em; padding-top: 5px; padding-bottom: 5px; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("☕ 리더와의 대화")
    st.caption("경영진 및 팀장급 리더와 자유롭게 소통하며 비전을 나누는 시간입니다.")
    st.markdown("---")

    if "l_admin_logged_in" not in st.session_state: st.session_state.l_admin_logged_in = False

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread_leader():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_리더대화_DB")

    def get_sheet_data_leader(sheet_name):
        try: doc = init_gspread_leader(); return doc.worksheet(sheet_name).get_all_records()
        except: return []

    def fetch_latest_data_leader(force=False):
        if force: st.cache_data.clear()
        try:
            st.session_state.leaders_data = get_sheet_data_leader("leaders")
            ad_list = get_sheet_data_leader("admin")
            st.session_state.l_admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}
            
            raw_slots = get_sheet_data_leader("slots")
            formatted_slots = []
            for s in raw_slots:
                if not s.get('date'): continue
                s['date'] = datetime.datetime.strptime(str(s['date']), "%Y-%m-%d").date()
                s['start'] = datetime.datetime.strptime(str(s['start']), "%H:%M:%S").time()
                s['end'] = datetime.datetime.strptime(str(s['end']), "%H:%M:%S").time()
                formatted_slots.append(s)
            st.session_state.l_available_slots = formatted_slots
            
            raw_res = get_sheet_data_leader("reservations")
            formatted_res = []
            for r in raw_res:
                if not r.get('date'): continue
                r['date'] = datetime.datetime.strptime(str(r['date']), "%Y-%m-%d").date()
                r['start_time'] = datetime.datetime.strptime(str(r['start_time']), "%H:%M:%S").time()
                r['end_time'] = datetime.datetime.strptime(str(r['end_time']), "%H:%M:%S").time()
                r['status'] = str(r.get('status', '대기중')).strip()
                formatted_res.append(r)
            st.session_state.l_reservations = formatted_res
        except: pass

    fetch_latest_data_leader()

    def safe_save_leader(ws_name, data_list):
        try:
            doc = init_gspread_leader()
            ws = doc.worksheet(ws_name)
            ws.clear()
            if data_list:
                df = pd.DataFrame(data_list)
                for c in ['date', 'start', 'end', 'start_time', 'end_time']:
                    if c in df.columns: df[c] = df[c].astype(str)
                df = df.fillna("")
                ws.update([df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data_leader(force=True)
        except: st.error("⚠️ 데이터 저장 오류")

    def send_dooray_noti(leader_name, date, start, end, location):
        webhook_url = "https://dhflour.dooray.com/services/2381698226825327324/4360453717122810883/xUa23WA3SJGNp2KDxVnZWA"
        
        start_str = start.strftime('%H:%M') if hasattr(start, 'strftime') else str(start)[:5]
        end_str = end.strftime('%H:%M') if hasattr(end, 'strftime') else str(end)[:5]
        
        message = {
            "botName": "조직문화 알리미",
            "botIconImage": "https://cdn-icons-png.flaticon.com/512/1944/1944436.png",
            "text": f"📢 [{leader_name} 리더님]의 새로운 대화 일정이 오픈되었습니다!\n\n"
                    f"  • 📅 일시 : {date} ({start_str} ~ {end_str})\n"
                    f"  • 📍 장소 : {location}\n\n"
                    f"▶ 지금 바로 조직문화 플랫폼에 접속해서 대화를 신청해 보세요!\n"
                    f"      https://dhfeed-culture.streamlit.app"
        }
        try:
            requests.post(webhook_url, headers={"Content-Type": "application/json"}, data=json.dumps(message))
        except:
            pass

    leader_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('leaders_data', [])]

    # 🚀 큰 방 3개 (역할별 메인 탭) 생성
    main_tab_mentee, main_tab_leader, main_tab_admin = st.tabs(["🙋‍♂️ 구성원 대화 신청", "💼 리더 공간", "👑 관리자 메뉴"])

    # =========================================================
    # 🙋‍♂️ [메인 탭 1: 구성원 대화 신청 공간]
    # =========================================================
    with main_tab_mentee:
        st.subheader("🗓️ 리더와의 대화 신청")
        if st.button("🔄 최신 현황 불러오기", key="l_refresh_1"): fetch_latest_data_leader(force=True); st.rerun()

        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            today_date = datetime.date.today()
            all_slots = [s for s in st.session_state.get('l_available_slots', []) if s['date'] >= today_date]
            
            if not all_slots: st.info("현재 등록된 신청 가능한 일정이 없습니다.")
            else:
                summ = {}
                for s in all_slots:
                    w_day = WEEKS[s['date'].weekday()]
                    info = f"📅 {s['date'].strftime('%m/%d')}({w_day}) ⏰ {s['start'].strftime('%H:%M')}~{s['end'].strftime('%H:%M')} [📍 {s.get('location','-')}]"
                    summ[s['mentor']] = summ.get(s['mentor'], []) + [info]
                for m, infos in summ.items():
                    st.markdown(f"✅ **{m} 리더님**")
                    for single_info in sorted(infos): st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{single_info}")

        st.markdown("---")
        
        st.markdown("#### 1️⃣ 대화할 리더 및 일정 선택")
        r_sel1, r_sel2 = st.columns(2)
        # 구성원들은 리더를 선택해야 하므로 여기는 기존처럼 드롭다운(selectbox)을 유지합니다.
        selected_m = r_sel1.selectbox("리더 선택", leader_names, key="l_s_t1")
        sel_date = r_sel2.date_input("날짜 선택", datetime.date.today() + datetime.timedelta(days=1), key="l_d_t1", format="YYYY/MM/DD")
            
        if selected_m != "선택해주세요":
            p = next((m for m in st.session_state.get('leaders_data', []) if m['name'] == selected_m), None)
            if p: 
                st.markdown(f"""
                <div style="border: 2px solid #2ECC71; padding: 18px; border-radius: 12px; background-color: #EAFDF1; margin-top: 10px; margin-bottom: 20px;">
                    <h4 style="margin-top:0; color: #1E8449;">👑 {p['name']} {p.get('position','')}</h4>
                    <p style="margin-bottom: 8px; font-size: 0.95em;">🏢 소속: {p.get('team','')}<br>🎯 담당/전문분야: {p.get('expertise','')}</p>
                    <div style="background-color: white; padding: 10px; border-radius: 8px; border-left: 4px solid #2ECC71;">
                        <p style="font-size: 0.9em; margin: 0; color: #555;"><i>"{p.get('greeting','')}"</i></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            slots = [s for s in st.session_state.get('l_available_slots', []) if s['mentor']==selected_m and s['date']==sel_date]
            if slots:
                ts = slots[0]['start']
                te = slots[0]['end']
                loc = slots[0].get('location', '-')
                st.success(f"✅ **자동 배정된 대화 시간:** {ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')} (📍 장소: {loc})")
                
                st.markdown("#### 2️⃣ 신청자 정보 입력")
                with st.form(key="apply_form"):
                    r1_c1, r1_c2 = st.columns(2)
                    m_n = r1_c1.text_input("신청자 성함")
                    m_t = r1_c2.text_input("팀명")

                    r2_c1, r2_c2 = st.columns(2)
                    m_p = r2_c1.text_input("직급")
                    m_e = r2_c2.text_input("사내 이메일", placeholder="example@daehanfeed.co.kr")
                    
                    topic = st.text_area("대화 희망 주제 (필수)")
                    
                    submit_btn = st.form_submit_button("🚀 신청하기", use_container_width=True)
                    
                    if submit_btn:
                        if not m_n or not topic or not is_company_email(m_e): 
                            st.warning("⚠️ 정보를 정확히 입력해 주세요. (이메일은 @daehanfeed.co.kr 필수)")
                        else:
                            with st.status("📡 매칭 처리 중..."):
                                new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": loc, "status": "대기중"}
                                st.session_state.l_reservations.append(new_res)
                                safe_save_leader("reservations", st.session_state.l_reservations)
                                
                                slot_to_del = next((s for s in st.session_state.l_available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                                if slot_to_del:
                                    st.session_state.l_available_slots.remove(slot_to_del)
                                    safe_save_leader("slots", st.session_state.l_available_slots)

                                m_info = next((m for m in st.session_state.leaders_data if m['name']==selected_m), None)
                                if m_info and m_info.get('email'):
                                    mail_subject = f"[대한사료 리더대화] 새로운 대화 신청이 접수되었습니다."
                                    mail_body = f"안녕하세요, {selected_m} 리더님!\n\n{m_n}님께서 대화를 신청하셨습니다.\n\n- 일시: {sel_date} ({ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')})\n- 주제: {topic}\n\n▶ 시스템 접속: {SYSTEM_URL}"
                                    send_email(m_info['email'], mail_subject, mail_body)
                            st.balloons(); time.sleep(1); st.rerun()

    # =========================================================
    # 💼 [메인 탭 2: 리더 전용 공간]
    # =========================================================
    with main_tab_leader:
        sub_tab_schedule, sub_tab_manage, sub_tab_info = st.tabs(["🗓️ 일정 등록 및 관리", "📋 신청 현황 관리", "⚙️ 리더 정보 변경"])
        
        # --- [서브 탭 1: 일정 관리] ---
        with sub_tab_schedule:
            st.subheader("💼 나의 일정 관리")
            st.markdown("🔒 **리더 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            l_name_1 = c_log1.text_input("본인 성함", key="l_name_1", placeholder="이름을 입력하세요")
            l_pw_1 = c_log2.text_input("비밀번호", type="password", key="l_pw_1")
            
            if l_name_1 and l_pw_1:
                minfo = next((m for m in st.session_state.get('leaders_data', []) if m['name'] == l_name_1), None)
                if not minfo:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(minfo['pw']) != l_pw_1:
                    st.error("🚫 비밀번호가 일치하지 않습니다.")
                else:
                    st.success(f"✅ {l_name_1} 리더님, 환영합니다!")
                    st.markdown("---")
                    c2_1, c2_2, c2_3, c2_4 = st.columns(4)
                    dv, sv, ev, lv = c2_1.date_input("날짜", key="l_sd_t2"), c2_2.time_input("시작", datetime.time(0,0), key="l_ss_t2"), c2_3.time_input("종료", datetime.time(0,0), key="l_se_t2"), c2_4.text_input("장소", key="l_sl_t2")
                    
                    if st.button("🗓️ 일정 등록하기", type="primary", use_container_width=True, key="l_sb_t2"):
                        is_duplicate = False
                        for r in st.session_state.get('l_reservations', []):
                            if r['mentor'] == l_name_1 and r['date'] == dv:
                                if not (ev <= r['start_time'] or sv >= r['end_time']): is_duplicate = True; break
                        if not is_duplicate:
                            for s in st.session_state.get('l_available_slots', []):
                                if s['mentor'] == l_name_1 and s['date'] == dv:
                                    if not (ev <= s['start'] or sv >= s['end']): is_duplicate = True; break
                    
                        if is_duplicate: st.error("🚫 중복된 시간이 존재합니다.")
                        elif sv >= ev: st.error("🚫 시간 설정 오류")
                        else:
                            with st.status("📡 저장 중..."):
                                st.session_state.l_available_slots.append({"mentor": l_name_1, "date": dv, "start": sv, "end": ev, "location": lv})
                                safe_save_leader("slots", st.session_state.l_available_slots)
                                send_dooray_noti(l_name_1, dv, sv, ev, lv)
                            st.snow(); st.success("등록 완료!"); time.sleep(1); st.rerun()
            
                    st.divider(); st.markdown(f"#### 🗑️ {l_name_1} 리더님의 등록 일정")
                    my_slots = [x for x in st.session_state.get('l_available_slots', []) if x['mentor'] == l_name_1]
                    for i, s in enumerate(my_slots):
                        col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                        col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                        if col_b.button("삭제", key=f"l_del_s_{i}"):
                            st.session_state.l_available_slots.remove(s); safe_save_leader("slots", st.session_state.l_available_slots); st.rerun()

        # --- [서브 탭 2: 신청 현황 관리] ---
        with sub_tab_manage:
            st.subheader("📋 구성원 신청 현황 관리")
            st.markdown("🔒 **리더 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            l_name_2 = c_log1.text_input("본인 성함", key="l_name_2", placeholder="이름을 입력하세요")
            l_pw_2 = c_log2.text_input("비밀번호", type="password", key="l_pw_2")
            
            if l_name_2 and l_pw_2:
                minfo3 = next((m for m in st.session_state.get('leaders_data', []) if m['name'] == l_name_2), None)
                if not minfo3:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(minfo3['pw']) != l_pw_2:
                    st.error("🚫 비밀번호가 일치하지 않습니다.")
                else:
                    st.success(f"✅ {l_name_2} 리더님, 환영합니다!")
                    st.markdown("---")
                    my_res = [x for x in st.session_state.get('l_reservations', []) if x['mentor'] == l_name_2]
                    for r in my_res:
                        with st.expander(f"[{r['status']}] {r['date']}({WEEKS[r['date'].weekday()]}) | {r['mentee_name']}님"):
                            col_r1, col_r2 = st.columns(2)
                            with col_r1:
                                st.write(f"- 성함: {r['mentee_name']} ({r.get('mentee_position','-')})\n- 팀명: {r.get('mentee_team','-')}\n- 이메일: {r.get('mentee_email','-')}")
                            with col_r2:
                                st.write(f"- 시간: {r['start_time']} ~ {r['end_time']}\n- 주제: {r['topic']}")
                            
                            if r['status'] == "대기중":
                                b1, b2 = st.columns(2)
                                if b1.button("✅ 승인", key=f"l_ok_{r['id']}", use_container_width=True):
                                    r['status']="승인됨"; safe_save_leader("reservations", st.session_state.l_reservations)
                                    if r.get('mentee_email'):
                                        body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 리더와의 대화가 승인되었습니다.\n\n- 일시: {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 리더: {l_name_2} 리더님\n\n감사합니다."
                                        send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 승인되었습니다!", body)
                                    st.rerun()
                            
                                if b2.button("❌ 거절", key=f"l_no_{r['id']}", use_container_width=True):
                                    r['status']="거절됨"; safe_save_leader("reservations", st.session_state.l_reservations)
                                    if r.get('mentee_email'):
                                        send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 반려되었습니다.", f"아쉽게도 {l_name_2} 리더님이 예약을 반려하셨습니다. 다른 일정을 선택해 주세요.")
                                    st.session_state.l_available_slots.append({
                                        "mentor": r['mentor'], "date": r['date'], "start": r['start_time'], "end": r['end_time'], "location": r.get('location', '')
                                    })
                                    safe_save_leader("slots", st.session_state.l_available_slots)
                                    st.rerun()

        # --- [서브 탭 3: 리더 정보 변경] ---
        with sub_tab_info:
            st.subheader("⚙️ 리더 정보 변경")
            st.info("💡 본인의 담당/전문분야, 인사말, 그리고 비밀번호를 편하게 직접 수정하실 수 있습니다.")
            st.markdown("🔒 **리더 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            l_name_3 = c_log1.text_input("본인 성함", key="l_name_3", placeholder="이름을 입력하세요")
            l_pw_3 = c_log2.text_input("현재 비밀번호 입력", type="password", key="l_pw_3")
            
            if l_name_3 and l_pw_3:
                linfo_info = next((m for m in st.session_state.get('leaders_data', []) if m['name'] == l_name_3), None)
                if not linfo_info:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(linfo_info['pw']) != l_pw_3:
                    st.error("🚫 비밀번호가 일치하지 않습니다. 다시 확인해 주세요.")
                else:
                    st.success(f"✅ {l_name_3} 리더님, 환영합니다!")
                    st.markdown("---")
                    with st.form(key="edit_leader_info_form"):
                        st.markdown("#### 📝 프로필 정보 수정")
                        new_exp = st.text_input("담당/전문분야", value=linfo_info.get('expertise', ''))
                        new_greet = st.text_area("인사말", value=linfo_info.get('greeting', ''))
                        
                        st.markdown("#### 🔒 비밀번호 변경 (유지하려면 비워두세요)")
                        c1, c2 = st.columns(2)
                        new_pw = c1.text_input("새로운 비밀번호", type="password")
                        new_pw_confirm = c2.text_input("새로운 비밀번호 확인", type="password")
                        
                        submit_info = st.form_submit_button("💾 정보 업데이트", use_container_width=True)
                        
                        if submit_info:
                            has_error = False
                            final_pw = linfo_info['pw']
                            
                            if new_pw or new_pw_confirm:
                                if new_pw != new_pw_confirm:
                                    st.error("🚫 새로운 비밀번호와 확인용 비밀번호가 일치하지 않습니다.")
                                    has_error = True
                                else:
                                    final_pw = new_pw
                                    
                            if not has_error:
                                with st.status("📡 정보 동기화 중..."):
                                    for idx, m in enumerate(st.session_state.leaders_data):
                                        if m['name'] == l_name_3:
                                            st.session_state.leaders_data[idx]['expertise'] = new_exp
                                            st.session_state.leaders_data[idx]['greeting'] = new_greet
                                            st.session_state.leaders_data[idx]['pw'] = final_pw
                                            break
                                    safe_save_leader("leaders", st.session_state.leaders_data)
                                    st.success("✅ 리더 정보가 성공적으로 변경되었습니다!")
                                    time.sleep(1.5)
                                    st.rerun()

    # =========================================================
    # 👑 [메인 탭 3: 관리자 공간]
    # =========================================================
    with main_tab_admin:
        st.subheader("👑 인사총무팀 전용 관리 시스템")
        if not st.session_state.l_admin_logged_in:
            aid, apw = st.text_input("ID", key="l_ad_id"), st.text_input("PW", type="password", key="l_ad_pw")
            if st.button("로그인", key="l_login_btn") and aid == st.session_state.l_admin_info['id'] and apw == str(st.session_state.l_admin_info['pw']):
                st.session_state.l_admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃", key="l_logout_btn"): st.session_state.l_admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 리더 신규 등록"):
                r1, r2, r3, r4 = st.columns(4)
                nm = r1.text_input("성함",key="l_n1"); np = r2.text_input("직급",key="l_n2")
                nt = r3.text_input("팀명",key="l_n3"); n_pw = r4.text_input("비번",key="l_n4")
                e1, e2 = st.columns(2); ne = e1.text_input("이메일",key="l_n5"); nx = e2.text_input("전문분야",key="l_n6")
                ng = st.text_area("인사말", key="l_n7")
                if st.button("등록하기", key="l_reg_btn") and is_company_email(ne):
                    st.session_state.leaders_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "expertise":nx, "greeting":ng, "email":ne})
                    safe_save_leader("leaders", st.session_state.leaders_data); st.rerun()
            
            with st.expander("📋 기존 리더 수정/삭제", expanded=True):
                for i, m in enumerate(st.session_state.get('leaders_data', [])):
                    st.markdown(f"**[{m['name']}] 리더님**")
                    er1, er2, er3, er4 = st.columns(4)
                    un = er1.text_input("성함", m['name'], key=f"l_un_{i}"); up = er2.text_input("직급", m.get('position',''), key=f"l_up_{i}")
                    ut = er3.text_input("팀명", m.get('team',''), key=f"l_ut_{i}"); upw = er4.text_input("비번", m.get('pw',''), key=f"l_upw_{i}")
                    e1, e2 = st.columns(2)
                    ue = e1.text_input("이메일", m.get('email',''), key=f"l_ue_{i}"); ux = e2.text_input("전문분야", m.get('expertise',''), key=f"l_ux_{i}")
                    ug = st.text_area("인사말", m.get('greeting',''), key=f"l_ug_{i}")
                    if st.button("💾 저장", key=f"l_sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.leaders_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue,"expertise":ux,"greeting":ug})
                            safe_save_leader("leaders", st.session_state.leaders_data); st.success("수정됨"); st.rerun()
                    if st.button("❌ 삭제", key=f"l_dl_{i}"):
                        st.session_state.leaders_data.pop(i); safe_save_leader("leaders", st.session_state.leaders_data); st.rerun()
                    st.divider()
