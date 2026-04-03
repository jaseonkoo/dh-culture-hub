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

# --- [보조 함수들] ---
def is_company_email(email): 
    return email.strip().lower().endswith("@daehanfeed.co.kr")

def generate_time_slots(start_time, end_time):
    slots = []
    curr = datetime.datetime.combine(datetime.date.today(), start_time)
    end = datetime.datetime.combine(datetime.date.today(), end_time)
    while curr <= end: 
        slots.append(curr.time())
        curr += datetime.timedelta(minutes=30)
    return slots

def send_email(to_email, subject, body):
    SMTP_S, SMTP_P = "smtp.dooray.com", 465
    try:
        U, P = st.secrets["email"]["smtp_user"], st.secrets["email"]["smtp_password"]
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'], msg['From'], msg['To'] = Header(subject, 'utf-8'), Header(U), to_email
        with smtplib.SMTP_SSL(SMTP_S, SMTP_P) as server: 
            server.login(U, P)
            server.sendmail(U, to_email, msg.as_string())
    except: pass

def reset_pw_t2():
    if "m_pw_t2" in st.session_state: st.session_state["m_pw_t2"] = ""
def reset_pw_t3():
    if "m_pw_t3" in st.session_state: st.session_state["m_pw_t3"] = ""

# ==========================================
# 🤝 [사내 멘토링 프로그램] - 차장님 "라스트 버전" 풀 이식
# ==========================================
def run_mentoring():
    # 📱 모바일 최적화 및 스타일
    st.markdown("""
        <style>
        .stTextInput, .stSelectbox, .stDateInput, .stTextArea, .stTimeInput { margin-bottom: 12px !important; }
        @media (max-width: 768px) {
            div[data-testid="stExpander"] details summary p { display: block !important; visibility: visible !important; line-height: 1.6 !important; font-size: 15px !important; }
        }
        .status-item { padding: 5px 10px; border-bottom: 1px solid #f0f2f6; line-height: 1.5; }
        </style>
    """, unsafe_allow_html=True)

    st.header("🤝 사내 멘토링")
    st.caption("대한사료 임직원 간의 성장을 돕는 실시간 소통 플랫폼")

    # DB 연동 설정
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_멘토링_DB")

    def get_sheet_data(sheet_name):
        try:
            doc = init_gspread()
            return doc.worksheet(sheet_name).get_all_records()
        except: return []

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
        except: st.error("⚠️ 데이터 저장 오류")

    # 데이터 로드
    mentors_data = get_sheet_data("mentors")
    admin_data = get_sheet_data("admin")
    admin_info = admin_data[0] if admin_data else {"id": "admin", "pw": "dhfeed1947"}
    
    raw_slots = get_sheet_data("slots")
    available_slots = []
    for s in raw_slots:
        if not s.get('date'): continue
        s['date'] = datetime.datetime.strptime(str(s['date']), "%Y-%m-%d").date()
        s['start'] = datetime.datetime.strptime(str(s['start']), "%H:%M:%S").time()
        s['end'] = datetime.datetime.strptime(str(s['end']), "%H:%M:%S").time()
        available_slots.append(s)

    raw_res = get_sheet_data("reservations")
    reservations = []
    for r in raw_res:
        if not r.get('date'): continue
        r['date'] = datetime.datetime.strptime(str(r['date']), "%Y-%m-%d").date()
        r['start_time'] = datetime.datetime.strptime(str(r['start_time']), "%H:%M:%S").time()
        r['end_time'] = datetime.datetime.strptime(str(r['end_time']), "%H:%M:%S").time()
        reservations.append(r)

    mentor_names = ["선택해주세요"] + [m['name'] for m in mentors_data]

    # 📊 탭 구성
    tab1, tab2, tab3, tab4 = st.tabs(["🙋‍♂️ 멘티 예약 신청", "💼 멘토 일정 관리", "📋 멘토 예약 관리", "👑 관리자 메뉴"])

    # --- [🙋‍♂️ Tab 1: 신청] ---
    with tab1:
        if st.button("🔄 최신 현황 불러오기"): st.rerun()
        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            if not available_slots: st.info("등록된 일정이 없습니다.")
            else:
                summ = {}
                for s in available_slots:
                    w_day = WEEKS[s['date'].weekday()]
                    info = f"📅 {s['date'].strftime('%m/%d')}({w_day}) ⏰ {s['start'].strftime('%H:%M')}~{s['end'].strftime('%H:%M')} [📍 {s.get('location','-')}]"
                    summ[s['mentor']] = summ.get(s['mentor'], []) + [info]
                for m, infos in summ.items():
                    st.markdown(f"✅ **{m} 멘토님**")
                    for single_info in sorted(infos): st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{single_info}")
        
        st.divider()
        c1, c2 = st.columns(2)
        m_n, m_p = c1.text_input("신청자 성함", key="m_n_t1"), c1.text_input("직급", key="m_p_t1")
        m_t, m_e = c2.text_input("팀명", key="m_t_t1"), c2.text_input("사내 이메일", key="m_e_t1")
        
        col_sel, col_prof = st.columns([1.2, 1])
        with col_sel:
            selected_m = st.selectbox("멘토 선택", mentor_names, key="m_s_t1")
            sel_date = st.date_input("날짜 선택", datetime.date.today() + datetime.timedelta(days=1))
            slots = [s for s in available_slots if s['mentor']==selected_m and s['date']==sel_date]
            if slots:
                st.info(f"📍 {slots[0].get('location','-')} | ⏰ {slots[0]['start']} ~ {slots[0]['end']}")
                p_t = generate_time_slots(slots[0]['start'], slots[0]['end'])
                ct1, ct2 = st.columns(2)
                ts = ct1.selectbox("시작 시간", p_t, format_func=lambda x: x.strftime("%H:%M"))
                te = ct2.selectbox("종료 시간", [t for t in p_t if t > ts] if [t for t in p_t if t > ts] else [ts], format_func=lambda x: x.strftime("%H:%M"))
                topic = st.text_area("상담 주제 (필수)")
                if st.button("🚀 예약 신청하기", type="primary", use_container_width=True):
                    if m_n and topic and is_company_email(m_e):
                        new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n, "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e, "date": sel_date, "start_time": ts, "end_time": te, "topic": topic, "location": slots[0].get('location',''), "status": "대기중"}
                        reservations.append(new_res); safe_save("reservations", reservations)
                        available_slots.remove(slots[0]); safe_save("slots", available_slots)
                        m_info = next((m for m in mentors_data if m['name']==selected_m), None)
                        if m_info:
                            send_email(m_info['email'], "[대한사료 멘토링] 신청 접수", f"{m_n}님의 신청: {sel_date} {ts}~{te}\n\n접속: {SYSTEM_URL}")
                        st.balloons(); time.sleep(1); st.rerun()

        with col_prof:
            if selected_m != "선택해주세요":
                p = next((m for m in mentors_data if m['name'] == selected_m), None)
                if p: st.markdown(f"""<div style="border: 2px solid #4A90E2; padding: 20px; border-radius: 12px; background-color: #f0f7ff;"><h3>🎖️ {p['name']} {p.get('position','')}</h3><p>🏢 {p.get('team','')}<br>🎯 {p.get('expertise','')}</p><i>"{p.get('greeting','')}"</i></div>""", unsafe_allow_html=True)

    # --- [💼 Tab 2: 멘토 일정 관리] ---
    with tab2:
        st.subheader("💼 나의 멘토링 일정 관리")
        m_log2 = st.selectbox("본인 성함 선택", mentor_names, key="m_log_t2", on_change=reset_pw_t2)
        if m_log2 != "선택해주세요":
            minfo = next((m for m in mentors_data if m['name']==m_log2), None)
            if minfo and st.text_input("비밀번호 입력", type="password", key="m_pw_t2") == str(minfo['pw']):
                c2_1, c2_2, c2_3, c2_4 = st.columns(4)
                dv, sv, ev, lv = c2_1.date_input("날짜", key="sd_t2"), c2_2.time_input("시작", key="ss_t2"), c2_3.time_input("종료", key="se_t2"), c2_4.text_input("장소", key="sl_t2")
                if st.button("🗓️ 일정 등록하기", type="primary", use_container_width=True):
                    available_slots.append({"mentor": m_log2, "date": dv, "start": sv, "end": ev, "location": lv})
                    safe_save("slots", available_slots); st.snow(); st.rerun()
                st.divider()
                my_slots = [x for x in available_slots if x['mentor'] == m_log2]
                for i, s in enumerate(my_slots):
                    col_a, col_b = st.columns([4, 1])
                    col_a.write(f"📅 {s['date']} | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                    if col_b.button("삭제", key=f"del_s_{i}"):
                        available_slots.remove(s); safe_save("slots", available_slots); st.rerun()

    # --- [📋 Tab 3: 멘토 예약 관리] ---
    with tab3:
        st.subheader("📋 멘티 신청 현황 관리")
        m_sel3 = st.selectbox("본인 성함 선택", mentor_names, key="m_sel_t3", on_change=reset_pw_t3)
        if m_sel3 != "선택해주세요":
            minfo3 = next((m for m in mentors_data if m['name']==m_sel3), None)
            if minfo3 and st.text_input("비번 확인", type="password", key="m_pw_t3") == str(minfo3['pw']):
                my_res = [x for x in reservations if x['mentor']==m_sel3]
                for r in my_res:
                    with st.expander(f"[{r['status']}] {r['date']} | {r['mentee_name']}님"):
                        st.write(f"주제: {r['topic']} | 시간: {r['start_time']}~{r['end_time']}")
                        if r['status'] == "대기중":
                            b1, b2 = st.columns(2)
                            if b1.button("✅ 승인", key=f"ok_{r['id']}"):
                                r['status']="승인됨"; safe_save("reservations", reservations)
                                send_email(r['mentee_email'], "예약 승인 알림", f"{r['date']} 멘토링이 승인되었습니다."); st.rerun()
                            if b2.button("❌ 거절", key=f"no_{r['id']}"):
                                r['status']="거절됨"; safe_save("reservations", reservations); st.rerun()

    # --- [👑 Tab 4: 관리자 메뉴] ---
    with tab4:
        st.subheader("👑 관리자 메뉴")
        if "admin_logged_in" not in st.session_state: st.session_state.admin_logged_in = False
        if not st.session_state.admin_logged_in:
            aid, apw = st.text_input("ID"), st.text_input("PW", type="password")
            if st.button("로그인") and aid == admin_info['id'] and apw == str(admin_info['pw']):
                st.session_state.admin_logged_in = True; st.rerun()
        else:
            if st.button("로그아웃"): st.session_state.admin_logged_in = False; st.rerun()
            with st.expander("👨‍🏫 멘토 관리 (수정/삭제)"):
                for i, m in enumerate(mentors_data):
                    col_m1, col_m2 = st.columns([3, 1])
                    col_m1.write(f"**{m['name']}** ({m.get('team','')})")
                    if col_m2.button("삭제", key=f"adm_del_{i}"):
                        mentors_data.pop(i); safe_save("mentors", mentors_data); st.rerun()

def run_leader_talk():
    st.header("☕ 리더와의 대화")
    st.info("준비 중입니다.")

def run_class():
    st.header("🎓 직무 원데이 클래스")
    st.info("준비 중입니다.")
