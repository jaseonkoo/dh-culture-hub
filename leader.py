import requests
import json
import pandas as pd
import gspread
import datetime
import uuid
import time
import streamlit as st
import caldav
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

    @st.cache_data(ttl=60, show_spinner=False)
    def get_sheet_data_leader(sheet_name):
        try: 
            doc = init_gspread_leader()
            return doc.worksheet(sheet_name).get_all_records()
        except Exception as e:
            st.error(f"⚠️ '{sheet_name}' 데이터를 불러오는 중 오류 발생: {e}")
            return []

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
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist())
            return True
        except Exception as e: 
            st.error(f"⚠️ 데이터 저장 오류 ({ws_name}): {e}")
            return False

    # =========================================================
    # 📆 [두레이 캘린더 자동 탐색 및 연동 로직 적용]
    # =========================================================
    def get_dooray_calendar_leader():
        cal_id = st.secrets.get("dooray_cal_id")
        cal_pw = st.secrets.get("dooray_cal_pw")
        
        if not cal_id or not cal_pw:
            st.error("⚠️ Secrets에 두레이 계정 정보가 설정되지 않았습니다.")
            return None

        urls_to_try = [
            f"https://caldav.dooray.com/caldav/principals/{cal_id}/",
            "https://caldav.dooray.com/caldav/",
            "https://caldav.dooray.com"
        ]
        
        last_error = ""
        for test_url in urls_to_try:
            try:
                client = caldav.DAVClient(url=test_url, username=cal_id, password=cal_pw)
                principal = client.principal()
                calendars = principal.calendars()
                
                if calendars:
                    for c in calendars:
                        if hasattr(c, 'name') and c.name in ["리더와의 대화", "멘토링&코칭"]:
                            return c
                    return calendars[0]
            except Exception as e:
                last_error = str(e)
                continue
                
        st.error(f"⚠️ 캘린더 서버 접속 에러 (마지막 에러: {last_error})")
        return None

    def add_dooray_calendar_event_leader(name, date_obj, start_time, end_time, location, prefix="[예약가능]"):
        try:
            my_calendar = get_dooray_calendar_leader()
            if not my_calendar: return False
            
            start_dt = datetime.datetime.combine(date_obj, start_time).strftime("%Y%m%dT%H%M%S")
            end_dt = datetime.datetime.combine(date_obj, end_time).strftime("%Y%m%dT%H%M%S")
            title = f"{prefix} {name} 리더님"
            
            event_uid = str(uuid.uuid4())
            dt_stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            
            vcal_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Daehanfeed Culture Hub//EN
BEGIN:VEVENT
UID:{event_uid}
DTSTAMP:{dt_stamp}
SUMMARY:{title}
DTSTART;TZID=Asia/Seoul:{start_dt}
DTEND;TZID=Asia/Seoul:{end_dt}
LOCATION:{location}
DESCRIPTION:조직문화 플랫폼에서 신청 가능한 리더와의 대화 일정입니다.\\nhttps://dhfeed-culture.streamlit.app/
END:VEVENT
END:VCALENDAR"""
            
            try:
                my_calendar.save_event(vcal_data)
                return True
            except caldav.lib.error.PutError as pe:
                if "200" in str(pe) or "201" in str(pe) or "204" in str(pe):
                    return True
                else:
                    st.error(f"⚠️ 캘린더 일정 등록 에러: {pe}")
                    return False
        except Exception as e:
            st.error(f"⚠️ 캘린더 시스템 에러: {e}")
            return False

    def delete_dooray_calendar_event_leader(name, date_obj):
        try:
            my_calendar = get_dooray_calendar_leader()
            if not my_calendar: return False
            
            start_dt = datetime.datetime.combine(date_obj, datetime.time.min)
            end_dt = start_dt + datetime.timedelta(days=1)
            
            events = my_calendar.date_search(start=start_dt, end=end_dt)
            for event in events:
                if name in event.data: 
                    event.delete()
            return True
        except Exception as e:
            st.error(f"⚠️ 캘린더 일정 삭제 에러: {e}")
            return False

    # ✨ [추가] 과거 미예약 캘린더 일정 자동 삭제 함수
    def auto_cleanup_past_dooray_events_leader():
        today_str = str(datetime.date.today())
        # 속도 저하를 막기 위해 해당 세션에서는 하루에 한 번만 백그라운드 체크 실행
        if st.session_state.get('l_last_cal_cleanup') == today_str:
            return 
            
        try:
            my_calendar = get_dooray_calendar_leader()
            if not my_calendar: return
            
            # 30일 전부터 ~ 어제 자정(오늘 시작 전)까지의 일정 검색
            start_dt = datetime.datetime.now() - datetime.timedelta(days=30)
            end_dt = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
            
            events = my_calendar.date_search(start=start_dt, end=end_dt)
            for event in events:
                # 캘린더 데이터 내에 '[예약가능]' 태그가 있는 경우에만 삭제 ([승인완료]는 통과)
                if "[예약가능]" in event.data:
                    event.delete()
                    
            st.session_state.l_last_cal_cleanup = today_str
        except Exception as e:
            pass # 백그라운드 자동 정리는 에러가 나도 사용자에게 알리지 않고 조용히 넘어갑니다.

    # 🚀 페이지 로드 시 백그라운드 자동 정리 실행
    auto_cleanup_past_dooray_events_leader()

    # =========================================================

    def send_telegram_noti(name, date, start, end, location):
        try:
            bot_token = st.secrets["telegram_bot_token"]
        except KeyError:
            st.error("⚠️ 스트림릿 Secrets에 텔레그램 토큰이 설정되지 않았습니다.")
            return False
            
        chat_id = "-1004464463229" 
        
        start_str = start.strftime('%H:%M') if hasattr(start, 'strftime') else str(start)[:5]
        end_str = end.strftime('%H:%M') if hasattr(end, 'strftime') else str(end)[:5]
        
        text = (f"📢 *[{name} 리더님]*의 새로운 대화 일정이 오픈되었습니다!\n\n"
                f"  • 📅 일시 : {date} ({start_str} ~ {end_str})\n"
                f"  • 📍 장소 : {location}\n\n"
                f"▶ 지금 바로 조직문화 플랫폼에 접속해서 대화를 신청해 보세요!\n"
                f"      (https://dhfeed-culture.streamlit.app)")
                
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        try:
            res = requests.post(url, json=payload)
            if res.status_code != 200:
                st.error(f"⚠️ 텔레그램 발송 실패 원인: {res.text}")
                return False
            return True
        except Exception as e:
            st.error(f"⚠️ 통신 에러: {str(e)}")
            return False

    today_date_check = datetime.date.today()
    active_leaders = {s['mentor'] for s in st.session_state.get('l_available_slots', []) if s['date'] >= today_date_check}
    leader_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('leaders_data', []) if m['name'] in active_leaders]

    main_tab_mentee, main_tab_leader, main_tab_admin = st.tabs(["🙋‍♂️ 구성원 대화 신청", "💼 리더 공간", "👑 관리자 메뉴"])

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
                            with st.status("📡 매칭 처리 중...") as status:
                                new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": loc, "status": "대기중"}
                                st.session_state.l_reservations.append(new_res)
                                save1 = safe_save_leader("reservations", st.session_state.l_reservations)
                                
                                slot_to_del = next((s for s in st.session_state.l_available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                                save2 = True
                                if slot_to_del:
                                    st.session_state.l_available_slots.remove(slot_to_del)
                                    save2 = safe_save_leader("slots", st.session_state.l_available_slots)

                                m_info = next((m for m in st.session_state.leaders_data if m['name']==selected_m), None)
                                mail_ok = False
                                if m_info and m_info.get('email'):
                                    mail_subject = f"[대한사료 리더대화] 새로운 대화 신청이 접수되었습니다."
                                    mail_body = f"안녕하세요, {selected_m} 리더님!\n\n{m_n}님께서 대화를 신청하셨습니다.\n\n- 일시 : {sel_date} ({ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')})\n- 주제 : {topic}\n\n▶ 시스템 접속: {SYSTEM_URL}"
                                    mail_ok = send_email(m_info['email'], mail_subject, mail_body)

                                if save1 and save2:
                                    status.update(label="처리 완료!", state="complete")
                                    st.balloons()
                                    if mail_ok:
                                        st.success("✅ 신청이 완료되었으며, 리더님께 알림 메일이 발송되었습니다.")
                                    else:
                                        st.warning("⚠️ 예약은 정상 저장되었으나 메일 발송에 실패했습니다.")
                                    time.sleep(3)
                                    fetch_latest_data_leader(force=True) 
                                    st.rerun()
                                else:
                                    status.update(label="처리 실패", state="error")
                                    st.error("⚠️ 데이터 저장에 실패하여 신청이 취소되었습니다.")

    with main_tab_leader:
        sub_tab_schedule, sub_tab_manage, sub_tab_info = st.tabs(["🗓️ 일정 등록 및 관리", "📋 신청 현황 관리", "⚙️ 리더 정보 변경"])
        
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
                            is_noti_success = False
                            with st.status("📡 저장 중..."):
                                st.session_state.l_available_slots.append({"mentor": l_name_1, "date": dv, "start": sv, "end": ev, "location": lv})
                                if safe_save_leader("slots", st.session_state.l_available_slots):
                                    
                                    add_dooray_calendar_event_leader(l_name_1, dv, sv, ev, lv)
                                    is_noti_success = send_telegram_noti(l_name_1, dv, sv, ev, lv)
                            
                            if is_noti_success:
                                st.snow()
                                st.success("등록 완료!")
                                time.sleep(2)
                                fetch_latest_data_leader(force=True)
                                st.rerun()
                            else:
                                st.warning("일정은 저장되었으나 텔레그램 알림 발송에 실패했습니다.")
            
                    st.divider(); st.markdown(f"#### 🗑️ {l_name_1} 리더님의 등록 일정")
                    my_slots = [x for x in st.session_state.get('l_available_slots', []) if x['mentor'] == l_name_1]
                    for i, s in enumerate(my_slots):
                        col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                        col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                        if col_b.button("삭제", key=f"l_del_s_{i}"):
                            st.session_state.l_available_slots.remove(s)
                            if safe_save_leader("slots", st.session_state.l_available_slots):
                                delete_dooray_calendar_event_leader(l_name_1, s['date'])
                                fetch_latest_data_leader(force=True)
                                st.rerun()

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
                                    r['status']="승인됨"
                                    if safe_save_leader("reservations", st.session_state.l_reservations):
                                        if r.get('mentee_email'):
                                            body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 리더와의 대화가 승인되었습니다.\n\n- 일시 : {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 리더 : {l_name_2} 리더님\n\n감사합니다."
                                            send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 승인되었습니다!", body)
                                            
                                        delete_dooray_calendar_event_leader(l_name_2, r['date'])
                                        add_dooray_calendar_event_leader(l_name_2, r['date'], r['start_time'], r['end_time'], r.get('location', '-'), prefix="[승인완료]")
                                        
                                        fetch_latest_data_leader(force=True)
                                        st.rerun()
                            
                                if b2.button("❌ 거절", key=f"l_no_{r['id']}", use_container_width=True):
                                    r['status']="거절됨"
                                    if safe_save_leader("reservations", st.session_state.l_reservations):
                                        if r.get('mentee_email'):
                                            send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 반려되었습니다.", f"아쉽게도 {l_name_2} 리더님이 예약을 반려하셨습니다. 다른 일정을 선택해 주세요.")
                                        st.session_state.l_available_slots.append({
                                            "mentor": r['mentor'], "date": r['date'], "start": r['start_time'], "end": r['end_time'], "location": r.get('location', '')
                                        })
                                        safe_save_leader("slots", st.session_state.l_available_slots)
                                        
                                        delete_dooray_calendar_event_leader(l_name_2, r['date'])
                                        add_dooray_calendar_event_leader(l_name_2, r['date'], r['start_time'], r['end_time'], r.get('location', '미정'), prefix="[예약가능]")
                                        
                                        fetch_latest_data_leader(force=True)
                                        st.rerun()

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
                                    if safe_save_leader("leaders", st.session_state.leaders_data):
                                        st.success("✅ 리더 정보가 성공적으로 변경되었습니다!")
                                        time.sleep(1.5)
                                        st.rerun()

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
                    if safe_save_leader("leaders", st.session_state.leaders_data):
                        fetch_latest_data_leader(force=True); st.rerun()
            
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
                            if safe_save_leader("leaders", st.session_state.leaders_data): 
                                st.success("수정됨")
                                fetch_latest_data_leader(force=True)
                                st.rerun()
                    if st.button("❌ 삭제", key=f"l_dl_{i}"):
                        st.session_state.leaders_data.pop(i)
                        if safe_save_leader("leaders", st.session_state.leaders_data): 
                            fetch_latest_data_leader(force=True)
                            st.rerun()
                    st.divider()
            
            with st.expander("🛠️ 시스템 관리 (기존 일정 캘린더 일괄 등록 및 정리)"):
                st.info("💡 캘린더 연동 기능이 적용되기 전에 등록된 '예약 가능' 및 '승인 완료' 일정들을 두레이 캘린더로 일괄 전송하거나, 과거의 미예약 일정을 수동으로 즉시 정리할 수 있습니다.")
                st.warning("🚨 주의: 버튼을 여러 번 누르면 캘린더에 일정이 중복으로 등록될 수 있으니 딱 한 번만 눌러주세요!")
                
                if st.button("🔄 캘린더 일괄 동기화 실행", key="l_sync_btn", type="primary", use_container_width=True):
                    with st.status("📡 기존 일정들을 캘린더로 전송하는 중...") as sync_status:
                        success_count = 0
                        today_date = datetime.date.today()
                        
                        for s in st.session_state.get('l_available_slots', []):
                            if s['date'] >= today_date:
                                if add_dooray_calendar_event_leader(s['mentor'], s['date'], s['start'], s['end'], s.get('location', '-'), prefix="[예약가능]"):
                                    success_count += 1
                        
                        for r in st.session_state.get('l_reservations', []):
                            if r['date'] >= today_date and r['status'] == "승인됨":
                                if add_dooray_calendar_event_leader(r['mentor'], r['date'], r['start_time'], r['end_time'], r.get('location', '-'), prefix="[승인완료]"):
                                    success_count += 1
                        
                        sync_status.update(label=f"✅ 총 {success_count}건의 일정이 두레이 캘린더에 성공적으로 등록되었습니다!", state="complete")
                        st.balloons()
                        
                # ✨ [추가] 수동으로 과거 미예약 일정 삭제하는 버튼 
                st.divider()
                st.markdown("#### 🗑️ 캘린더 청소하기")
                if st.button("🧹 지난 미예약 캘린더 일정 일괄 삭제", key="l_clean_btn", use_container_width=True):
                    with st.status("📡 과거 캘린더 일정을 정리하는 중...") as clean_status:
                        try:
                            my_calendar = get_dooray_calendar_leader()
                            if my_calendar:
                                start_dt = datetime.datetime.now() - datetime.timedelta(days=30)
                                end_dt = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
                                events = my_calendar.date_search(start=start_dt, end=end_dt)
                                del_count = 0
                                for event in events:
                                    if "[예약가능]" in event.data:
                                        event.delete()
                                        del_count += 1
                                clean_status.update(label=f"✅ 총 {del_count}건의 과거 [예약가능] 일정이 깔끔하게 삭제되었습니다!", state="complete")
                            else:
                                clean_status.update(label="⚠️ 캘린더 연결에 실패했습니다.", state="error")
                        except Exception as e:
                            clean_status.update(label=f"⚠️ 삭제 중 에러 발생: {e}", state="error")
