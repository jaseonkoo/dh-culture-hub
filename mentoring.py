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

# ==========================================================
# 🤝 동반성장 멘토링 (mentoring.py)
#  v2 : 화면이 느리게 뜨던 원인을 고쳤습니다.
#   ① 두레이 캘린더 접속을 화면 열 때마다 하지 않고 한 번만 합니다.
#   ② 과거 일정 자동 정리는 '화면을 다 그린 뒤'에, 서버당 하루 한 번만 합니다.
#   ③ 구글 시트가 잠깐 말썽이어도(503) 실패를 기억하지 않고 다시 시도합니다.
# ==========================================================

M_SCOPE = ["https://spreadsheets.google.com/feeds",
           "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/drive.file",
           "https://www.googleapis.com/auth/drive"]

M_DB = "대한사료_멘토링_DB"
M_CAL_NAME = "멘토링&코칭"


class MentorBusy(Exception):
    """구글 시트가 잠깐 응답하지 않을 때."""
    pass


def _m_retry(fn, *a, **kw):
    """503·429 같은 '잠깐 나는 오류'는 조금 기다렸다 다시 불러 봅니다."""
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
            last = e
            if i >= 1:
                raise
            time.sleep(1.0)
    raise MentorBusy(str(last))


@st.cache_resource(show_spinner=False)
def init_gspread():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], M_SCOPE)
    client = gspread.authorize(creds)
    return _m_retry(client.open, M_DB)


@st.cache_data(ttl=60, show_spinner=False)
def get_sheet_data(sheet_name):
    """탭 하나를 읽어 옵니다.
       ⚠️ 예전에는 실패했을 때 빈 목록을 돌려주고 그걸 기억해 버려서,
          한 번 오류가 나면 1분 동안 화면이 비어 보였습니다."""
    doc = init_gspread()
    ws = _m_retry(doc.worksheet, sheet_name)
    return _m_retry(ws.get_all_records)


def _reset_mentor_conn():
    for f in (init_gspread, get_sheet_data, get_dooray_calendar):
        try:
            f.clear()
        except Exception:
            pass


# =========================================================
# 📆 두레이 캘린더
#   ⚡ 예전에는 캘린더가 필요할 때마다 주소 3개를 차례로 찔러 보며
#      새로 접속했습니다. 그게 화면이 느리게 뜨던 가장 큰 원인이었습니다.
# =========================================================
@st.cache_resource(show_spinner=False)
def get_dooray_calendar():
    cal_id = st.secrets.get("dooray_cal_id")
    cal_pw = st.secrets.get("dooray_cal_pw")

    if not cal_id or not cal_pw:
        return None

    urls_to_try = [
        f"https://caldav.dooray.com/caldav/principals/{cal_id}/",
        "https://caldav.dooray.com/caldav/",
        "https://caldav.dooray.com",
    ]

    for test_url in urls_to_try:
        try:
            client = caldav.DAVClient(url=test_url, username=cal_id, password=cal_pw,
                                      timeout=8)
            principal = client.principal()
            calendars = principal.calendars()
            if calendars:
                for c in calendars:
                    if hasattr(c, 'name') and c.name == M_CAL_NAME:
                        return c
                return calendars[0]
        except Exception:
            continue
    return None


@st.cache_resource(show_spinner=False)
def _m_cleanup_marker():
    """'오늘 이미 캘린더 청소를 했는지'를 서버 전체가 함께 기억합니다.
       (예전에는 접속한 사람마다 따로 기억해서, 사람마다 한 번씩 느렸습니다)"""
    return {}


def add_dooray_calendar_event(name, date_obj, start_time, end_time, location,
                              prefix="[예약가능]"):
    try:
        my_calendar = get_dooray_calendar()
        if not my_calendar:
            return False

        start_dt = datetime.datetime.combine(date_obj, start_time).strftime("%Y%m%dT%H%M%S")
        end_dt = datetime.datetime.combine(date_obj, end_time).strftime("%Y%m%dT%H%M%S")
        title = f"{prefix} {name} 멘토님"

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
DESCRIPTION:조직문화 플랫폼에서 신청 가능한 멘토링 일정입니다.\\nhttps://dhfeed-culture.streamlit.app/
END:VEVENT
END:VCALENDAR"""

        try:
            my_calendar.save_event(vcal_data)
            return True
        except caldav.lib.error.PutError as pe:
            if "200" in str(pe) or "201" in str(pe) or "204" in str(pe):
                return True
            st.error(f"⚠️ 캘린더 일정 등록 에러: {pe}")
            return False
    except Exception as e:
        st.error(f"⚠️ 캘린더 시스템 에러: {e}")
        return False


def delete_dooray_calendar_event(name, date_obj):
    try:
        my_calendar = get_dooray_calendar()
        if not my_calendar:
            return False

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


def auto_cleanup_past_dooray_events():
    """과거의 [예약가능] 일정을 정리합니다.
       ⚡ 서버당 하루 한 번만, 그리고 화면을 다 그린 '뒤에' 실행합니다."""
    today_str = str(datetime.date.today())
    marker = _m_cleanup_marker()
    if marker.get("day") == today_str:
        return
    marker["day"] = today_str          # 먼저 표시해 두어 중복 실행을 막습니다.

    try:
        my_calendar = get_dooray_calendar()
        if not my_calendar:
            return
        start_dt = datetime.datetime.now() - datetime.timedelta(days=30)
        end_dt = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
        events = my_calendar.date_search(start=start_dt, end=end_dt)
        for event in events:
            if "[예약가능]" in event.data:
                event.delete()
    except Exception:
        pass      # 자동 정리는 실패해도 조용히 넘어갑니다.


def send_telegram_noti(mentor_name, date, start, end, location):
    try:
        bot_token = st.secrets["telegram_bot_token"]
    except KeyError:
        st.error("⚠️ 스트림릿 Secrets에 텔레그램 토큰이 설정되지 않았습니다.")
        return False

    chat_id = "-1004464463229"

    start_str = start.strftime('%H:%M') if hasattr(start, 'strftime') else str(start)[:5]
    end_str = end.strftime('%H:%M') if hasattr(end, 'strftime') else str(end)[:5]

    text = (f"📢 *[{mentor_name} 멘토님]*의 새로운 멘토링 일정이 오픈되었습니다!\n\n"
            f"  • 📅 일시 : {date} ({start_str} ~ {end_str})\n"
            f"  • 📍 장소 : {location}\n\n"
            f"▶ 지금 바로 조직문화 플랫폼에 접속해서 대화를 신청해 보세요!\n"
            f"      (https://dhfeed-culture.streamlit.app)")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            st.error(f"⚠️ 텔레그램 발송 실패 원인: {res.text}")
            return False
        return True
    except Exception as e:
        st.error(f"⚠️ 통신 에러: {str(e)}")
        return False


def run_mentoring():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_mentoring()
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        st.markdown("### 🤝 동반성장 멘토링")
        if code in (429, 500, 502, 503) or isinstance(e, MentorBusy):
            st.warning("⏳ 구글 시트가 잠시 응답하지 않고 있습니다. "
                       "구글 쪽 일시적인 문제라 조금 기다리면 대부분 정상으로 돌아옵니다.\n\n"
                       "**5~10초 뒤 아래 [다시 시도] 버튼을 눌러 주세요.**")
        elif code == 403:
            st.error("구글 시트 접근 권한이 없습니다. "
                     "시트를 서비스 계정 이메일에 **편집자**로 공유했는지 확인해 주세요.")
        else:
            st.error("자료를 불러오는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:200])
        if st.button("🔄 다시 시도", key="m_retry_btn", type="primary"):
            _reset_mentor_conn()
            st.rerun()
        return

    # ⚡ 캘린더 청소는 화면을 다 그린 '뒤에' 조용히 합니다.
    auto_cleanup_past_dooray_events()


def _run_mentoring():
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

    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    def fetch_latest_data(force=False):
        # ⚠️ 예전에는 st.cache_data.clear() 로 '앱 전체'의 기억을 지웠습니다.
        #    (도서관·통계까지 같이 지워져서 모두 느려졌습니다) 이제 이 화면 것만 지웁니다.
        if force:
            get_sheet_data.clear()

        st.session_state.mentors_data = get_sheet_data("mentors")
        ad_list = get_sheet_data("admin")
        st.session_state.admin_info = ad_list[0] if ad_list else {"id": "admin", "pw": "dhfeed1947"}

        raw_slots = get_sheet_data("slots")
        formatted_slots = []
        for s in raw_slots:
            if not s.get('date'):
                continue
            try:
                s = dict(s)
                s['date'] = datetime.datetime.strptime(str(s['date']), "%Y-%m-%d").date()
                s['start'] = datetime.datetime.strptime(str(s['start']), "%H:%M:%S").time()
                s['end'] = datetime.datetime.strptime(str(s['end']), "%H:%M:%S").time()
            except Exception:
                continue
            formatted_slots.append(s)
        st.session_state.available_slots = formatted_slots

        raw_res = get_sheet_data("reservations")
        formatted_res = []
        for r in raw_res:
            if not r.get('date'):
                continue
            try:
                r = dict(r)
                r['date'] = datetime.datetime.strptime(str(r['date']), "%Y-%m-%d").date()
                r['start_time'] = datetime.datetime.strptime(str(r['start_time']), "%H:%M:%S").time()
                r['end_time'] = datetime.datetime.strptime(str(r['end_time']), "%H:%M:%S").time()
                r['status'] = str(r.get('status', '대기중')).strip()
            except Exception:
                continue
            formatted_res.append(r)
        st.session_state.reservations = formatted_res

    fetch_latest_data()

    def safe_save(ws_name, data_list):
        try:
            doc = init_gspread()
            ws = _m_retry(doc.worksheet, ws_name)
            _m_retry(ws.clear)
            if data_list:
                df = pd.DataFrame(data_list)
                for c in ['date', 'start', 'end', 'start_time', 'end_time']:
                    if c in df.columns:
                        df[c] = df[c].astype(str)
                df = df.fillna("")
                _m_retry(ws.update, values=[df.columns.values.tolist()] + df.values.tolist())
            return True
        except Exception as e:
            st.error(f"⚠️ 구글 시트 저장 오류 ({ws_name}): {e}")
            return False

    today_date_check = datetime.date.today()
    active_mentors = {s['mentor'] for s in st.session_state.get('available_slots', []) if s['date'] >= today_date_check}
    mentor_names = ["선택해주세요"] + [m['name'] for m in st.session_state.get('mentors_data', []) if m['name'] in active_mentors]

    main_tab_mentee, main_tab_mentor, main_tab_admin = st.tabs(["🙋‍♂️ 멘티 공간", "💼 멘토 공간", "👑 관리자 메뉴"])

    # =========================================================
    # 🙋‍♂️ [메인 탭 1: 멘티 공간]
    # =========================================================
    with main_tab_mentee:
        st.subheader("🗓️ 멘토링 예약 신청")
        if st.button("🔄 최신 현황 불러오기"):
            fetch_latest_data(force=True); st.rerun()

        with st.expander("📢 예약 가능 현황 확인", expanded=True):
            today_date = datetime.date.today()
            all_slots = [s for s in st.session_state.get('available_slots', []) if s['date'] >= today_date]

            if not all_slots:
                st.info("현재 등록된 신청 가능한 일정이 없습니다.")
            else:
                summ = {}
                for s in all_slots:
                    w_day = WEEKS[s['date'].weekday()]
                    info = f"📅 {s['date'].strftime('%m/%d')}({w_day}) ⏰ {s['start'].strftime('%H:%M')}~{s['end'].strftime('%H:%M')} [📍 {s.get('location','-')}]"
                    summ[s['mentor']] = summ.get(s['mentor'], []) + [info]
                for m, infos in summ.items():
                    st.markdown(f"✅ **{m} 멘토님**")
                    for single_info in sorted(infos):
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{single_info}")

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

            slots = [s for s in st.session_state.get('available_slots', []) if s['mentor'] == selected_m and s['date'] == sel_date]
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
                            with st.status("📡 매칭 처리 중...") as status:
                                new_res = {"id": str(uuid.uuid4())[:8], "mentor": selected_m, "mentee_name": m_n,
                                           "mentee_position": m_p, "mentee_team": m_t, "mentee_email": m_e,
                                           "date": sel_date, "start_time": ts, "end_time": te, "topic": topic,
                                           "location": loc, "status": "대기중"}
                                st.session_state.reservations.append(new_res)
                                save1 = safe_save("reservations", st.session_state.reservations)

                                slot_to_del = next((s for s in st.session_state.available_slots if s['mentor'] == selected_m and s['date'] == sel_date), None)
                                save2 = True
                                if slot_to_del:
                                    st.session_state.available_slots.remove(slot_to_del)
                                    save2 = safe_save("slots", st.session_state.available_slots)

                                m_info = next((m for m in st.session_state.mentors_data if m['name'] == selected_m), None)
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
        sub_tab_schedule, sub_tab_manage, sub_tab_info = st.tabs(["🗓️ 일정 등록 및 관리", "📋 신청 현황 및 예약 관리", "⚙️ 멘토 정보 변경"])

        # --- [서브 탭 1: 일정 관리] ---
        with sub_tab_schedule:
            st.subheader("💼 나의 멘토링 일정 관리")
            st.markdown("🔒 **멘토 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            m_name_1 = c_log1.text_input("본인 성함", key="m_name_1", placeholder="이름을 입력하세요")
            m_pw_1 = c_log2.text_input("비밀번호", type="password", key="m_pw_1")

            if m_name_1 and m_pw_1:
                minfo = next((m for m in st.session_state.get('mentors_data', []) if m['name'] == m_name_1), None)
                if not minfo:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(minfo['pw']) != m_pw_1:
                    st.error("🚫 비밀번호가 일치하지 않습니다.")
                else:
                    st.success(f"✅ {m_name_1} 멘토님, 환영합니다!")
                    st.markdown("---")
                    c2_1, c2_2, c2_3, c2_4 = st.columns(4)
                    dv, sv, ev, lv = (c2_1.date_input("날짜", key="sd_t2"),
                                      c2_2.time_input("시작", datetime.time(0, 0), key="ss_t2"),
                                      c2_3.time_input("종료", datetime.time(0, 0), key="se_t2"),
                                      c2_4.text_input("장소", key="sl_t2"))

                    if st.button("🗓️ 일정 등록하기", type="primary", use_container_width=True, key="sb_t2"):
                        is_duplicate = False
                        for r in st.session_state.get('reservations', []):
                            if r['mentor'] == m_name_1 and r['date'] == dv:
                                if not (ev <= r['start_time'] or sv >= r['end_time']):
                                    is_duplicate = True; break
                        if not is_duplicate:
                            for s in st.session_state.get('available_slots', []):
                                if s['mentor'] == m_name_1 and s['date'] == dv:
                                    if not (ev <= s['start'] or sv >= s['end']):
                                        is_duplicate = True; break

                        if is_duplicate:
                            st.error("🚫 중복된 시간이 존재합니다.")
                        elif sv >= ev:
                            st.error("🚫 시간 설정 오류")
                        else:
                            is_noti_success = False
                            with st.status("📡 저장 중..."):
                                st.session_state.available_slots.append({"mentor": m_name_1, "date": dv, "start": sv, "end": ev, "location": lv})
                                if safe_save("slots", st.session_state.available_slots):
                                    add_dooray_calendar_event(m_name_1, dv, sv, ev, lv)
                                    is_noti_success = send_telegram_noti(m_name_1, dv, sv, ev, lv)

                            if is_noti_success:
                                st.snow()
                                st.success("등록 완료!")
                                time.sleep(2)
                                fetch_latest_data(force=True)
                                st.rerun()
                            else:
                                st.warning("일정은 저장되었으나 텔레그램 알림 발송에 실패했습니다.")

                    st.divider(); st.markdown(f"#### 🗑️ {m_name_1} 멘토님의 등록 일정")
                    my_slots = [x for x in st.session_state.get('available_slots', []) if x['mentor'] == m_name_1]
                    for i, s in enumerate(my_slots):
                        col_a, col_b = st.columns([4, 1]); w_s = WEEKS[s['date'].weekday()]
                        col_a.write(f"📅 {s['date']}({w_s}) | ⏰ {s['start']}~{s['end']} | 📍 {s.get('location','-')}")
                        if col_b.button("삭제", key=f"del_s_{i}"):
                            st.session_state.available_slots.remove(s)
                            if safe_save("slots", st.session_state.available_slots):
                                delete_dooray_calendar_event(m_name_1, s['date'])
                                fetch_latest_data(force=True)
                                st.rerun()

        # --- [서브 탭 2: 예약 관리 및 후기] ---
        with sub_tab_manage:
            st.subheader("📋 멘티 신청 현황 및 후기 관리")
            st.markdown("🔒 **멘토 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            m_name_2 = c_log1.text_input("본인 성함", key="m_name_2", placeholder="이름을 입력하세요")
            m_pw_2 = c_log2.text_input("비밀번호", type="password", key="m_pw_2")

            if m_name_2 and m_pw_2:
                minfo3 = next((m for m in st.session_state.get('mentors_data', []) if m['name'] == m_name_2), None)
                if not minfo3:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(minfo3['pw']) != m_pw_2:
                    st.error("🚫 비밀번호가 일치하지 않습니다.")
                else:
                    st.success(f"✅ {m_name_2} 멘토님, 환영합니다!")
                    st.markdown("---")
                    my_res = [x for x in st.session_state.get('reservations', []) if x['mentor'] == m_name_2]
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
                                    r['status'] = "승인됨"
                                    if safe_save("reservations", st.session_state.reservations):
                                        if r.get('mentee_email'):
                                            body = f"안녕하세요, {r['mentee_name']}님!\n\n신청하신 멘토링 예약이 승인되었습니다.\n\n- 일시: {r['date']} ({r['start_time']} ~ {r['end_time']})\n- 멘토: {m_name_2} 멘토님\n\n감사합니다."
                                            send_email(r['mentee_email'], "[대한사료 멘토링] 신청하신 예약이 승인되었습니다!", body)

                                        delete_dooray_calendar_event(m_name_2, r['date'])
                                        add_dooray_calendar_event(m_name_2, r['date'], r['start_time'], r['end_time'], r.get('location', '-'), prefix="[승인완료]")

                                        fetch_latest_data(force=True)
                                        st.rerun()

                                if b2.button("❌ 거절", key=f"no_{r['id']}", use_container_width=True):
                                    r['status'] = "거절됨"
                                    if safe_save("reservations", st.session_state.reservations):
                                        if r.get('mentee_email'):
                                            send_email(r['mentee_email'], "[대한사료 멘토링] 예약 반려 안내", f"아쉽게도 {m_name_2} 멘토님이 예약을 반려하셨습니다.")
                                        st.session_state.available_slots.append({
                                            "mentor": r['mentor'], "date": r['date'], "start": r['start_time'],
                                            "end": r['end_time'], "location": r.get('location', '')
                                        })
                                        safe_save("slots", st.session_state.available_slots)

                                        # ✨ 멘토 거절 시, 기존 일정 완전히 삭제
                                        delete_dooray_calendar_event(m_name_2, r['date'])

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
                                        if safe_save("reservations", st.session_state.reservations):
                                            st.rerun()
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

        # --- [서브 탭 3: 멘토 정보 변경] ---
        with sub_tab_info:
            st.subheader("⚙️ 멘토 정보 변경")
            st.info("💡 본인의 전문분야, 인사말, 그리고 비밀번호를 편하게 직접 수정하실 수 있습니다.")
            st.markdown("🔒 **멘토 본인 인증**")
            c_log1, c_log2 = st.columns(2)
            m_name_3 = c_log1.text_input("본인 성함", key="m_name_3", placeholder="이름을 입력하세요")
            m_pw_3 = c_log2.text_input("현재 비밀번호 입력", type="password", key="m_pw_3")

            if m_name_3 and m_pw_3:
                minfo_info = next((m for m in st.session_state.get('mentors_data', []) if m['name'] == m_name_3), None)
                if not minfo_info:
                    st.error("🚫 등록되지 않은 이름입니다.")
                elif str(minfo_info['pw']) != m_pw_3:
                    st.error("🚫 비밀번호가 일치하지 않습니다. 다시 확인해 주세요.")
                else:
                    st.success(f"✅ {m_name_3} 멘토님, 환영합니다!")
                    st.markdown("---")
                    with st.form(key="edit_mentor_info_form"):
                        st.markdown("#### 📝 프로필 정보 수정")
                        new_exp = st.text_input("전문분야", value=minfo_info.get('expertise', ''))
                        new_greet = st.text_area("인사말", value=minfo_info.get('greeting', ''))

                        st.markdown("#### 🔒 비밀번호 변경 (유지하려면 비워두세요)")
                        c1, c2 = st.columns(2)
                        new_pw = c1.text_input("새로운 비밀번호", type="password")
                        new_pw_confirm = c2.text_input("새로운 비밀번호 확인", type="password")

                        submit_info = st.form_submit_button("💾 정보 업데이트", use_container_width=True)

                        if submit_info:
                            has_error = False
                            final_pw = minfo_info['pw']

                            if new_pw or new_pw_confirm:
                                if new_pw != new_pw_confirm:
                                    st.error("🚫 새로운 비밀번호와 확인용 비밀번호가 일치하지 않습니다.")
                                    has_error = True
                                else:
                                    final_pw = new_pw

                            if not has_error:
                                with st.status("📡 정보 동기화 중..."):
                                    for idx, m in enumerate(st.session_state.mentors_data):
                                        if m['name'] == m_name_3:
                                            st.session_state.mentors_data[idx]['expertise'] = new_exp
                                            st.session_state.mentors_data[idx]['greeting'] = new_greet
                                            st.session_state.mentors_data[idx]['pw'] = final_pw
                                            break
                                    if safe_save("mentors", st.session_state.mentors_data):
                                        st.success("✅ 멘토 정보가 성공적으로 변경되었습니다!")
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
            col_out, col_ref = st.columns(2)
            if col_out.button("로그아웃"):
                st.session_state.admin_logged_in = False; st.rerun()
            if col_ref.button("🔄 연결 새로고침", key="m_reset_conn",
                              help="구글 시트나 캘린더가 말썽일 때 눌러 주세요."):
                _reset_mentor_conn(); st.success("연결을 새로 읽었습니다."); st.rerun()

            with st.expander("👨‍🏫 멘토 신규 등록"):
                r1, r2, r3, r4 = st.columns(4)
                nm, np, nt, n_pw = (r1.text_input("성함", key="n1"), r2.text_input("직급", key="n2"),
                                    r3.text_input("팀명", key="n3"), r4.text_input("비번", key="n4"))
                e1, e2 = st.columns(2); ne = e1.text_input("이메일", key="n5"); nx = e2.text_input("전문분야", key="n6")
                ng = st.text_area("인사말", key="n7")
                if st.button("등록하기") and is_company_email(ne):
                    st.session_state.mentors_data.append({"name": nm, "position": np, "team": nt, "pw": n_pw, "expertise": nx, "greeting": ng, "email": ne})
                    if safe_save("mentors", st.session_state.mentors_data):
                        fetch_latest_data(force=True); st.rerun()

            with st.expander("📋 기존 멘토 수정/삭제", expanded=True):
                for i, m in enumerate(st.session_state.get('mentors_data', [])):
                    st.markdown(f"#### 👤 {m['name']} 멘토님 정보 수정")
                    er1, er2, er3, er4 = st.columns(4)
                    un = er1.text_input("성함", m['name'], key=f"un_{i}"); up = er2.text_input("직급", m.get('position', ''), key=f"up_{i}")
                    ut = er3.text_input("팀명", m.get('team', ''), key=f"ut_{i}"); upw = er4.text_input("비번", m.get('pw', ''), key=f"upw_{i}")
                    e1, e2 = st.columns(2)
                    ue = e1.text_input("이메일", m.get('email', ''), key=f"ue_{i}"); ux = e2.text_input("전문분야", m.get('expertise', ''), key=f"ux_{i}")
                    ug = st.text_area("인사말", m.get('greeting', ''), key=f"ug_{i}")
                    if st.button("💾 저장", key=f"sv_{i}"):
                        if is_company_email(ue):
                            st.session_state.mentors_data[i].update({"name": un, "position": up, "team": ut, "pw": upw, "email": ue, "expertise": ux, "greeting": ug})
                            if safe_save("mentors", st.session_state.mentors_data):
                                st.success("수정됨"); fetch_latest_data(force=True); st.rerun()
                    if st.button("❌ 삭제", key=f"dl_{i}"):
                        st.session_state.mentors_data.pop(i)
                        if safe_save("mentors", st.session_state.mentors_data):
                            fetch_latest_data(force=True); st.rerun()
                    st.divider()

            with st.expander("🛠️ 시스템 관리 (기존 일정 캘린더 일괄 등록 및 정리)"):
                st.info("💡 캘린더 연동 기능이 적용되기 전에 등록된 '예약 가능' 및 '승인 완료' 일정들을 두레이 캘린더로 일괄 전송하거나, 과거의 미예약 일정을 수동으로 즉시 정리할 수 있습니다.")
                st.warning("🚨 주의: 버튼을 여러 번 누르면 캘린더에 일정이 중복으로 등록될 수 있으니 딱 한 번만 눌러주세요!")

                if st.button("🔄 캘린더 일괄 동기화 실행", type="primary", use_container_width=True):
                    with st.status("📡 기존 일정들을 캘린더로 전송하는 중...") as sync_status:
                        success_count = 0
                        today_date = datetime.date.today()

                        # 1. 예약 가능 일정 (slots) 밀어넣기 (오늘 이후 일정만)
                        for s in st.session_state.get('available_slots', []):
                            if s['date'] >= today_date:
                                if add_dooray_calendar_event(s['mentor'], s['date'], s['start'], s['end'], s.get('location', '-'), prefix="[예약가능]"):
                                    success_count += 1

                        # 2. 승인 완료된 예약 (reservations) 밀어넣기 (오늘 이후 일정만)
                        for r in st.session_state.get('reservations', []):
                            if r['date'] >= today_date and r['status'] == "승인됨":
                                if add_dooray_calendar_event(r['mentor'], r['date'], r['start_time'], r['end_time'], r.get('location', '-'), prefix="[승인완료]"):
                                    success_count += 1

                        sync_status.update(label=f"✅ 총 {success_count}건의 일정이 두레이 캘린더에 성공적으로 등록되었습니다!", state="complete")
                        st.balloons()

                st.divider()
                st.markdown("#### 🗑️ 캘린더 청소하기")
                if st.button("🧹 지난 미예약 캘린더 일정 일괄 삭제", key="m_clean_btn", use_container_width=True):
                    with st.status("📡 과거 캘린더 일정을 정리하는 중...") as clean_status:
                        try:
                            my_calendar = get_dooray_calendar()
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
