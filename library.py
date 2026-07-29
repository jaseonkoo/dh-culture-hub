# -*- coding: utf-8 -*-
# ==========================================================
# 📚 사내 도서관 (library.py)  —  ISBN + 수량관리 버전
#  - 책에 인쇄된 ISBN 바코드로 셀프 대출/반납 (별도 라벨 불필요)
#  - 같은 책 여러 권은 '수량'으로 관리 (총 n권 중 대출가능 m권)
#  - 휴대폰 카메라 + USB 스캐너 겸용
#  - 개인정보 최소화: 사번 + 이름
#  - DB: 구글 시트 "대한사료_도서관_DB"
#  - ISBN 조회: 국립중앙도서관(공공데이터) + 구글북스(해외 보조)
# ==========================================================
from utils import *          # st, datetime, uuid, pd, gspread, time, ServiceAccountCredentials 등
import urllib.request, json

# 휴대폰 카메라 바코드 해석용 (없어도 나머지 기능은 동작)
try:
    from PIL import Image
    import numpy as np
    import zxingcpp
    _SCAN_OK = True
except Exception:
    _SCAN_OK = False

# ---------------- 설정값 ----------------
LIB_DB     = "대한사료_도서관_DB"
ADMIN_PW   = "dhfeed1947"    # 👈 관리자 비밀번호 (반드시 변경)
LOAN_DAYS  = 14
RENEW_DAYS = 7
MAX_RENEW  = 1
MAX_LOANS  = 5

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# 각 시트(탭) 헤더 - 없으면 자동 생성
HEADERS = {
    "books":        ["isbn", "title", "author", "publisher", "year", "category", "location",
                     "total_qty", "available_qty", "status", "cover"],
    "members":      ["saban", "name", "joined"],
    "loans":        ["loan_id", "isbn", "title", "saban", "name",
                     "loan_date", "due_date", "return_date", "renew_count", "status"],
    "reservations": ["res_id", "isbn", "title", "saban", "name", "res_date", "status"],
    "wishlist":     ["wish_id", "title", "author", "isbn", "saban", "name", "reason", "date", "status"],
}

# ==========================================================
# 구글 시트 접근
# ==========================================================
@st.cache_resource
def _lib_doc():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
    client = gspread.authorize(creds)
    return client.open(LIB_DB)

@st.cache_resource
def _ws_cache():
    """탭(워크시트) 핸들·헤더 캐시. 구글 API 호출 횟수를 최소화하기 위한 것."""
    return {}

class LibBusy(Exception):
    """구글 시트 접속이 일시적으로 막혔을 때(사용량 초과 등)."""
    pass

def _retry(fn, *a, **kw):
    """구글 시트 호출을 몇 번 다시 시도. 사용량 초과(429)·일시 오류(5xx) 대응."""
    last = None
    for i in range(4):
        try:
            return fn(*a, **kw)
        except gspread.exceptions.APIError as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (429, 500, 502, 503):
                last = e
                time.sleep(1.2 * (i + 1))
                continue
            raise
    raise LibBusy(str(last))

def _ws(name):
    """탭 핸들을 돌려준다. 한 번 찾은 탭은 캐시해 두고 재사용한다."""
    cache = _ws_cache()
    if name in cache:
        return cache[name]
    doc = _lib_doc()
    try:
        ws = _retry(doc.worksheet, name)
        try:
            first = _retry(ws.row_values, 1)
        except Exception:
            first = None
        if not first:
            _retry(ws.append_row, HEADERS[name])
            first = list(HEADERS[name])
    except gspread.exceptions.WorksheetNotFound:
        ws = _retry(doc.add_worksheet, title=name, rows=1000, cols=26)
        _retry(ws.append_row, HEADERS[name])
        first = list(HEADERS[name])
    cache[name] = ws
    cache["__hdr__" + name] = first
    return ws

def _header(name):
    """해당 탭의 첫 줄(열 이름)을 돌려준다. (캐시 사용)"""
    cache = _ws_cache()
    if "__hdr__" + name not in cache:
        _ws(name)
    return cache.get("__hdr__" + name, list(HEADERS[name]))

def _col(name, field):
    """열 번호(1부터). 시트에 해당 열이 없으면 기본 헤더 순서를 사용."""
    hdr = _header(name)
    try:
        return hdr.index(field) + 1
    except ValueError:
        return HEADERS[name].index(field) + 1

@st.cache_data(ttl=60, show_spinner=False)
def _records(name):
    try:
        return _retry(_ws(name).get_all_records)
    except Exception:
        return []

def _refresh():
    _records.clear()

def _reset_conn():
    """탭 캐시 초기화 (시트 구조를 바꿨을 때 사용)."""
    try:
        _ws_cache().clear()
    except Exception:
        pass
    _records.clear()

def _today():
    return datetime.date.today()

def _norm_isbn(x):
    """하이픈·공백 제거해 매칭용으로 정규화 (숫자/문자 유지, 대문자)."""
    return "".join(ch for ch in str(x or "").strip().upper() if ch.isalnum())

def _to_int(v, default=0):
    try:
        return int(str(v).strip())
    except Exception:
        return default

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
    _retry(_ws("members").append_row, [saban, name, str(_today())])
    _refresh()
    return {"saban": saban, "name": name}, None

# ==========================================================
# 도서 (ISBN 키 + 수량)
# ==========================================================
def _find_book(isbn):
    isbn = _norm_isbn(isbn)
    for b in _records("books"):
        if _norm_isbn(b.get("isbn")) == isbn:
            return b
    return None

def _book_avail_label(book):
    if not book:
        return "-"
    if book.get("status") == "폐기":
        return "폐기"
    if _to_int(book.get("available_qty")) > 0:
        return "대출가능"
    if _first_reservation(book.get("isbn", "")):
        return "예약중"
    return "대출중"

def _adjust_available(isbn, delta):
    """available_qty 를 delta 만큼 조정(0~total 범위로 제한)."""
    isbn = _norm_isbn(isbn)
    ws = _ws("books"); ca = _col("books", "available_qty")
    for i, r in enumerate(_records("books")):
        if _norm_isbn(r.get("isbn")) == isbn:
            cur = _to_int(r.get("available_qty"))
            tot = _to_int(r.get("total_qty"), cur)
            newv = max(0, min(cur + delta, tot))
            _retry(ws.update_cell, i + 2, ca, newv)
            return newv
    return None

def _is_overdue(loan):
    due = str(loan.get("due_date", ""))
    if not due or loan.get("status") != "대출중":
        return False
    try:
        return _today() > datetime.datetime.strptime(due, "%Y-%m-%d").date()
    except Exception:
        return False

def _first_reservation(isbn):
    isbn = _norm_isbn(isbn)
    res = [r for r in _records("reservations")
           if r.get("status") == "대기" and _norm_isbn(r.get("isbn")) == isbn]
    res.sort(key=lambda r: str(r.get("res_date", "")))
    return res[0] if res else None

# ---------------- 대출 ----------------
def _checkout(isbn, saban, name):
    isbn = _norm_isbn(isbn)
    if not isbn:
        return False, "책의 ISBN 바코드를 스캔하세요."
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    book = _find_book(isbn)
    if not book:
        return False, f"등록되지 않은 도서입니다. (ISBN {isbn}) 관리자에게 등록을 요청하세요."
    if book.get("status") == "폐기":
        return False, "폐기된 도서입니다."

    my_active = [l for l in _records("loans")
                 if l.get("status") == "대출중" and str(l.get("saban")).strip() == member["saban"]]
    if any(_norm_isbn(l.get("isbn")) == isbn for l in my_active):
        return False, "이미 이 책을 대출 중입니다."
    if len(my_active) >= MAX_LOANS:
        return False, f"동시 대출 한도({MAX_LOANS}권)를 초과했습니다."
    if _to_int(book.get("available_qty")) <= 0:
        return False, "현재 모든 권이 대출 중입니다. '검색' 탭에서 예약할 수 있어요."

    loan_id = str(uuid.uuid4())[:8]
    loan_date = _today()
    due = loan_date + datetime.timedelta(days=LOAN_DAYS)
    _retry(_ws("loans").append_row,
           [loan_id, isbn, book.get("title", ""), member["saban"], member["name"],
            str(loan_date), str(due), "", 0, "대출중"])
    _adjust_available(isbn, -1)
    _refresh()
    return True, {"title": book.get("title", ""), "due": str(due), "name": member["name"]}

# ---------------- 반납 ----------------
def _checkin(isbn, saban=""):
    isbn = _norm_isbn(isbn)
    if not isbn:
        return False, "책의 ISBN 바코드를 스캔하세요."
    book = _find_book(isbn)
    if not book:
        return False, f"등록되지 않은 도서입니다. (ISBN {isbn})"
    ws = _ws("loans")
    open_loans = [(i + 2, r) for i, r in enumerate(_records("loans"))
                  if _norm_isbn(r.get("isbn")) == isbn and r.get("status") == "대출중"]
    if not open_loans:
        return False, "대출 중이 아닌 책입니다. (이미 반납되었을 수 있어요)"

    if len(open_loans) == 1:
        target = open_loans[0]
    else:
        saban = str(saban).strip()
        if not saban:
            return False, {"need_saban": True,
                           "msg": "이 책은 여러 권이 대출 중이에요. 반납자의 사번을 입력한 뒤 다시 시도해 주세요."}
        cand = [t for t in open_loans if str(t[1].get("saban")).strip() == saban]
        if not cand:
            return False, {"need_saban": True, "msg": "해당 사번으로 이 책을 대출한 기록이 없어요. 사번을 확인해 주세요."}
        cand.sort(key=lambda t: str(t[1].get("due_date", "")))
        target = cand[0]

    row, loan = target
    _retry(ws.update_cell, row, _col("loans", "return_date"), str(_today()))
    _retry(ws.update_cell, row, _col("loans", "status"), "반납완료")
    _adjust_available(isbn, +1)
    waiting = _first_reservation(isbn)
    overdue = _is_overdue(loan)
    _refresh()
    return True, {"title": book.get("title", ""), "overdue": overdue,
                  "waiting": waiting["name"] if waiting else "", "borrower": str(loan.get("name", ""))}

# ---------------- 연장 ----------------
def _renew(loan_id, saban):
    ws = _ws("loans")
    for i, r in enumerate(_records("loans")):
        if str(r.get("loan_id")).strip() == str(loan_id).strip():
            if str(r.get("saban")).strip() != str(saban).strip():
                return False, "본인 대출만 연장할 수 있습니다."
            if r.get("status") != "대출중":
                return False, "이미 반납된 대출입니다."
            cnt = _to_int(r.get("renew_count"))
            if cnt >= MAX_RENEW:
                return False, f"더 이상 연장할 수 없습니다. (최대 {MAX_RENEW}회)"
            if _first_reservation(r.get("isbn", "")):
                return False, "예약 대기자가 있어 연장할 수 없습니다."
            try:
                base = datetime.datetime.strptime(str(r.get("due_date")), "%Y-%m-%d").date()
            except Exception:
                base = _today()
            newdue = base + datetime.timedelta(days=RENEW_DAYS)
            _retry(ws.update_cell, i + 2, _col("loans", "due_date"), str(newdue))
            _retry(ws.update_cell, i + 2, _col("loans", "renew_count"), cnt + 1)
            _refresh()
            return True, {"due": str(newdue)}
    return False, "대출 기록을 찾을 수 없습니다."

# ---------------- 예약 / 희망도서 ----------------
def _reserve(isbn, saban, name):
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    book = _find_book(isbn)
    if not book:
        return False, "도서를 찾을 수 없습니다."
    if _to_int(book.get("available_qty")) > 0:
        return False, "지금 대출 가능한 책입니다. 예약이 필요 없어요."
    nisbn = _norm_isbn(isbn)
    dup = any(r.get("status") == "대기" and str(r.get("saban")).strip() == member["saban"]
              and _norm_isbn(r.get("isbn")) == nisbn for r in _records("reservations"))
    if dup:
        return False, "이미 예약 대기 중입니다."
    _retry(_ws("reservations").append_row,
           [str(uuid.uuid4())[:8], nisbn, book.get("title", ""),
            member["saban"], member["name"], str(_today()), "대기"])
    _refresh()
    return True, "예약 완료. 반납되면 안내됩니다."

def _add_wish(saban, name, title, author, reason):
    member, err = _ensure_member(saban, name)
    if err:
        return False, err
    if not str(title).strip():
        return False, "희망 도서 제목을 입력하세요."
    _retry(_ws("wishlist").append_row,
           [str(uuid.uuid4())[:8], title, author, "", member["saban"],
            member["name"], reason, str(_today()), "접수"])
    _refresh()
    return True, "희망도서 신청이 접수되었습니다."

def _set_wish_status(wish_id, status):
    ws = _ws("wishlist")
    for i, r in enumerate(_records("wishlist")):
        if str(r.get("wish_id")).strip() == str(wish_id).strip():
            _retry(ws.update_cell, i + 2, _col("wishlist", "status"), status)
            _refresh()
            return True
    return False

# ==========================================================
# 도서 등록 / ISBN 자동조회
# ==========================================================
def _get_nl_key():
    try:
        return st.secrets["nl"]["cert_key"]
    except Exception:
        return None

def _pick(d, *names):
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""

def _lookup_nl(isbn, key):
    """국립중앙도서관 서지정보(SEOJI) API."""
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
        title = _pick(d, "TITLE").split(" / ")[0].strip()
        predate = _pick(d, "PUBLISH_PREDATE", "PUBLISH_DATE", "REAL_PUBLISH_DATE")
        return {
            "isbn": isbn, "title": title, "author": _pick(d, "AUTHOR"),
            "publisher": _pick(d, "PUBLISHER"), "year": predate[:4] if predate else "",
            "category": _pick(d, "SUBJECT"), "cover": _pick(d, "TITLE_URL", "BOOK_TB_URL"),
        }
    except Exception:
        return None

def _lookup_google(isbn):
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
        return {"isbn": isbn, "title": v.get("title", ""), "author": ", ".join(v.get("authors", [])),
                "publisher": v.get("publisher", ""), "year": str(v.get("publishedDate", ""))[:4],
                "category": ", ".join(v.get("categories", [])), "cover": cover}
    except Exception:
        return None

def _lookup_isbn(isbn):
    """반환값: (정보 dict 또는 None, 안내 메시지 또는 None)"""
    isbn = "".join(ch for ch in str(isbn) if ch.isdigit() or ch in "Xx")
    if not isbn:
        return None, "ISBN을 입력하세요."
    key = _get_nl_key()
    if key:
        info = _lookup_nl(isbn, key)
        if info:
            return info, None
    info = _lookup_google(isbn)
    if info:
        return info, None
    if not key:
        return None, "국립중앙도서관 인증키가 설정되어 있지 않습니다. 앱 설정의 Secrets에 [nl] cert_key 를 추가해 주세요."
    return None, "도서 정보를 찾지 못했습니다. ISBN을 확인하거나 직접 입력해 주세요."

def _add_book(b):
    isbn = _norm_isbn(b.get("isbn"))
    if not isbn:
        return False, "ISBN을 입력(스캔)하세요. ISBN이 없는 자료는 임의의 숫자코드를 부여해 주세요."
    if not str(b.get("title", "")).strip():
        return False, "제목을 입력하세요."
    qty = max(1, _to_int(b.get("qty"), 1))
    existing = _find_book(isbn)
    if existing:
        ws = _ws("books")
        for i, r in enumerate(_records("books")):
            if _norm_isbn(r.get("isbn")) == isbn:
                t = _to_int(r.get("total_qty")) + qty
                a = _to_int(r.get("available_qty")) + qty
                _retry(ws.update_cell, i + 2, _col("books", "total_qty"), t)
                _retry(ws.update_cell, i + 2, _col("books", "available_qty"), a)
                if r.get("status") == "폐기":
                    _retry(ws.update_cell, i + 2, _col("books", "status"), "정상")
                _refresh()
                return True, f"기존 도서에 {qty}권 추가 (총 {t}권): {existing.get('title')}"
    _retry(_ws("books").append_row,
           [isbn, b.get("title", ""), b.get("author", ""), b.get("publisher", ""),
            b.get("year", ""), b.get("category", ""), b.get("location", ""),
            qty, qty, "정상", b.get("cover", "")])
    _refresh()
    return True, f"등록 완료: {b.get('title')} ({qty}권)"

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

def _qty_text(book):
    if not book:
        return ""
    return f"대출가능 {_to_int(book.get('available_qty'))} / 총 {_to_int(book.get('total_qty'))}권"

def _home_card(book, rank=None, count=None, title_fallback=""):
    if book:
        cover = f"<img src='{book.get('cover')}'>" if book.get("cover") else "<img>"
        title = book.get("title") or title_fallback
        meta = " · ".join([str(book.get(k)) for k in ["author", "publisher", "year"] if book.get(k)])
        loc = book.get("location") or "-"
        qty = _qty_text(book)
    else:
        cover, title, meta, loc, qty = "<img>", title_fallback, "", "-", ""
    rank_html = f"<span style='font-weight:800;color:#2563eb;margin-right:6px;'>{rank}위</span>" if rank else ""
    count_html = f"<span class='lib-hint'> · 누적 대출 {count}회</span>" if count else ""
    st.markdown(f"""<div class="book-card">{cover}
        <div>{rank_html}<b>{title}</b>{count_html}<br>
        <span class="lib-hint">{meta}</span><br>
        <span class="lib-hint">{qty} · 위치 {loc}</span><br>
        {_status_badge(_book_avail_label(book))}</div></div>""", unsafe_allow_html=True)

# ==========================================================
# 화면
# ==========================================================
def run_library():
    """바깥 껍데기: 구글 시트 오류가 나도 앱이 죽지 않고 안내 메시지를 보여준다."""
    try:
        _run_library()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"구글 시트 '{LIB_DB}' 를 열 수 없습니다. 시트 이름과 서비스 계정 공유(편집자) 설정을 확인해 주세요.")
    except (LibBusy, gspread.exceptions.APIError) as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (429, None):
            st.warning("⏳ 구글 시트 요청이 잠시 몰렸습니다. 5~10초 뒤 아래 버튼을 눌러 다시 시도해 주세요.")
        elif code == 403:
            st.error("구글 시트 접근 권한이 없습니다. 시트를 서비스 계정 이메일에 **편집자**로 공유했는지 확인해 주세요.")
        else:
            st.error(f"구글 시트 오류가 발생했습니다. (코드 {code}) 잠시 후 다시 시도해 주세요.")
        if st.button("🔄 다시 시도", key="lib_retry"):
            _reset_conn(); st.rerun()

def _run_library():
    st.markdown("""
        <style>
        .book-card { border:1px solid #e5e7eb; border-radius:12px; padding:14px; margin-bottom:10px;
                     background:#fff; display:flex; gap:12px; }
        .book-card img { width:52px; height:72px; object-fit:cover; border-radius:6px; background:#eef1f4; }
        .lib-hint { color:#6b7280; font-size:.85em; }
        </style>
    """, unsafe_allow_html=True)

    st.header("📚 사내 도서관")
    st.caption("책에 인쇄된 ISBN 바코드로 셀프 대출·반납하세요. 개인정보는 사번·이름만 사용합니다.")
    if not _SCAN_OK:
        st.info("ℹ️ 휴대폰 카메라 스캔을 쓰려면 requirements.txt에 zxing-cpp, pillow가 필요합니다. (직접 입력·USB 스캐너는 지금도 가능)")
    st.markdown("---")

    tab_home, tab_lend, tab_search, tab_my, tab_admin = st.tabs(
        ["🏠 홈", "📕 대출·반납", "🔍 도서 검색", "🙋 내 대출·희망도서", "👑 관리자"])

    # ---------------- 홈 ----------------
    with tab_home:
        home_books = [b for b in _records("books") if b.get("status") != "폐기"]
        home_loans = _records("loans")

        st.subheader("🆕 최근 입고된 책")
        recent = list(reversed(home_books))[:5]
        if not recent:
            st.info("아직 등록된 도서가 없습니다. 관리자 탭에서 도서를 등록해 주세요.")
        else:
            for b in recent:
                _home_card(b)

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
                _home_card(book, rank=rank, count=c, title_fallback=title)

    # ---------------- 대출 / 반납 ----------------
    with tab_lend:
        mode = st.radio("무엇을 하시겠어요?", ["📕 대출하기", "📗 반납하기"], horizontal=True, key="lib_mode")
        use_cam = st.checkbox("📷 휴대폰 카메라로 스캔", key="lib_usecam",
                              help="체크하면 카메라가 켜집니다. USB 스캐너·직접 입력은 체크 없이 사용하세요.")

        # ===== 대출 =====
        if mode == "📕 대출하기":
            c1, c2 = st.columns(2)
            saban = c1.text_input("사번", key="co_saban", placeholder="사번 입력")
            name = c2.text_input("이름 (처음 이용 시 1회)", key="co_name", placeholder="이름")

            if use_cam:
                img = st.camera_input("책의 ISBN 바코드를 비추고 촬영하세요", key="co_cam")
                code = _decode(img)
                if code and st.session_state.get("co_last") != code:
                    ok, res = _checkout(code, saban, name)
                    st.session_state["co_last"] = code
                    if ok:
                        st.success(f"✅ **{res['title']}** 대출 완료 · 반납예정일 **{res['due']}**"); st.balloons()
                    else:
                        st.error(f"⚠️ {res}")
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 조금 더 가까이서 다시 촬영해 주세요.")
            else:
                with st.form("co_form", clear_on_submit=True):
                    manual = st.text_input("책 ISBN 바코드 (USB 스캐너로 스캔 또는 숫자 직접 입력)")
                    if st.form_submit_button("대출하기", use_container_width=True):
                        ok, res = _checkout(manual, saban, name)
                        if ok:
                            st.success(f"✅ **{res['title']}** 대출 완료 · 반납예정일 **{res['due']}**"); st.balloons()
                        else:
                            st.error(f"⚠️ {res}")
            st.markdown("<p class='lib-hint'>USB 스캐너는 입력칸에 커서를 두고 스캔하면 자동 입력됩니다.</p>", unsafe_allow_html=True)

        # ===== 반납 =====
        else:
            ci_saban = st.text_input("반납자 사번 (같은 책 여러 권이 대출 중일 때만 필요)", key="ci_saban", placeholder="보통은 비워두어도 됩니다")
            if use_cam:
                img = st.camera_input("반납할 책의 ISBN 바코드를 촬영하세요", key="ci_cam")
                code = _decode(img)
                if code and st.session_state.get("ci_last") != code:
                    ok, res = _checkin(code, ci_saban)
                    if ok:
                        st.session_state["ci_last"] = code
                        extra = " (연체 반납)" if res["overdue"] else ""
                        wait = f" · 🔔 예약자 {res['waiting']}님 대기" if res["waiting"] else ""
                        st.success(f"✅ **{res['title']}** 반납 완료{extra}{wait}")
                    elif isinstance(res, dict) and res.get("need_saban"):
                        st.info(res["msg"])   # 사번 입력 후 재시도 허용 (ci_last 고정 안 함)
                    else:
                        st.session_state["ci_last"] = code
                        st.error(f"⚠️ {res}")
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 다시 촬영해 주세요.")
            else:
                with st.form("ci_form", clear_on_submit=True):
                    manual = st.text_input("반납할 책 ISBN 바코드")
                    if st.form_submit_button("반납하기", use_container_width=True):
                        ok, res = _checkin(manual, ci_saban)
                        if ok:
                            extra = " (연체 반납)" if res["overdue"] else ""
                            wait = f" · 🔔 예약자 {res['waiting']}님 대기" if res["waiting"] else ""
                            st.success(f"✅ **{res['title']}** 반납 완료{extra}{wait}")
                        elif isinstance(res, dict) and res.get("need_saban"):
                            st.info(res["msg"])
                        else:
                            st.error(f"⚠️ {res}")
            st.markdown("<p class='lib-hint'>반납은 보통 책 바코드만 스캔하면 됩니다. 같은 책 여러 권이 동시에 대출 중일 때만 사번을 넣어 주세요.</p>", unsafe_allow_html=True)

    # ---------------- 도서 검색 ----------------
    with tab_search:
        q = st.text_input("제목 · 저자 · ISBN 검색", key="lib_q", placeholder="검색어를 입력하세요")
        books = [b for b in _records("books") if b.get("status") != "폐기"]
        ql = q.strip().lower()
        if ql:
            books = [b for b in books if any(
                ql in str(b.get(k, "")).lower() for k in ["title", "author", "isbn", "category", "publisher"])]
        books = sorted(books, key=lambda b: str(b.get("title", "")))
        st.caption(f"총 {len(books)}종")
        for b in books[:100]:
            cover = f"<img src='{b.get('cover')}'>" if b.get("cover") else "<img>"
            meta = " · ".join([str(b.get(k)) for k in ["author", "publisher", "year"] if b.get(k)])
            st.markdown(f"""<div class="book-card">{cover}
                <div><b>{b.get('title')}</b><br>
                <span class="lib-hint">{meta}</span><br>
                <span class="lib-hint">{_qty_text(b)} · 위치 {b.get('location') or '-'}</span><br>
                {_status_badge(_book_avail_label(b))}</div></div>""", unsafe_allow_html=True)
            if _to_int(b.get("available_qty")) <= 0 and b.get("status") != "폐기":
                with st.expander(f"🔖 '{b.get('title')}' 예약하기"):
                    with st.form(f"res_{_norm_isbn(b.get('isbn'))}", clear_on_submit=True):
                        rc1, rc2 = st.columns(2)
                        rs = rc1.text_input("사번", key=f"rs_{_norm_isbn(b.get('isbn'))}")
                        rn = rc2.text_input("이름", key=f"rn_{_norm_isbn(b.get('isbn'))}")
                        if st.form_submit_button("예약 신청"):
                            ok, msg = _reserve(b.get("isbn"), rs, rn)
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
                cnt = _to_int(l.get("renew_count"))
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
            lo_c, rs_c = st.columns([1, 1])
            if lo_c.button("로그아웃", key="lib_admin_logout"):
                st.session_state.lib_admin = False; st.rerun()
            if rs_c.button("🔄 시트 연결 새로고침", key="lib_reset_conn",
                           help="구글 시트에서 탭을 지우거나 열을 바꿨을 때 누르세요."):
                _reset_conn(); st.success("연결을 새로 읽었습니다."); st.rerun()

            books = _records("books")
            loans = _records("loans")
            active = [l for l in loans if l.get("status") == "대출중"]
            overdue = [l for l in active if _is_overdue(l)]
            wishes = [w for w in _records("wishlist") if w.get("status") == "접수"]
            live_books = [b for b in books if b.get("status") != "폐기"]
            total_copies = sum(_to_int(b.get("total_qty")) for b in live_books)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 장서(권)", total_copies)
            m2.metric("대출 중", len(active))
            m3.metric("연체", len(overdue))
            m4.metric("희망도서", len(wishes))
            st.caption(f"도서 종수: {len(live_books)}종 · 회원 {len(_records('members'))}명")

            with st.expander("➕ 도서 등록  (같은 ISBN을 다시 등록하면 수량이 늘어납니다)", expanded=True):
                ic1, ic2 = st.columns([3, 1])
                isbn_in = ic1.text_input("ISBN (스캔 또는 입력) *", key="reg_isbn")
                if ic2.button("ISBN 조회", key="reg_lookup", use_container_width=True):
                    info, err = _lookup_isbn(isbn_in)
                    if info:
                        for k in ["title", "author", "publisher", "year", "category", "cover"]:
                            st.session_state[f"reg_{k}"] = info[k]
                        st.success("정보를 불러왔습니다. 아래에서 확인 후 등록하세요.")
                    else:
                        st.warning(err or "도서 정보를 찾지 못했습니다. 직접 입력해 주세요.")
                with st.form("book_form", clear_on_submit=True):
                    title = st.text_input("제목 *", value=st.session_state.get("reg_title", ""))
                    bc1, bc2 = st.columns(2)
                    author = bc1.text_input("저자", value=st.session_state.get("reg_author", ""))
                    publisher = bc2.text_input("출판사", value=st.session_state.get("reg_publisher", ""))
                    bc3, bc4 = st.columns(2)
                    year = bc3.text_input("출판연도", value=st.session_state.get("reg_year", ""))
                    category = bc4.text_input("분류", value=st.session_state.get("reg_category", ""))
                    bc5, bc6 = st.columns(2)
                    location = bc5.text_input("위치 (예: A-3)")
                    qty = bc6.number_input("수량(권수)", min_value=1, value=1, step=1)
                    if st.form_submit_button("등록", use_container_width=True):
                        ok, msg = _add_book({
                            "isbn": isbn_in, "title": title, "author": author, "publisher": publisher,
                            "year": year, "category": category, "location": location,
                            "qty": qty, "cover": st.session_state.get("reg_cover", "")})
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
                    st.dataframe(pd.DataFrame([{"도서": l.get("title"), "대출자": f"{l.get('name')}({l.get('saban')})",
                                               "대출일": l.get("loan_date"), "반납예정": l.get("due_date"),
                                               "연체": "🔴" if _is_overdue(l) else ""} for l in active]),
                                 use_container_width=True, hide_index=True)
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
