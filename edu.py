from utils import *
import re
import datetime
import pandas as pd

# ==========================================================
# 📊 교육이수제 현황 (edu.py)
#   - 원래 따로 돌던 프로그램을 플랫폼 안으로 옮긴 것입니다.
#   - 구글 시트를 읽는 방법을 두 가지로 준비해 두었습니다.
#       ① 서비스 계정(gspread) — 플랫폼의 다른 프로그램과 같은 방식
#       ② 공개 링크 CSV — ①이 안 되면 자동으로 이 방법을 씁니다
#     그래서 st-gsheets-connection 패키지를 따로 설치하지 않아도 됩니다.
# ==========================================================

EDU_URL = "https://docs.google.com/spreadsheets/d/1en8kN_2uhvDrQpsze_wWBVSCu3l2WiPH78Dy57W3mXs/edit?usp=sharing"

# 교육 구분(순서대로 화면에 나옵니다)
EDU_CATEGORIES = ["면접관 양성 교육", "경영비즈니스 교육", "DX교육"]

EDU_SCOPE = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file",
             "https://www.googleapis.com/auth/drive"]


class EduBusy(Exception):
    """구글 시트가 잠깐 응답하지 않을 때."""
    pass


def _e_retry(fn, *a, **kw):
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
    raise EduBusy(str(last))


def _edu_csv_url(url):
    """공개 링크 주소를 'CSV로 내려받는 주소'로 바꿔 줍니다."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", str(url))
    if not m:
        return ""
    key = m.group(1)
    gid = "0"
    g = re.search(r"[#&?]gid=(\d+)", str(url))
    if g:
        gid = g.group(1)
    return ("https://docs.google.com/spreadsheets/d/%s/export?format=csv&gid=%s"
            % (key, gid))


@st.cache_resource(show_spinner=False)
def _edu_doc():
    """서비스 계정으로 시트를 엽니다. (실패하면 기억하지 않습니다)"""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], EDU_SCOPE)
    client = gspread.authorize(creds)
    return _e_retry(client.open_by_url, EDU_URL)


@st.cache_data(ttl=60, show_spinner=False)
def load_edu_data():
    """교육 이수 자료를 표로 읽어 옵니다."""
    # ① 서비스 계정으로 먼저 시도
    try:
        ws = _e_retry(_edu_doc().get_worksheet, 0)
        rows = _e_retry(ws.get_all_records)
        if rows:
            df = pd.DataFrame(rows)
            df.columns = df.columns.astype(str).str.strip().str.replace("\n", "", regex=False)
            return df
    except Exception:
        pass

    # ② 안 되면 공개 링크(CSV)로 읽습니다.
    csv_url = _edu_csv_url(EDU_URL)
    if not csv_url:
        raise EduBusy("시트 주소를 알아볼 수 없습니다.")
    df = pd.read_csv(csv_url)
    df.columns = df.columns.astype(str).str.strip().str.replace("\n", "", regex=False)
    return df


def _reset_edu_conn():
    for f in (_edu_doc, load_edu_data):
        try:
            f.clear()
        except Exception:
            pass


def _e_num(v, default=0.0):
    """'1,200' · '8.0' 처럼 적혀 있어도 숫자로 읽습니다."""
    s = str(v).replace(",", "").strip()
    if not s or s == "-" or s.lower() == "nan":
        return default
    try:
        return float(s)
    except Exception:
        return default


def _e_int_text(v):
    """8.0 → 8 처럼 소수점 없는 숫자로 보여 줍니다."""
    n = _e_num(v, None)
    if n is None:
        return str(v)
    return str(int(n)) if float(n).is_integer() else str(n)


EDU_CSS = """
<style>
    /* 원래 프로그램(app.py)의 꾸미기를 그대로 옮겼습니다. */
    .stApp { background-color: #f8f9fa !important; background-image: none !important; }

    h1, h2, h3 { color: #2c3e50 !important; font-weight: 700; letter-spacing: -0.5px; }

    div.stButton > button:first-child,
    div.stFormSubmitButton > button:first-child {
        background-color: #4361ee; color: white; border: none;
        border-radius: 8px; font-weight: 600; padding: 0.5rem 1rem;
        transition: all 0.3s ease; box-shadow: 0 4px 6px rgba(67, 97, 238, 0.15);
    }
    div.stButton > button:first-child:hover,
    div.stFormSubmitButton > button:first-child:hover {
        background-color: #3f37c9; transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(67, 97, 238, 0.2);
    }

    table {
        border-collapse: collapse; width: 100%; background-color: white;
        border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    th {
        background-color: #f1f3f5 !important; color: #495057 !important;
        font-weight: 600; font-size: 14px; text-align: center !important;
        padding: 12px 15px !important; border-bottom: 2px solid #dee2e6 !important;
        border-left: none !important; border-right: none !important;
    }
    td {
        text-align: center !important; color: #343a40 !important;
        padding: 10px 15px !important; border-bottom: 1px solid #e9ecef !important;
        border-left: none !important; border-right: none !important;
    }

    tbody tr:hover { background-color: #f8f9fa !important; }

    tbody tr:last-child { background-color: white !important; }
    tbody tr:last-child td {
        font-weight: 700 !important; color: #343a40 !important;
        border-top: 2px solid #ced4da !important; background-color: white !important;
    }
    .edu-sub { color: #6c757d; margin-bottom: 2rem; }
</style>
"""


def run_edu():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_edu()
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        st.markdown("### 📊 교육이수제 현황")
        if code in (429, 500, 502, 503) or isinstance(e, EduBusy):
            st.warning("⏳ 구글 시트가 잠시 응답하지 않고 있습니다. "
                       "**5~10초 뒤 아래 [다시 시도] 버튼을 눌러 주세요.**")
        elif code == 403:
            st.error("구글 시트에 접근할 수 없습니다. 교육이수 시트를 "
                     "**서비스 계정 이메일에 공유**하거나, "
                     "**링크가 있는 모든 사용자 - 뷰어**로 열어 주세요.")
        else:
            st.error("교육 이수 자료를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:200])
        if st.button("🔄 다시 시도", key="edu_retry", type="primary"):
            _reset_edu_conn()
            st.rerun()


def _run_edu():
    st.markdown(EDU_CSS, unsafe_allow_html=True)

    st.title("📊 교육이수제 현황")
    st.markdown("<p class='edu-sub'>개인별 연간 필수 교육 이수 내역 및 "
                "교육비 집계를 실시간으로 조회합니다.</p>", unsafe_allow_html=True)

    df = load_edu_data()

    current_year = datetime.datetime.now().year
    years = list(range(current_year - 5, current_year + 2))

    # 사번·성명은 '엔터'로도 조회되도록 폼 안에 넣었습니다.
    with st.form("edu_search_form", clear_on_submit=False):
        # 다섯 칸을 똑같은 너비로 나누고, 마지막 칸에 버튼을 놓습니다.
        c1, c2, c3, c4, c5 = st.columns(5)
        search_id = c1.text_input("사번 (숫자 입력)", key="edu_id")
        search_name = c2.text_input("성명", key="edu_name")
        start_year = c3.selectbox("시작 연도", years,
                                  index=years.index(current_year - 1), key="edu_y1")
        end_year = c4.selectbox("종료 연도", years,
                                index=years.index(current_year), key="edu_y2")
        # 버튼을 왼쪽 입력칸들과 같은 높이에 맞추기 위한 빈 자리입니다.
        c5.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        go = c5.form_submit_button("조회하기", type="primary",
                                   use_container_width=True)

    if not go:
        return

    if not str(search_id).strip() or not str(search_name).strip():
        st.warning("⚠️ 사번과 성명을 모두 입력해 주세요.")
        return
    if start_year > end_year:
        st.error("⚠️ 시작 연도가 종료 연도보다 클 수 없습니다. 기간을 다시 설정해 주세요.")
        return

    if "사번" not in df.columns or "성명" not in df.columns:
        st.error("시트에 `사번` 또는 `성명` 열이 없습니다. 열 이름을 확인해 주세요.")
        st.caption("지금 시트의 열 : %s" % ", ".join(map(str, df.columns[:15])))
        return

    user_df = df[(df["사번"].astype(str).str.strip() == str(search_id).strip())
                 & (df["성명"].astype(str).str.strip() == str(search_name).strip())].copy()

    if user_df.empty:
        st.info("해당 직원의 데이터가 존재하지 않습니다. 사번과 성명을 다시 확인해 주세요.")
        return

    # ----- 연도 걸러내기 -----
    date_col = "교육시작일자"
    if date_col not in user_df.columns:
        cands = [c for c in user_df.columns if "일자" in str(c) or "시작" in str(c)]
        if cands:
            date_col = cands[0]
        else:
            st.error("시트에 `교육시작일자` 열이 없습니다.")
            return

    user_df[date_col] = user_df[date_col].astype(str)
    picked = pd.to_numeric(user_df[date_col].str.extract(r"(\d{4})")[0], errors="coerce")
    year_df = user_df[(picked >= start_year) & (picked <= end_year)].copy()

    cols = ["교육명", date_col, "교육종료일자", "교육시간", "교육기관", "교육비"]

    cat_col = "교육구분" if "교육구분" in year_df.columns else year_df.columns[5]
    year_df["비교용_교육구분"] = (year_df[cat_col].astype(str)
                            .str.replace(r"[^\w가-힣]", "", regex=True))

    final_data = []
    total_time = 0.0
    total_cost = 0.0

    for cat in EDU_CATEGORIES:
        clean_cat = re.sub(r"[^\w가-힣]", "", cat)
        match = year_df[year_df["비교용_교육구분"] == clean_cat]

        if match.empty:
            final_data.append({"구분": cat, **{c: "-" for c in cols}})
            continue

        for i in range(len(match)):
            row = {"구분": cat}
            for c in cols:
                if c not in match.columns:
                    row[c] = "-"
                    continue
                val = match.iloc[i][c]
                if pd.isna(val) or str(val).strip() == "":
                    row[c] = "-"
                elif c == "교육비":
                    row[c] = "%s 원" % format(int(_e_num(val)), ",")
                elif c == "교육시간":
                    row[c] = _e_int_text(val)
                else:
                    row[c] = val
            final_data.append(row)

            total_time += _e_num(match.iloc[i].get("교육시간", 0))
            total_cost += _e_num(match.iloc[i].get("교육비", 0))

    final_data.append({
        "구분": "합계",
        "교육명": "",
        date_col: "",
        "교육종료일자": "",
        "교육시간": "%s 시간" % _e_int_text(total_time),
        "교육기관": "",
        "교육비": "%s 원" % format(int(total_cost), ","),
    })

    display_df = pd.DataFrame(final_data).set_index("구분")

    st.subheader("✅ %s님의 교육 결과 (%d년 ~ %d년)"
                 % (str(search_name).strip(), start_year, end_year))

    st.table(display_df)
