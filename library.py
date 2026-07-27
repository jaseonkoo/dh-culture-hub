# -*- coding: utf-8 -*-
# ==========================================================
# 📚 사내 도서관 (library.py)
#  - 기존 조직문화 허브(main.py)에 붙는 독립 모듈
#  - 바코드 셀프 대출/반납 (휴대폰 카메라 + USB 스캐너)
#  - 개인정보 최소화: 사번 + 이름만 사용
#  - DB: 구글 시트 파일 "대한사료_도서관_DB"
# ==========================================================
from utils import *          # streamlit(st), datetime, uuid, pd, gspread, time, ServiceAccountCredentials 등
import urllib.request, json

# 휴대폰 카메라 바코드 해석용 (없어도 나머지 기능은 동작)
try:
    from PIL import Image
    import numpy as np
    import zxingcpp
    _SCAN_OK = True
except Exception:
    _SCAN_OK = False

# ---------------- 설정값 (필요 시 수정) ----------------
LIB_DB     = "대한사료_도서관_DB"   # 구글 드라이브에 이 이름으로 빈 시트를 만들어 두세요
ADMIN_PW   = "dhfeed1947"          # 👈 관리자 비밀번호 (반드시 변경)
LOAN_DAYS  = 14                    # 기본 대출 기간(일)
RENEW_DAYS = 7                     # 연장 시 추가 기간(일)
MAX_RENEW  = 1                     # 최대 연장 횟수
MAX_LOANS  = 5                     # 1인 동시 대출 권수

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# 각 시트(탭)의 헤더 - 없으면 자동 생성됨
HEADERS = {
    "books":        ["asset_id", "isbn", "title", "author", "publisher", "year", "category", "location", "status", "cover"],
    "members":      ["saban", "name", "joined"],
    "loans":        ["loan_id", "asset_id", "title", "saban", "name", "loan_date", "due_date", "return_date", "renew_count", "status"],
    "reservations": ["res_id", "isbn", "title", "saban", "name", "res_date", "status"],
    "wishlist":     ["wish_id", "title", "author", "isbn", "saban", "name", "reason", "date", "status"],
}

# ==========================================================
# 구글 시트 접근 (기존 플랫폼과 동일한 방식)
# ==========================================================
@st.cache_resource
def _lib_doc():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
    client = gspread.authorize(creds)
    return client.open(LIB_DB)

def _ws(name):
    """워크시트 반환. 없으면 헤더와 함께 자동 생성."""
    doc = _lib_doc()
    titles = [w.title for w in doc.worksheets()]
    if name not in titles:
        ws = doc.add_worksheet(name, 1000, 26)
        ws.append_row(HEADERS[name])
        return ws
    ws = doc.worksheet(name)
    if not ws.row_values(1):
        ws.append_row(HEADERS[name])
    return ws

@st.cache_data(ttl=30, show_spinner=False)
def _records(name):
    try:
        return _ws(name).get_all_records()
    except Exception:
        return []

def _refresh():
    _records.clear()

def _today():
    return datetime.date.today()

# ==========================================================
# 회원 (사번 + 이름)
# ==========================================================
def _ensure_member(saban, name):
    saban = str(saban).strip(); name = str(name).strip()
    if not saban:
        return None, "사번을 입력하세요."
    for m in _records("members"):
        if str(m.get("saban")).strip() == saban:
            return {"saban": saban, "name": str(m.get("name", "")).strip()}, None
    if not name:
        return None, "처음 이용하시는 사번입니다. 이름도 함께 입력해 주세요."
    _ws("members").append_row([saban, name, str(_today())])
    _refresh()
    return {"saban": saban, "name": name}, None

# ==========================================================
# 도서 상태 / 대출 / 반납
# ==========================================================
def _set_book_status(asset_id, status):
    ws = _ws("books")
    header = ws.row_values(1)
    if "status" not in header:
        return False
    col = header.index("status") + 1
    for i, r in enumerate(ws.get_all_records()):
        if str(r.get("asset_id")).strip() == str(asset_id).strip():
            ws.update_cell(i + 2, col, status)
            return True
    return False

def _is_overdue(loan):
    due = str(loan.get("due_date", ""))
    if not due or loan.get("status") != "대출중":
        return False
    try:
        return _today() > datetime.datetime.strptime(due, "%Y-%m-%d").date()
    except Exception:
        return False

def _first_reservation(title):
    title = str(title).strip()
    res = [r for r in _records("reservations")
           if r.get("status") == "대기" and str(r.get("title")).strip() == title]
    res.sort(key=lambda r: str(r.get("res_date", "")))
    return res[0] if res else None

def _checkout(code, saban, name):
    code = str(code).strip()
    if not code:
        return False, "책 바코드를 스캔하세요."
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    book = next((b for b in _records("books") if str(b.get("asset_id")).strip() == code), None)
    if not book:
        return False, f"등록되지 않은 도서입니다: {code}"
    if book.get("status") == "폐기":
        return False, "폐기된 도서입니다."
    if book.get("status") == "대출중":
        return False, "이미 대출 중인 도서입니다."
    if book.get("status") == "예약중":
        w = _first_reservation(book.get("title", ""))
        if w and str(w.get("saban")).strip() != member["saban"]:
            return False, "다른 직원이 예약한 도서입니다. (예약자 우선)"
        if w:  # 예약자 본인 → 예약 소진
            _mark_reservation_done(w.get("res_id"))
    active = [l for l in _records("loans")
              if str(l.get("saban")).strip() == member["saban"] and l.get("status") == "대출중"]
    if len(active) >= MAX_LOANS:
        return False, f"동시 대출 한도({MAX_LOANS}권)를 초과했습니다."

    loan_id = str(uuid.uuid4())[:8]
    loan_date = _today()
    due = loan_date + datetime.timedelta(days=LOAN_DAYS)
    _ws("loans").append_row([loan_id, code, book.get("title", ""), member["saban"], member["name"],
                             str(loan_date), str(due), "", 0, "대출중"])
    _set_book_status(code, "대출중")
    _refresh()
    return True, {"title": book.get("title", ""), "due": str(due), "name": member["name"]}

def _checkin(code):
    code = str(code).strip()
    if not code:
        return False, "책 바코드를 스캔하세요."
    ws = _ws("loans")
    header = ws.row_values(1)
    records = ws.get_all_records()
    target, target_row = None, None
    for i, r in enumerate(records):
        if str(r.get("asset_id")).strip() == code and r.get("status") == "대출중":
            target, target_row = r, i + 2
    if not target:
        _set_book_status(code, "대출가능")
        return False, "대출 기록이 없는 도서입니다. (이미 반납되었을 수 있어요)"
    ws.update_cell(target_row, header.index("return_date") + 1, str(_today()))
    ws.update_cell(target_row, header.index("status") + 1, "반납완료")
    waiting = _first_reservation(target.get("title", ""))
    _set_book_status(code, "예약중" if waiting else "대출가능")
    overdue = _is_overdue(target)
    _refresh()
    return True, {"title": target.get("title", ""), "overdue": overdue,
                  "waiting": waiting["name"] if waiting else ""}

def _renew(loan_id, saban):
    ws = _ws("loans")
    header = ws.row_values(1)
    for i, r in enumerate(ws.get_all_records()):
        if str(r.get("loan_id")).strip() == str(loan_id).strip():
            if str(r.get("saban")).strip() != str(saban).strip():
                return False, "본인 대출만 연장할 수 있습니다."
            if r.get("status") != "대출중":
                return False, "이미 반납된 대출입니다."
            cnt = int(r.get("renew_count") or 0)
            if cnt >= MAX_RENEW:
                return False, f"더 이상 연장할 수 없습니다. (최대 {MAX_RENEW}회)"
            if _first_reservation(r.get("title", "")):
                return False, "예약 대기자가 있어 연장할 수 없습니다."
            try:
                base = datetime.datetime.strptime(str(r.get("due_date")), "%Y-%m-%d").date()
            except Exception:
                base = _today()
            newdue = base + datetime.timedelta(days=RENEW_DAYS)
            ws.update_cell(i + 2, header.index("due_date") + 1, str(newdue))
            ws.update_cell(i + 2, header.index("renew_count") + 1, cnt + 1)
            _refresh()
            return True, {"due": str(newdue)}
    return False, "대출 기록을 찾을 수 없습니다."

# ==========================================================
# 예약 / 희망도서
# ==========================================================
def _mark_reservation_done(res_id):
    ws = _ws("reservations")
    header = ws.row_values(1)
    for i, r in enumerate(ws.get_all_records()):
        if str(r.get("res_id")).strip() == str(res_id).strip():
            ws.update_cell(i + 2, header.index("status") + 1, "완료")
            return True
    return False

def _reserve(asset_id, saban, name):
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    book = next((b for b in _records("books") if str(b.get("asset_id")).strip() == str(asset_id).strip()), None)
    if not book:
        return False, "도서를 찾을 수 없습니다."
    if book.get("status") == "대출가능":
        return False, "바로 대출 가능한 도서입니다. 예약이 필요 없어요."
    dup = any(r.get("status") == "대기" and str(r.get("saban")).strip() == member["saban"]
              and str(r.get("title")).strip() == str(book.get("title")).strip()
              for r in _records("reservations"))
    if dup:
        return False, "이미 예약 대기 중입니다."
    _ws("reservations").append_row([str(uuid.uuid4())[:8], book.get("isbn", ""), book.get("title", ""),
                                    member["saban"], member["name"], str(_today()), "대기"])
    _refresh()
    return True, "예약 완료. 반납되면 순번대로 안내됩니다."

def _add_wish(saban, name, title, author, reason):
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    if not str(title).strip():
        return False, "희망 도서 제목을 입력하세요."
    _ws("wishlist").append_row([str(uuid.uuid4())[:8], title, author, "", member["saban"],
                               member["name"], reason, str(_today()), "접수"])
    _refresh()
    return True, "희망도서 신청이 접수되었습니다."

def _set_wish_status(wish_id, status):
    ws = _ws("wishlist")
    header = ws.row_values(1)
    for i, r in enumerate(ws.get_all_records()):
        if str(r.get("wish_id")).strip() == str(wish_id).strip():
            ws.update_cell(i + 2, header.index("status") + 1, status)
            _refresh()
            return True
    return False

# ==========================================================
# 도서 등록 / ISBN 자동조회
# ==========================================================
def _get_nl_key():
    """Streamlit Secrets 에서 국립중앙도서관 인증키를 읽어온다. 없으면 None."""
    try:
        return st.secrets["nl"]["cert_key"]
    except Exception:
        return None

def _pick(d, *names):
    """응답 필드명이 조금 달라도 견디도록, 여러 후보 중 값이 있는 것을 고른다."""
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""

def _lookup_nl(isbn, key):
    """국립중앙도서관 서지정보(SEOJI) API. 공공데이터 + 상당수 표지(TITLE_URL) 제공."""
    try:
        url = ("https://www.nl.go.kr/seoji/SearchApi.do?cert_key=" + key +
               "&result_style=json&page_no=1&page_size=10&isbn=" + isbn)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        data = json.loads(raw, strict=False)
        docs = data.get("docs") or data.get("DOCS") or []
        if not docs:
            return None
        d = docs[0]
        title = _pick(d, "TITLE").split(" / ")[0].strip()          # "제목 / 저자" → 제목만
        predate = _pick(d, "PUBLISH_PREDATE", "PUBLISH_DATE", "REAL_PUBLISH_DATE")
        return {
            "isbn": isbn,
            "title": title,
            "author": _pick(d, "AUTHOR"),
            "publisher": _pick(d, "PUBLISHER"),
            "year": predate[:4] if predate else "",
            "category": _pick(d, "SUBJECT"),                        # KDC 분류
            "cover": _pick(d, "TITLE_URL", "BOOK_TB_URL"),          # 표지 이미지
        }
    except Exception:
        return None

def _lookup_google(isbn):
    """구글 북스 - 해외 원서 보조용."""
    try:
        url = "https://www.googleapis.com/books/v1/volumes?q=isbn:" + isbn
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("items"):
            return None
        v = data["items"][0].get("volumeInfo", {})
        cover = ""
        il = v.get("imageLinks", {})
        if il:
            cover = (il.get("thumbnail") or il.get("smallThumbnail") or "").replace("http://", "https://")
        return {
            "isbn": isbn, "title": v.get("title", ""),
            "author": ", ".join(v.get("authors", [])), "publisher": v.get("publisher", ""),
            "year": str(v.get("publishedDate", ""))[:4], "category": ", ".join(v.get("categories", [])),
            "cover": cover,
        }
    except Exception:
        return None

def _lookup_isbn(isbn):
    """도서 정보 조회. 반환값: (정보 dict 또는 None, 안내 메시지 또는 None)"""
    isbn = "".join(ch for ch in str(isbn) if ch.isdigit() or ch in "Xx")
    if not isbn:
        return None, "ISBN을 입력하세요."
    key = _get_nl_key()
    if key:
        info = _lookup_nl(isbn, key)       # 1순위: 국립중앙도서관(국내서)
        if info:
            return info, None
    info = _lookup_google(isbn)             # 2순위: 구글 북스(해외서)
    if info:
        return info, None
    if not key:
        return None, "국립중앙도서관 인증키가 설정되어 있지 않습니다. 앱 설정의 Secrets에 [nl] cert_key 를 추가해 주세요."
    return None, "도서 정보를 찾지 못했습니다. ISBN을 확인하거나 직접 입력해 주세요."

def _add_book(b):
    asset = str(b.get("asset_id", "")).strip()
    if not asset:
        return False, "자산번호(바코드)를 입력하세요."
    if not str(b.get("title", "")).strip():
        return False, "제목을 입력하세요."
    if any(str(x.get("asset_id")).strip() == asset for x in _records("books")):
        return False, f"이미 존재하는 자산번호입니다: {asset}"
    _ws("books").append_row([asset, b.get("isbn", ""), b.get("title", ""), b.get("author", ""),
                            b.get("publisher", ""), b.get("year", ""), b.get("category", ""),
                            b.get("location", ""), "대출가능", b.get("cover", "")])
    _refresh()
    return True, f"등록 완료: {b.get('title')}"

# ==========================================================
# 바코드 이미지 해석 (휴대폰 카메라)
# ==========================================================
def _decode(img_file):
    if not _SCAN_OK or img_file is None:
        return None
    try:
        image = Image.open(img_file).convert("RGB")
        results = zxingcpp.read_barcodes(np.array(image))
        if results:
            return results[0].text.strip()
    except Exception:
        return None
    return None

def _status_badge(s):
    color = {"대출가능": "#059669", "대출중": "#dc2626", "예약중": "#d97706", "폐기": "#6b7280"}.get(s, "#6b7280")
    return f"<span style='background:{color}22;color:{color};font-weight:700;font-size:.8em;padding:2px 8px;border-radius:20px;'>{s}</span>"

def _availability_by_title(title, books):
    """같은 제목의 여러 권(복본) 중 한 권이라도 빌릴 수 있으면 '대출가능'으로 본다."""
    copies = [b for b in books if str(b.get("title")).strip() == str(title).strip()]
    if any(b.get("status") == "대출가능" for b in copies):
        return "대출가능"
    if any(b.get("status") == "예약중" for b in copies):
        return "예약중"
    return "대출중" if copies else "-"

def _home_card(book, status, rank=None, count=None, title_fallback=""):
    """표지 + 정보 + 대출가능 배지가 들어간 카드 한 장을 그린다."""
    if book:
        cover = f"<img src='{book.get('cover')}'>" if book.get("cover") else "<img>"
        title = book.get("title") or title_fallback
        meta = " · ".join([str(book.get(k)) for k in ["author", "publisher", "year"] if book.get(k)])
        loc = book.get("location") or "-"
    else:
        cover, title, meta, loc = "<img>", title_fallback, "", "-"
    rank_html = f"<span style='font-weight:800;color:#2563eb;margin-right:6px;'>{rank}위</span>" if rank else ""
    count_html = f"<span class='lib-hint'> · 누적 대출 {count}회</span>" if count else ""
    st.markdown(f"""<div class="book-card">{cover}
        <div>{rank_html}<b>{title}</b>{count_html}<br>
        <span class="lib-hint">{meta}</span><br>
        <span class="lib-hint">위치 {loc}</span><br>
        {_status_badge(status)}</div></div>""", unsafe_allow_html=True)

# ==========================================================
# 화면
# ==========================================================
def run_library():
    st.markdown("""
        <style>
        .book-card { border:1px solid #e5e7eb; border-radius:12px; padding:14px; margin-bottom:10px;
                     background:#fff; display:flex; gap:12px; }
        .book-card img { width:52px; height:72px; object-fit:cover; border-radius:6px; background:#eef1f4; }
        .lib-hint { color:#6b7280; font-size:.85em; }
        </style>
    """, unsafe_allow_html=True)

    st.header("📚 사내 도서관")
    st.caption("책에 붙은 바코드로 셀프 대출·반납하세요. 개인정보는 사번·이름만 사용합니다.")
    if not _SCAN_OK:
        st.info("ℹ️ 휴대폰 카메라 스캔 기능을 쓰려면 requirements.txt에 `zxing-cpp`, `pillow`를 추가해 주세요. (직접 입력·USB 스캐너는 지금도 사용 가능)")
    st.markdown("---")

    tab_home, tab_lend, tab_search, tab_my, tab_admin = st.tabs(
        ["🏠 홈", "📕 대출·반납", "🔍 도서 검색", "🙋 내 대출·희망도서", "👑 관리자"])

    # ---------------- 홈 (최근 입고 · 인기 대출) ----------------
    with tab_home:
        home_books = [b for b in _records("books") if b.get("status") != "폐기"]
        home_loans = _records("loans")

        st.subheader("🆕 최근 입고된 책")
        recent = list(reversed(home_books))[:5]   # 가장 최근에 등록한 순서(시트 맨 아래가 최신)
        if not recent:
            st.info("아직 등록된 도서가 없습니다. 관리자 탭에서 도서를 등록해 주세요.")
        else:
            for b in recent:
                _home_card(b, b.get("status", "대출가능"))

        st.markdown("---")
        st.subheader("🔥 많이 대출된 책 TOP 5")
        counts = {}
        for l in home_loans:
            t = str(l.get("title", "")).strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:5]
        if not top:
            st.info("아직 대출 기록이 없습니다.")
        else:
            for rank, (title, c) in enumerate(top, start=1):
                book = next((b for b in home_books if str(b.get("title")).strip() == title), None)
                avail = _availability_by_title(title, home_books)
                _home_card(book, avail, rank=rank, count=c, title_fallback=title)

    # ---------------- 대출 / 반납 ----------------
    with tab_lend:
        mode = st.radio("무엇을 하시겠어요?", ["📕 대출하기", "📗 반납하기"], horizontal=True, key="lib_mode")
        use_cam = st.checkbox("📷 휴대폰 카메라로 스캔", key="lib_usecam",
                              help="체크하면 카메라가 켜집니다. USB 스캐너나 직접 입력은 체크 없이 사용하세요.")

        # ===== 대출 =====
        if mode == "📕 대출하기":
            c1, c2 = st.columns(2)
            saban = c1.text_input("사번", key="co_saban", placeholder="사번 입력")
            name = c2.text_input("이름 (처음 이용 시 1회)", key="co_name", placeholder="이름")

            if use_cam:
                img = st.camera_input("책 바코드를 비추고 촬영하세요", key="co_cam")
                code = _decode(img)
                if code and st.session_state.get("co_last") != code:
                    ok, res = _checkout(code, saban, name)
                    st.session_state["co_last"] = code
                    if ok:
                        st.success(f"✅ **{res['title']}** 대출 완료 · 반납예정일 **{res['due']}**")
                        st.balloons()
                    else:
                        st.error(f"⚠️ {res}")
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 조금 더 가까이서 다시 촬영해 주세요.")
            else:
                with st.form("co_form", clear_on_submit=True):
                    manual = st.text_input("책 바코드 (USB 스캐너로 스캔 또는 자산번호 직접 입력)")
                    submitted = st.form_submit_button("대출하기", use_container_width=True)
                if submitted:
                    ok, res = _checkout(manual, saban, name)
                    if ok:
                        st.success(f"✅ **{res['title']}** 대출 완료 · 반납예정일 **{res['due']}**")
                        st.balloons()
                    else:
                        st.error(f"⚠️ {res}")
            st.markdown("<p class='lib-hint'>USB 스캐너는 바코드 칸에 커서를 두고 스캔하면 자동 입력됩니다.</p>", unsafe_allow_html=True)

        # ===== 반납 =====
        else:
            if use_cam:
                img = st.camera_input("반납할 책 바코드를 촬영하세요", key="ci_cam")
                code = _decode(img)
                if code and st.session_state.get("ci_last") != code:
                    ok, res = _checkin(code)
                    st.session_state["ci_last"] = code
                    if ok:
                        extra = " (연체 반납)" if res["overdue"] else ""
                        wait = f" · 🔔 예약자 {res['waiting']}님 대기" if res["waiting"] else ""
                        st.success(f"✅ **{res['title']}** 반납 완료{extra}{wait}")
                    else:
                        st.error(f"⚠️ {res}")
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 다시 촬영해 주세요.")
            else:
                with st.form("ci_form", clear_on_submit=True):
                    manual = st.text_input("반납할 책 바코드")
                    submitted = st.form_submit_button("반납하기", use_container_width=True)
                if submitted:
                    ok, res = _checkin(manual)
                    if ok:
                        extra = " (연체 반납)" if res["overdue"] else ""
                        wait = f" · 🔔 예약자 {res['waiting']}님 대기" if res["waiting"] else ""
                        st.success(f"✅ **{res['title']}** 반납 완료{extra}{wait}")
                    else:
                        st.error(f"⚠️ {res}")
            st.markdown("<p class='lib-hint'>반납은 사번 없이 책 바코드만 스캔하면 됩니다.</p>", unsafe_allow_html=True)

    # ---------------- 도서 검색 ----------------
    with tab_search:
        q = st.text_input("제목 · 저자 · ISBN 검색", key="lib_q", placeholder="검색어를 입력하세요")
        books = [b for b in _records("books") if b.get("status") != "폐기"]
        ql = q.strip().lower()
        if ql:
            books = [b for b in books if any(
                ql in str(b.get(k, "")).lower() for k in ["title", "author", "isbn", "asset_id", "category", "publisher"])]
        books = sorted(books, key=lambda b: str(b.get("title", "")))
        st.caption(f"총 {len(books)}권")
        for b in books[:100]:
            cover = f"<img src='{b.get('cover')}'>" if b.get("cover") else "<img>"
            meta = " · ".join([str(b.get(k)) for k in ["author", "publisher", "year"] if b.get(k)])
            st.markdown(f"""<div class="book-card">{cover}
                <div><b>{b.get('title')}</b><br>
                <span class="lib-hint">{meta}</span><br>
                <span class="lib-hint">자산번호 {b.get('asset_id')} · 위치 {b.get('location') or '-'}</span><br>
                {_status_badge(b.get('status', '대출가능'))}</div></div>""", unsafe_allow_html=True)
            if b.get("status") in ("대출중", "예약중"):
                with st.expander(f"🔖 '{b.get('title')}' 예약하기"):
                    with st.form(f"res_{b.get('asset_id')}", clear_on_submit=True):
                        rc1, rc2 = st.columns(2)
                        rs = rc1.text_input("사번", key=f"rs_{b.get('asset_id')}")
                        rn = rc2.text_input("이름", key=f"rn_{b.get('asset_id')}")
                        if st.form_submit_button("예약 신청"):
                            ok, msg = _reserve(b.get("asset_id"), rs, rn)
                            (st.success if ok else st.error)(msg)

    # ---------------- 내 대출 / 희망도서 ----------------
    with tab_my:
        st.subheader("📖 내 대출 현황")
        msaban = st.text_input("사번으로 조회", key="my_saban", placeholder="사번 입력")
        if msaban.strip():
            mine = [l for l in _records("loans")
                    if str(l.get("saban")).strip() == msaban.strip() and l.get("status") == "대출중"]
            if not mine:
                st.info("현재 대출 중인 도서가 없습니다.")
            for l in mine:
                over = _is_overdue(l)
                cnt = int(l.get("renew_count") or 0)
                col1, col2 = st.columns([3, 1])
                status_txt = "🔴 연체" if over else "대출중"
                col1.markdown(f"**{l.get('title')}**  \n반납예정 {l.get('due_date')} · {status_txt} · 연장 {cnt}/{MAX_RENEW}회")
                if cnt < MAX_RENEW:
                    if col2.button("연장", key=f"rnw_{l.get('loan_id')}", use_container_width=True):
                        ok, res = _renew(l.get("loan_id"), msaban)
                        if ok:
                            st.success(f"연장 완료 · 새 반납예정일 {res['due']}"); time.sleep(1); st.rerun()
                        else:
                            st.error(res)
                else:
                    col2.caption("연장불가")

        st.markdown("---")
        st.subheader("🙋 희망도서 신청")
        with st.form("wish_form", clear_on_submit=True):
            wc1, wc2 = st.columns(2)
            ws_ = wc1.text_input("사번")
            wn_ = wc2.text_input("이름")
            wt_ = st.text_input("도서 제목")
            wa_ = st.text_input("저자 (선택)")
            wr_ = st.text_area("신청 사유 (선택)", height=70)
            if st.form_submit_button("신청하기", use_container_width=True):
                ok, msg = _add_wish(ws_, wn_, wt_, wa_, wr_)
                (st.success if ok else st.error)(msg)

    # ---------------- 관리자 ----------------
    with tab_admin:
        if "lib_admin" not in st.session_state:
            st.session_state.lib_admin = False
        if not st.session_state.lib_admin:
            pw = st.text_input("관리자 비밀번호", type="password", key="lib_admin_pw")
            if st.button("로그인", key="lib_admin_login"):
                if pw == ADMIN_PW:
                    st.session_state.lib_admin = True; st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        else:
            if st.button("로그아웃", key="lib_admin_logout"):
                st.session_state.lib_admin = False; st.rerun()

            books = _records("books")
            loans = _records("loans")
            active = [l for l in loans if l.get("status") == "대출중"]
            overdue = [l for l in active if _is_overdue(l)]
            wishes = [w for w in _records("wishlist") if w.get("status") == "접수"]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 장서", len([b for b in books if b.get("status") != "폐기"]))
            m2.metric("대출 중", len(active))
            m3.metric("연체", len(overdue))
            m4.metric("희망도서", len(wishes))

            with st.expander("➕ 도서 등록", expanded=True):
                ic1, ic2 = st.columns([3, 1])
                isbn_in = ic1.text_input("ISBN (조회로 자동 채우기)", key="reg_isbn")
                if ic2.button("ISBN 조회", key="reg_lookup", use_container_width=True):
                    info, err = _lookup_isbn(isbn_in)
                    if info:
                        for k in ["title", "author", "publisher", "year", "category", "cover"]:
                            st.session_state[f"reg_{k}"] = info[k]
                        st.success("정보를 불러왔습니다. 아래에서 확인 후 등록하세요.")
                    else:
                        st.warning(err or "도서 정보를 찾지 못했습니다. 직접 입력해 주세요.")
                with st.form("book_form", clear_on_submit=True):
                    asset = st.text_input("자산번호(책에 붙일 바코드) *")
                    title = st.text_input("제목 *", value=st.session_state.get("reg_title", ""))
                    bc1, bc2 = st.columns(2)
                    author = bc1.text_input("저자", value=st.session_state.get("reg_author", ""))
                    publisher = bc2.text_input("출판사", value=st.session_state.get("reg_publisher", ""))
                    bc3, bc4 = st.columns(2)
                    year = bc3.text_input("출판연도", value=st.session_state.get("reg_year", ""))
                    category = bc4.text_input("분류", value=st.session_state.get("reg_category", ""))
                    location = st.text_input("위치 (예: A-3)")
                    if st.form_submit_button("등록", use_container_width=True):
                        ok, msg = _add_book({
                            "asset_id": asset, "isbn": isbn_in, "title": title, "author": author,
                            "publisher": publisher, "year": year, "category": category,
                            "location": location, "cover": st.session_state.get("reg_cover", "")})
                        if ok:
                            for k in ["reg_title", "reg_author", "reg_publisher", "reg_year", "reg_category", "reg_cover"]:
                                st.session_state[k] = ""
                            st.success(msg)
                        else:
                            st.error(msg)

            with st.expander("👤 회원 등록"):
                with st.form("member_form", clear_on_submit=True):
                    mc1, mc2 = st.columns(2)
                    ms = mc1.text_input("사번")
                    mn = mc2.text_input("이름")
                    if st.form_submit_button("회원 등록"):
                        mem, err = _ensure_member(ms, mn)
                        (st.error(err) if err else st.success(f"등록/확인 완료: {mem['name']}"))

            with st.expander(f"⏰ 연체 목록 ({len(overdue)})"):
                if not overdue:
                    st.info("연체 도서가 없습니다.")
                else:
                    rows = []
                    for l in overdue:
                        try:
                            days = (_today() - datetime.datetime.strptime(str(l.get("due_date")), "%Y-%m-%d").date()).days
                        except Exception:
                            days = ""
                        rows.append({"도서": l.get("title"), "대출자": f"{l.get('name')}({l.get('saban')})",
                                     "반납예정": l.get("due_date"), "연체일": days})
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            with st.expander(f"📗 전체 대출 현황 ({len(active)})"):
                if active:
                    df = pd.DataFrame([{"도서": l.get("title"), "대출자": f"{l.get('name')}({l.get('saban')})",
                                        "대출일": l.get("loan_date"), "반납예정": l.get("due_date"),
                                        "연체": "🔴" if _is_overdue(l) else ""} for l in active])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("대출 중인 도서가 없습니다.")

            with st.expander(f"🙋 희망도서 신청 ({len(wishes)})"):
                allw = list(reversed(_records("wishlist")))
                if not allw:
                    st.info("신청 내역이 없습니다.")
                for w in allw:
                    wc1, wc2, wc3 = st.columns([3, 1, 1])
                    wc1.markdown(f"**{w.get('title')}** {w.get('author') or ''}  \n"
                                 f"<span class='lib-hint'>{w.get('name')} · {w.get('status')}</span>", unsafe_allow_html=True)
                    if wc2.button("구매완료", key=f"wd_{w.get('wish_id')}", use_container_width=True):
                        _set_wish_status(w.get("wish_id"), "구매완료"); st.rerun()
                    if wc3.button("반려", key=f"wr_{w.get('wish_id')}", use_container_width=True):
                        _set_wish_status(w.get("wish_id"), "반려"); st.rerun()
