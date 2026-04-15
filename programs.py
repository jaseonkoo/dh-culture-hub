import streamlit as st
import datetime
import uuid
import pandas as pd
import gspread
import smtplib
import time
from email.mime.text import MIMEText
from email.header import Header
from oauth2client.service_account import ServiceAccountCredentials

# [공통 설정]
WEEKS = ['월', '화', '수', '목', '금', '토', '일']
SYSTEM_URL = "https://dhfeed-culture.streamlit.app" 

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

# 콜백 함수 (비번 리셋)
def reset_pw_t2():
    if "m_pw_t2" in st.session_state: st.session_state["m_pw_t2"] = ""
def reset_pw_t3():
    if "m_pw_t3" in st.session_state: st.session_state["m_pw_t3"] = ""

def is_company_email(email): 
    return email.strip().lower().endswith("@daehanfeed.co.kr")

def generate_time_slots(start_time, end_time):
    slots = []
    curr = datetime.datetime.combine(datetime.date.today(), start_time)
    end = datetime.datetime.combine(datetime.date.today(), end_time)
    while curr <= end: 
        slots.append(curr.time()); curr += datetime.timedelta(minutes=30)
    return slots

def send_email(to_email, subject, body):
    SMTP_S, SMTP_P = "smtp.dooray.com", 465
    try:
        U, P = st.secrets["email"]["smtp_user"], st.secrets["email"]["smtp_password"]
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'], msg['From'], msg['To'] = Header(subject, 'utf-8'), Header(U), to_email
        with smtplib.SMTP_SSL(SMTP_S, SMTP_P) as server: 
            server.login(U, P); server.sendmail(U, to_email, msg.as_string())
    except Exception as e:
        st.error(f"메일 발송 오류: {e}")

# ==========================================
# 🤝 [사내 멘토링 프로그램] - 라스트 버전 100% 복원
# ==========================================
def run_mentoring():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .status-item { padding: 5px 10px; border-bottom: 1px solid #f0f2f6; line-height: 1.5; }
        </style>
    """, unsafe_allow_html=True)

    st.header("🤝 사내 멘토링")
    st.caption("대한사료 임직원 간의 성장을 돕는 실시간 소통 플랫폼")
    st.markdown("---")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_멘토링_DB")

    def get_sheet_data(sheet_name):
        try: doc = init_gspread(); return doc.worksheet(sheet_name).get_all_records()
        except: return []

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
                formatted_res.append(r)
            st.session_state.reservations = formatted_res
        except: pass

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
                ws.update([df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data(force=True)
        except: st.error("⚠️ 데이터 저장 오류")

    mentor_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('mentors_data', [])]

    # ==========================================
    # 📊 탭 구성 (Tab 1 ~ 4)
    # ==========================================
    tab1, tab2, tab3, tab4 = st.tabs(["🙋‍♂️ 멘티 예약 신청", "💼 멘토 일정 관리", "📋 멘토 예약 관리", "👑 관리자 메뉴"])

    # --- [🙋‍♂️ Tab 1: 멘티 예약 신청] ---
    with tab1:
        st.subheader("🗓️ 멘토링 예약 신청")
        if st.button("🔄 최신 현황 불러오기"): fetch_latest_data(force=True); st.rerun()

        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            all_slots = st.session_state.get('available_slots', [])
            if not all_slots: st.info("등록된 일정이 없습니다.")
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
        
        # ✨ 디자인 수정: 좌측/우측을 정확히 5:5 비율로 나누어 가로 길이를 완벽히 맞춥니다.
        col_left, col_right = st.columns(2)
        
        with col_left:
            m_n = st.text_input("신청자 성함", key="m_n_t1")
            m_p = st.text_input("직급", key="m_p_t1")
            selected_m = st.selectbox("멘토 선택", mentor_names, key="m_s_t1")
            sel_date = st.date_input("날짜 선택", datetime.date.today() + datetime.timedelta(days=1), key="d_s_t1")
            
        with col_right:
            m_t = st.text_input("팀명", key="m_t_t1")
            m_e = st.text_input("사내 이메일", key="m_e_t1", placeholder="example@daehanfeed.co.kr")
            if m_e and not is_company_email(m_e): st.error("🚫 @daehanfeed.co.kr 전용")
            
            # 멘토를 선택하면 우측 빈 공간에 프로필 카드가 나타납니다.
            if selected_m != "선택해주세요":
                p = next((m for m in st.session_state.get('mentors_data', []) if m['name'] == selected_m), None)
                if p: 
                    st.markdown(f"""
                    <div style="border: 2px solid #4A90E2; padding: 18px; border-radius: 12px; background-color: #f0f7ff; margin-top: 10px;">
                        <h4 style="margin-top:0; color: #1E3A8A;">🎖️ {p['name']} {p.get('position','')} 멘토</h4>
                        <p style="margin-bottom: 8px; font-size: 0.95em;">🏢 소속: {p.get('team','')}<br>🎯 전문분야: {p.get('expertise','')}</p>
                        <div style="background-color: white; padding: 10px; border-radius: 8px; border-left: 4px solid #4A90E2;">
                            <p style="font-size: 0.9em; margin: 0; color: #555;"><i>"{p.get('greeting','')}"</i></p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # 멘토가 선택되었을 때만 하단에 시간 및 주제 입력란이 전체 너비로 깔끔하게 열립니다.
        if selected_m != "선택해주세요":
            slots = [s for s in st.session_state.get('available_slots', []) if s['mentor']==selected_m and s['date']==sel_date]
            if slots:
                st.markdown("---")
                w_day_sel = WEEKS[sel_date.weekday()]
                st.info(f"📍 {slots[0].get('location','-')} | ⏰ {sel_date.strftime('%m/%d')}({w_day_sel}) {slots[0]['start']} ~ {slots[0]['end']}")
                p_t = generate_time_slots(slots[0]['start'], slots[0]['end'])
                
                ct1, ct2 = st.columns(2)
                ts = ct1.selectbox("시작 시간", p_t, format_func=lambda x: x.strftime("%H:%M"), key="ts_t1")
                te = ct2.selectbox("종료 시간", [t for t in p_t if t > ts] if [t for t in p_t if t > ts] else [ts], format_func=lambda x: x.strftime("%H:%M"), key="te_t1")
                
                topic = st.text_area("상담 주제 (필수)", key="tp_t1")
                
                if st.button("🚀 예약 신청하기", type="primary", use_container_width=True, key="bt1"):
                    if not m_n or not topic or not is_company_email(m_e): st.warning("정보를 정확히 입력해 주세요.")
                    else:
                        with st.status("📡 매칭 처리 중..."):
                            new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": slots[0].get('location',''), "status": "대기중"}
                            st.session_state.reservations.append(new_res); safe_save("reservations", st.session_state.reservations)
                            
                            slot_to_del = next((s for s in st.session_state.available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                            if slot_to_del:
                                st.session_state.available_slots.remove(slot_to_del); safe_save("slots", st.session_state.available_slots)

                            m_info = next((m for m in st.session_state.mentors_data if m['name']==selected_m), None)
                            if m_info and m_info.get('email'):
                                mail_subject = f"[대한사료 멘토링] 새로운 멘토링 신청이 접수되었습니다."
                                mail_body = f"안녕하세요, {selected_m} 멘토님!\n\n{m_n}님께서 멘토링을 신청하셨습니다.\n\n- 일시: {sel_date} ({ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')})\n- 주제: {topic}\n\n▶ 시스템 접속: {SYSTEM_URL}"
                                send_email(m_info['email'], mail_subject, mail_body)
                        st.balloons(); time.sleep(1); st.rerun()

    # --- [💼 Tab 2: 멘토 일정 관리] ---
    with tab2:
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
                            safe_save("slots", st.session_state.available_slots)
                        st.snow(); st.success("등록 완료!"); time.sleep(1); st.rerun()
            
                st.divider(); st.markdown(f"#### 🗑️ {m_log2} 멘토님의 등록 일정")
                my_slots = [x for x in st.session_state.get('available_slots', []) if x['mentor'] == m_log2]
                for i, s in enumerate(my_slots):
                    col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                    col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                    if col_b.button("삭제", key=f"del_s_{i}"):
                        st.session_state.available_slots.remove(s); safe_save("slots", st.session_state.available_slots); st.rerun()

    # --- [📋 Tab 3: 멘토 예약 관리 (거절 메일 + 슬롯 자동 복구 완벽 구현)] ---
    with tab3:
        st.subheader("📋 멘티 신청 현황 관리")
        m_sel3 = st.selectbox("본인 성함 선택", mentor_names, key="m_sel_t3", on_change=reset_pw_t3)
        if m_sel3 != "선택해주세요":
            minfo3 = next((m for m in st.session_state.get('mentors_data', []) if m['name']==m_sel3), None)
            if minfo3 and st.text_input("비번 확인", type="password", key="m_pw_t3") == str(minfo3['pw']):
                my_res = [x for x in st.session_state.get('reservations', []) if x['mentor']==m_sel3]
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
                                r['status']="승인됨"; safe_save("reservations", st.session_state.reservations)
                                if r.get('mentee_email'):
                                    body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 멘토링 예약이 승인되었습니다.\n\n- 일시: {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 멘토: {m_sel3} 멘토님\n\n감사합니다."
                                    send_email(r['mentee_email'], "[대한사료 멘토링] 신청하신 예약이 승인되었습니다!", body)
                                st.rerun()
                            
                            # ✨ 거절 시 메일 발송 + 슬롯 자동 복구
                            if b2.button("❌ 거절", key=f"no_{r['id']}", use_container_width=True):
                                r['status']="거절됨"
                                safe_save("reservations", st.session_state.reservations)
                                
                                # 1. 메일 발송 로직 복원
                                if r.get('mentee_email'):
                                    send_email(r['mentee_email'], "[대한사료 멘토링] 신청하신 예약이 반려되었습니다.", f"아쉽게도 {m_sel3} 멘토님이 예약을 반려하셨습니다.")
                                
                                # 2. 취소된 일정을 slots 시트로 복원하여 다시 신청 가능하게 만듦
                                st.session_state.available_slots.append({
                                    "mentor": r['mentor'], "date": r['date'], "start": r['start_time'], "end": r['end_time'], "location": r.get('location', '')
                                })
                                safe_save("slots", st.session_state.available_slots)
                                st.rerun()

    # --- [👑 Tab 4: 관리자 메뉴] ---
    with tab4:
        st.subheader("👑 인사총무팀 전용 관리 시스템")
        if "admin_logged_in" not in st.session_state:
            st.session_state.admin_logged_in = False
            
        if not st.session_state.admin_logged_in:
            aid, apw = st.text_input("ID", key="ad_id"), st.text_input("PW", type="password", key="ad_pw")
            if st.button("로그인") and aid == st.session_state.admin_info['id'] and apw == str(st.session_state.admin_info['pw']):
                st.session_state.admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃"): st.session_state.admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 멘토 신규 등록"):
                r1, r2, r3, r4 = st.columns(4)
                nm = r1.text_input("성함",key="n1")
                np = r2.text_input("직급",key="n2")
                nt = r3.text_input("팀명",key="n3")
                n_pw = r4.text_input("비번",key="n4")
                
                # ✨ 이메일과 전문분야를 5:5 비율로 설정 (st.columns(2))
                e1, e2 = st.columns(2)
                ne = e1.text_input("이메일",key="n5")
                nx = e2.text_input("전문분야",key="n6")
                
                ng = st.text_area("인사말", key="n7")
                if st.button("등록하기") and is_company_email(ne):
                    st.session_state.mentors_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "expertise":nx, "greeting":ng, "email":ne})
                    safe_save("mentors", st.session_state.mentors_data); st.rerun()
            
            with st.expander("📋 기존 멘토 수정/삭제", expanded=True):
                for i, m in enumerate(st.session_state.get('mentors_data', [])):
                    st.markdown(f"**[{m['name']}] 관리**")
                    er1, er2, er3, er4 = st.columns(4)
                    un = er1.text_input("성함", m['name'], key=f"un_{i}")
                    up = er2.text_input("직급", m.get('position',''), key=f"up_{i}")
                    ut = er3.text_input("팀명", m.get('team',''), key=f"ut_{i}")
                    upw = er4.text_input("비번", m.get('pw',''), key=f"upw_{i}")
                    
                    # ✨ 기존 멘토 수정 화면도 이메일/전문분야를 5:5 비율로 설정
                    e1, e2 = st.columns(2)
                    ue = e1.text_input("이메일", m.get('email',''), key=f"ue_{i}")
                    ux = e2.text_input("전문분야", m.get('expertise',''), key=f"ux_{i}")
                    
                    ug = st.text_area("인사말", m.get('greeting',''), key=f"ug_{i}")
                    if st.button("💾 저장", key=f"sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.mentors_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue,"expertise":ux,"greeting":ug})
                            safe_save("mentors", st.session_state.mentors_data); st.success("수정됨"); st.rerun()
                    if st.button("❌ 삭제", key=f"dl_{i}"):
                        st.session_state.mentors_data.pop(i); safe_save("mentors", st.session_state.mentors_data); st.rerun()
                    st.divider()

# ==========================================
# ☕ [리더와의 대화] / 🎓 [원데이 클래스]
# ==========================================
# ==========================================
# ☕ [리더와의 대화] - 멘토링과 동일한 5:5 완벽 대칭 구조
# ==========================================
def run_leader_talk():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .status-item { padding: 5px 10px; border-bottom: 1px solid #f0f2f6; line-height: 1.5; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("☕ 리더와의 대화")
    st.caption("경영진 및 팀장급 리더와 자유롭게 소통하며 비전을 나누는 시간입니다.")
    st.markdown("---")

    if "l_admin_logged_in" not in st.session_state:
        st.session_state.l_admin_logged_in = False

    def reset_pw_l2():
        if "l_pw_t2" in st.session_state: st.session_state["l_pw_t2"] = ""
    def reset_pw_l3():
        if "l_pw_t3" in st.session_state: st.session_state["l_pw_t3"] = ""

    # DB 연동 (리더대화 전용 DB)
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

    leader_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('leaders_data', [])]

    # 📊 탭 구성 (리더대화 전용)
    tab1, tab2, tab3, tab4 = st.tabs(["🙋‍♂️ 대화 신청", "💼 리더 일정 관리", "📋 신청 현황 관리", "👑 관리자 메뉴"])

    # --- [🙋‍♂️ Tab 1: 대화 신청] ---
    with tab1:
        st.subheader("🗓️ 리더와의 대화 신청")
        if st.button("🔄 최신 현황 불러오기", key="l_refresh_1"): fetch_latest_data_leader(force=True); st.rerun()

        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            all_slots = st.session_state.get('l_available_slots', [])
            if not all_slots: st.info("등록된 일정이 없습니다.")
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
        # 5:5 완벽 대칭 구조 유지
        col_left, col_right = st.columns(2)
        
        with col_left:
            m_n = st.text_input("신청자 성함", key="l_n_t1")
            m_p = st.text_input("직급", key="l_p_t1")
            selected_m = st.selectbox("리더 선택", leader_names, key="l_s_t1")
            sel_date = st.date_input("날짜 선택", datetime.date.today() + datetime.timedelta(days=1), key="l_d_t1")
            
        with col_right:
            m_t = st.text_input("팀명", key="l_t_t1")
            m_e = st.text_input("사내 이메일", key="l_e_t1", placeholder="example@daehanfeed.co.kr")
            if m_e and not is_company_email(m_e): st.error("🚫 @daehanfeed.co.kr 전용")
            
            if selected_m != "선택해주세요":
                p = next((m for m in st.session_state.get('leaders_data', []) if m['name'] == selected_m), None)
                if p: 
                    st.markdown(f"""
                    <div style="border: 2px solid #2ECC71; padding: 18px; border-radius: 12px; background-color: #EAFDF1; margin-top: 10px;">
                        <h4 style="margin-top:0; color: #1E8449;">👑 {p['name']} {p.get('position','')}</h4>
                        <p style="margin-bottom: 8px; font-size: 0.95em;">🏢 소속: {p.get('team','')}<br>🎯 담당/전문분야: {p.get('expertise','')}</p>
                        <div style="background-color: white; padding: 10px; border-radius: 8px; border-left: 4px solid #2ECC71;">
                            <p style="font-size: 0.9em; margin: 0; color: #555;"><i>"{p.get('greeting','')}"</i></p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        if selected_m != "선택해주세요":
            slots = [s for s in st.session_state.get('l_available_slots', []) if s['mentor']==selected_m and s['date']==sel_date]
            if slots:
                st.markdown("---")
                w_day_sel = WEEKS[sel_date.weekday()]
                st.info(f"📍 {slots[0].get('location','-')} | ⏰ {sel_date.strftime('%m/%d')}({w_day_sel}) {slots[0]['start']} ~ {slots[0]['end']}")
                p_t = generate_time_slots(slots[0]['start'], slots[0]['end'])
                
                ct1, ct2 = st.columns(2)
                ts = ct1.selectbox("시작 시간", p_t, format_func=lambda x: x.strftime("%H:%M"), key="l_ts_t1")
                te = ct2.selectbox("종료 시간", [t for t in p_t if t > ts] if [t for t in p_t if t > ts] else [ts], format_func=lambda x: x.strftime("%H:%M"), key="l_te_t1")
                
                topic = st.text_area("대화 희망 주제 (필수)", key="l_tp_t1")
                
                if st.button("🚀 신청하기", type="primary", use_container_width=True, key="l_bt1"):
                    if not m_n or not topic or not is_company_email(m_e): st.warning("정보를 정확히 입력해 주세요.")
                    else:
                        with st.status("📡 매칭 처리 중..."):
                            new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": slots[0].get('location',''), "status": "대기중"}
                            st.session_state.l_reservations.append(new_res); safe_save_leader("reservations", st.session_state.l_reservations)
                            
                            slot_to_del = next((s for s in st.session_state.l_available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                            if slot_to_del:
                                st.session_state.l_available_slots.remove(slot_to_del); safe_save_leader("slots", st.session_state.l_available_slots)

                            m_info = next((m for m in st.session_state.leaders_data if m['name']==selected_m), None)
                            if m_info and m_info.get('email'):
                                mail_subject = f"[대한사료 리더대화] 새로운 대화 신청이 접수되었습니다."
                                mail_body = f"안녕하세요, {selected_m} 리더님!\n\n{m_n}님께서 대화를 신청하셨습니다.\n\n- 일시: {sel_date} ({ts.strftime('%H:%M')} ~ {te.strftime('%H:%M')})\n- 주제: {topic}\n\n▶ 시스템 접속: {SYSTEM_URL}"
                                send_email(m_info['email'], mail_subject, mail_body)
                        st.balloons(); time.sleep(1); st.rerun()

    # --- [💼 Tab 2: 리더 일정 관리] ---
    with tab2:
        st.subheader("💼 나의 일정 관리")
        m_log2 = st.selectbox("본인 성함 선택", leader_names, key="l_log_t2", on_change=reset_pw_l2)
        if m_log2 != "선택해주세요":
            minfo = next((m for m in st.session_state.get('leaders_data', []) if m['name']==m_log2), None)
            if minfo and st.text_input("비밀번호 입력", type="password", key="l_pw_t2") == str(minfo['pw']):
                c2_1, c2_2, c2_3, c2_4 = st.columns(4)
                dv, sv, ev, lv = c2_1.date_input("날짜", key="l_sd_t2"), c2_2.time_input("시작", datetime.time(0,0), key="l_ss_t2"), c2_3.time_input("종료", datetime.time(0,0), key="l_se_t2"), c2_4.text_input("장소", key="l_sl_t2")
                
                if st.button("🗓️ 일정 등록하기", type="primary", use_container_width=True, key="l_sb_t2"):
                    is_duplicate = False
                    for r in st.session_state.get('l_reservations', []):
                        if r['mentor'] == m_log2 and r['date'] == dv:
                            if not (ev <= r['start_time'] or sv >= r['end_time']): is_duplicate = True; break
                    if not is_duplicate:
                        for s in st.session_state.get('l_available_slots', []):
                            if s['mentor'] == m_log2 and s['date'] == dv:
                                if not (ev <= s['start'] or sv >= s['end']): is_duplicate = True; break
                    
                    if is_duplicate: st.error("🚫 중복된 시간이 존재합니다.")
                    elif sv >= ev: st.error("🚫 시간 설정 오류")
                    else:
                        with st.status("📡 저장 중..."):
                            st.session_state.l_available_slots.append({"mentor": m_log2, "date": dv, "start": sv, "end": ev, "location": lv})
                            safe_save_leader("slots", st.session_state.l_available_slots)
                        st.snow(); st.success("등록 완료!"); time.sleep(1); st.rerun()
            
                st.divider(); st.markdown(f"#### 🗑️ {m_log2} 리더님의 등록 일정")
                my_slots = [x for x in st.session_state.get('l_available_slots', []) if x['mentor'] == m_log2]
                for i, s in enumerate(my_slots):
                    col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                    col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                    if col_b.button("삭제", key=f"l_del_s_{i}"):
                        st.session_state.l_available_slots.remove(s); safe_save_leader("slots", st.session_state.l_available_slots); st.rerun()

    # --- [📋 Tab 3: 리더 예약 관리] ---
    with tab3:
        st.subheader("📋 구성원 신청 현황 관리")
        m_sel3 = st.selectbox("본인 성함 선택", leader_names, key="l_sel_t3", on_change=reset_pw_l3)
        if m_sel3 != "선택해주세요":
            minfo3 = next((m for m in st.session_state.get('leaders_data', []) if m['name']==m_sel3), None)
            if minfo3 and st.text_input("비번 확인", type="password", key="l_pw_t3") == str(minfo3['pw']):
                my_res = [x for x in st.session_state.get('l_reservations', []) if x['mentor']==m_sel3]
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
                                    body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 리더와의 대화가 승인되었습니다.\n\n- 일시: {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 리더: {m_sel3} 리더님\n\n감사합니다."
                                    send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 승인되었습니다!", body)
                                st.rerun()
                            
                            if b2.button("❌ 거절", key=f"l_no_{r['id']}", use_container_width=True):
                                r['status']="거절됨"; safe_save_leader("reservations", st.session_state.l_reservations)
                                if r.get('mentee_email'):
                                    send_email(r['mentee_email'], "[대한사료 리더대화] 신청하신 예약이 반려되었습니다.", f"아쉽게도 {m_sel3} 리더님이 예약을 반려하셨습니다. 다른 일정을 선택해 주세요.")
                                
                                st.session_state.l_available_slots.append({
                                    "mentor": r['mentor'], "date": r['date'], "start": r['start_time'], "end": r['end_time'], "location": r.get('location', '')
                                })
                                safe_save_leader("slots", st.session_state.l_available_slots)
                                st.rerun()

    # --- [👑 Tab 4: 관리자 메뉴] ---
    with tab4:
        st.subheader("👑 인사총무팀 전용 관리 시스템")
        if not st.session_state.l_admin_logged_in:
            aid, apw = st.text_input("ID", key="l_ad_id"), st.text_input("PW", type="password", key="l_ad_pw")
            if st.button("로그인", key="l_login_btn") and aid == st.session_state.l_admin_info['id'] and apw == str(st.session_state.l_admin_info['pw']):
                st.session_state.l_admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃", key="l_logout_btn"): st.session_state.l_admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 리더 신규 등록"):
                r1, r2, r3, r4 = st.columns(4)
                nm = r1.text_input("성함",key="l_n1")
                np = r2.text_input("직급",key="l_n2")
                nt = r3.text_input("팀명",key="l_n3")
                n_pw = r4.text_input("비번",key="l_n4")
                
                e1, e2 = st.columns(2)
                ne = e1.text_input("이메일",key="l_n5")
                nx = e2.text_input("전문분야",key="l_n6")
                
                ng = st.text_area("인사말", key="l_n7")
                if st.button("등록하기", key="l_reg_btn") and is_company_email(ne):
                    st.session_state.leaders_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "expertise":nx, "greeting":ng, "email":ne})
                    safe_save_leader("leaders", st.session_state.leaders_data); st.rerun()
            
            with st.expander("📋 기존 리더 수정/삭제", expanded=True):
                for i, m in enumerate(st.session_state.get('leaders_data', [])):
                    st.markdown(f"**[{m['name']}] 리더님**")
                    er1, er2, er3, er4 = st.columns(4)
                    un = er1.text_input("성함", m['name'], key=f"l_un_{i}")
                    up = er2.text_input("직급", m.get('position',''), key=f"l_up_{i}")
                    ut = er3.text_input("팀명", m.get('team',''), key=f"l_ut_{i}")
                    upw = er4.text_input("비번", m.get('pw',''), key=f"l_upw_{i}")
                    
                    e1, e2 = st.columns(2)
                    ue = e1.text_input("이메일", m.get('email',''), key=f"l_ue_{i}")
                    ux = e2.text_input("전문분야", m.get('expertise',''), key=f"l_ux_{i}")
                    
                    ug = st.text_area("인사말", m.get('greeting',''), key=f"l_ug_{i}")
                    if st.button("💾 저장", key=f"l_sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.leaders_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue,"expertise":ux,"greeting":ug})
                            safe_save_leader("leaders", st.session_state.leaders_data); st.success("수정됨"); st.rerun()
                    if st.button("❌ 삭제", key=f"l_dl_{i}"):
                        st.session_state.leaders_data.pop(i); safe_save_leader("leaders", st.session_state.leaders_data); st.rerun()
                    st.divider()

# ==========================================
# 🎓 [직무 원데이 클래스] - 개설, 신청, 명단 확인 통합
# ==========================================
# ==========================================
# 🎓 [직무 원데이 클래스] - 강사/관리자 권한 분리 적용
# ==========================================
def run_class():
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        .class-card { border: 2px solid #F39C12; padding: 20px; border-radius: 12px; background-color: #FFF9F0; margin-bottom: 15px; }
        </style>
    """, unsafe_allow_html=True)

    st.header("🎓 직무 원데이 클래스")
    st.caption("사내 전문가에게 직접 배우는 실무 노하우, 함께 성장하는 직무 교육 플랫폼")
    st.markdown("---")

    if "c_admin_logged_in" not in st.session_state:
        st.session_state.c_admin_logged_in = False

    def reset_pw_c2():
        if "c_pw_t2" in st.session_state: st.session_state["c_pw_t2"] = ""

    # DB 연동
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread_class():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_원데이클래스_DB")

    def get_sheet_data_class(sheet_name):
        try: doc = init_gspread_class(); return doc.worksheet(sheet_name).get_all_records()
        except: return []

    def fetch_latest_data_class(force=False):
        if force: st.cache_data.clear()
        try:
            st.session_state.classes_data = get_sheet_data_class("classes")
            st.session_state.c_reservations = get_sheet_data_class("applications")
            st.session_state.instructors_data = get_sheet_data_class("instructors") # 강사 DB 추가
            ad_list = get_sheet_data_class("admin")
            st.session_state.c_admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}
        except: pass

    fetch_latest_data_class()

    def safe_save_class(ws_name, data_list):
        try:
            doc = init_gspread_class(); ws = doc.worksheet(ws_name); ws.clear()
            if data_list:
                df = pd.DataFrame(data_list)
                df = df.fillna("")
                ws.update([df.columns.values.tolist()] + df.values.tolist())
            fetch_latest_data_class(force=True)
        except: st.error("⚠️ 데이터 저장 오류")

    instructor_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('instructors_data', [])]

    # 📊 탭 구성
    tab1, tab2, tab3 = st.tabs(["📖 수강 신청", "👨‍🏫 강사 전용 (개설/관리)", "👑 관리자 메뉴"])

    # --- [📖 Tab 1: 수강 신청 (임직원 모두 볼 수 있음)] ---
    with tab1:
        st.subheader("📚 오픈된 클래스 목록")
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
                                u_n = c1.text_input("성함")
                                u_p = c1.text_input("직급")
                                u_t = c2.text_input("팀명")
                                u_e = c2.text_input("사내 이메일")
                                
                                if st.form_submit_button("신청서 제출"):
                                    if u_n and is_company_email(u_e):
                                        new_app = {
                                            "id": str(uuid.uuid4())[:8],
                                            "class_id": c['id'],
                                            "class_title": c['title'],
                                            "user_name": u_n,
                                            "user_pos": u_p,
                                            "user_team": u_t,
                                            "user_email": u_e,
                                            "status": "신청완료"
                                        }
                                        st.session_state.c_reservations.append(new_app)
                                        safe_save_class("applications", st.session_state.c_reservations)
                                        st.balloons(); st.success("신청이 완료되었습니다!"); time.sleep(1.5); st.rerun()
                                    else:
                                        st.error("성함과 이메일 형식을 확인해 주세요.")

    # --- [👨‍🏫 Tab 2: 사내 강사 전용 공간 (자물쇠 적용)] ---
    with tab2:
        st.subheader("🔒 강사 전용 클래스 관리")
        c_log = st.selectbox("본인 성함 선택 (사전 등록된 강사만 가능)", instructor_names, key="c_log_t2", on_change=reset_pw_c2)
        
        if c_log != "선택해주세요":
            minfo = next((m for m in st.session_state.get('instructors_data', []) if m['name']==c_log), None)
            if minfo and st.text_input("비밀번호 입력", type="password", key="c_pw_t2") == str(minfo['pw']):
                
                # 비밀번호가 맞으면 숨겨진 메뉴가 나타납니다!
                mode = st.radio("작업 선택", ["신규 클래스 오픈하기", "내 클래스 신청자 명단 보기"], horizontal=True)
                
                if mode == "신규 클래스 오픈하기":
                    with st.form("new_class_form"):
                        title = st.text_input("강의명 (예: 실무 엑셀 마스터)")
                        st.info(f"👨‍🏫 배정된 강사: **{c_log}** (자동입력)")
                        c1, c2 = st.columns(2)
                        d_val = c1.date_input("강의 날짜")
                        t_val = c1.text_input("강의 시간 (예: 14:00~16:00)")
                        loc = c2.text_input("장소 (예: 본사 3층 대회의실)")
                        capa = c2.number_input("모집 정원", min_value=1, value=15)
                        desc = st.text_area("클래스 설명 및 준비물 (상세히 적어주세요)")
                        
                        if st.form_submit_button("클래스 오픈하기"):
                            if not title:
                                st.error("⚠️ 강의명을 입력해 주세요!")
                            else:
                                with st.status("📡 클래스 개설 중..."):
                                    new_class = {
                                        "id": str(uuid.uuid4())[:8],
                                        "title": title,
                                        "instructor": c_log, # 강사 이름 강제 고정
                                        "date": str(d_val),
                                        "time": t_val,
                                        "location": loc,
                                        "capacity": capa,
                                        "description": desc,
                                        "status": "모집중"
                                    }
                                    st.session_state.classes_data.append(new_class)
                                    safe_save_class("classes", st.session_state.classes_data)
                                st.balloons()
                                st.success(f"🎉 성공! '{title}' 클래스가 완벽하게 오픈되었습니다.")
                                time.sleep(1.5)
                                st.rerun()
                
                else: # 내 클래스 명단 보기
                    my_classes = [c for c in st.session_state.get('classes_data', []) if c['instructor'] == c_log]
                    if not my_classes:
                        st.info("아직 개설하신 클래스가 없습니다.")
                    else:
                        sel_class = st.selectbox("확인할 클래스 선택", [c['title'] for c in my_classes])
                        target_class = next(c for c in my_classes if c['title'] == sel_class)
                        applicants = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == target_class['id']]
                        
                        st.write(f"### 📋 '{sel_class}' 신청자 리스트 (총 {len(applicants)}명)")
                        if applicants:
                            df_app = pd.DataFrame(applicants)[['user_name', 'user_pos', 'user_team', 'user_email']]
                            df_app.columns = ['성함', '직급', '소속팀', '이메일'] # 표 헤더 한글화
                            st.dataframe(df_app, use_container_width=True)
                        else:
                            st.info("아직 신청자가 없습니다.")

    # --- [👑 Tab 3: 인사총무팀 관리자 메뉴] ---
    with tab3:
        st.subheader("👑 원데이 클래스 통합 관리 시스템")
        if not st.session_state.c_admin_logged_in:
            aid, apw = st.text_input("ID", key="c_ad_id"), st.text_input("PW", type="password", key="c_ad_pw")
            if st.button("로그인", key="c_login_btn") and aid == st.session_state.c_admin_info['id'] and apw == str(st.session_state.c_admin_info['pw']):
                st.session_state.c_admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃", key="c_logout_btn"): st.session_state.c_admin_logged_in = False; st.rerun()
            
            # 관리자 권한 1: 사내 강사 권한 부여
            with st.expander("👨‍🏫 [권한 관리] 사내 강사 신규 등록"):
                r1, r2, r3, r4 = st.columns(4)
                nm = r1.text_input("성함",key="c_n1"); np = r2.text_input("직급",key="c_n2")
                nt = r3.text_input("팀명",key="c_n3"); n_pw = r4.text_input("초기 비번",key="c_n4")
                ne = st.text_input("사내 이메일",key="c_n5")
                
                if st.button("강사 권한 부여", key="c_reg_btn") and is_company_email(ne):
                    st.session_state.instructors_data.append({"name":nm, "position":np, "team":nt, "pw":n_pw, "email":ne})
                    safe_save_class("instructors", st.session_state.instructors_data); st.success("등록 완료!"); st.rerun()

            with st.expander("📋 [권한 관리] 기존 강사 수정/삭제", expanded=False):
                for i, m in enumerate(st.session_state.get('instructors_data', [])):
                    st.markdown(f"#### 👤 {m['name']} 강사님 권한 관리")
                    er1, er2, er3, er4 = st.columns(4)
                    un = er1.text_input("성함", m['name'], key=f"c_un_{i}"); up = er2.text_input("직급", m.get('position',''), key=f"c_up_{i}")
                    ut = er3.text_input("팀명", m.get('team',''), key=f"c_ut_{i}"); upw = er4.text_input("비번", m.get('pw',''), key=f"c_upw_{i}")
                    ue = st.text_input("이메일", m.get('email',''), key=f"c_ue_{i}")
                    
                    if st.button("💾 저장", key=f"c_sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.instructors_data[i].update({"name":un,"position":up,"team":ut,"pw":upw,"email":ue})
                            safe_save_class("instructors", st.session_state.instructors_data); st.success("수정됨"); st.rerun()
                    if st.button("❌ 권한 회수(삭제)", key=f"c_dl_{i}"):
                        st.session_state.instructors_data.pop(i); safe_save_class("instructors", st.session_state.instructors_data); st.rerun()
                    st.divider()

            # 관리자 권한 2: 전체 클래스 명단 조회 및 상태 제어
            with st.expander("📚 [운영 관리] 전체 클래스 명단 조회 및 제어", expanded=True):
                st.info("개설된 모든 클래스의 신청 명단을 확인하고 상태를 제어합니다.")
                for i, c in enumerate(st.session_state.get('classes_data', [])):
                    # 클래스 정보 요약
                    current_apps = [a for a in st.session_state.get('c_reservations', []) if a['class_id'] == c['id']]
                    col_info, col_btn1, col_btn2 = st.columns([3, 1, 1])
                    col_info.markdown(f"**[{c['status']}] {c['title']}** (강사: {c['instructor']} | 신청: {len(current_apps)}/{c['capacity']}명)")
                    
                    if col_btn1.button("모집/마감 전환", key=f"c_tog_{i}"):
                        c['status'] = '마감' if c['status'] == '모집중' else '모집중'
                        safe_save_class("classes", st.session_state.classes_data); st.rerun()
                    if col_btn2.button("클래스 삭제", key=f"c_del_{i}"):
                        st.session_state.classes_data.pop(i)
                        safe_save_class("classes", st.session_state.classes_data); st.rerun()
                    
                    # 관리자용 전체 명단 테이블
                    if current_apps:
                        df_adm = pd.DataFrame(current_apps)[['user_name', 'user_pos', 'user_team', 'user_email']]
                        df_adm.columns = ['성함', '직급', '소속팀', '이메일']
                        st.dataframe(df_adm, use_container_width=True)
                    else:
                        st.caption("신청자 없음")
                    st.markdown("---")
