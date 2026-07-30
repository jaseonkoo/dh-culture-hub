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
LIB_VER    = "v10 (2026-07-30 · 책 소개는 구글 시트에서만)"   # 화면 맨 위에 표시됩니다. 배포 확인용.
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
                     "total_qty", "available_qty", "status", "cover", "summary"],
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

class LibSchema(Exception):
    """시트의 열(헤더)이 지금 프로그램 형식과 다를 때."""
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
    """열 번호(1부터). 없는 열에 잘못 쓰는 사고를 막기 위해, 없으면 오류를 낸다."""
    hdr = _header(name)
    if field in hdr:
        return hdr.index(field) + 1
    raise LibSchema(f"'{name}' 탭에 '{field}' 열이 없습니다. 👑 관리자 메뉴의 '시트 형식 변환'을 먼저 실행해 주세요.")

def _ensure_col(name, field):
    """시트에 그 열이 없으면 '맨 끝에' 새 열을 하나 만들어 준다.
       기존 값은 건드리지 않으므로 안전합니다."""
    hdr = _header(name)
    if field in hdr:
        return True
    try:
        ws = _ws(name)
        _retry(ws.update_cell, 1, len(hdr) + 1, field)
        _ws_cache()["__hdr__" + name] = hdr + [field]
        _records.clear()
        return True
    except Exception:
        return False

def _needs_migration():
    """books/loans 탭이 아직 예전(자산번호) 형식인지 확인."""
    try:
        bh = _header("books"); lh = _header("loans")
    except Exception:
        return False
    return ("available_qty" not in bh) or ("total_qty" not in bh) or ("isbn" not in lh)

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
    """시트 칸에 '1', 1, 1.0, ' 1 ', '1권' 같이 뭐가 들어 있어도 숫자로 읽는다."""
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return default
    try:
        return int(s)
    except Exception:
        pass
    num = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
    try:
        return int(float(num))
    except Exception:
        return default

# ==========================================================
# 회원 (사번 + 이름)
# ==========================================================
def _member_name(saban):
    """이미 한 번이라도 이용한 사번이면 저장된 이름을 돌려준다. 처음이면 빈 문자열."""
    saban = str(saban).strip()
    if not saban:
        return ""
    for m in _records("members"):
        if str(m.get("saban")).strip() == saban:
            return str(m.get("name", "")).strip()
    return ""

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

# ==========================================================
# 예전 형식(자산번호 1행=1권) → 새 형식(ISBN + 수량) 변환
# ==========================================================
def _build_migration():
    """변환 결과를 계산만 한다. (시트는 건드리지 않음)"""
    old_books = _retry(_ws("books").get_all_records)
    old_loans = _retry(_ws("loans").get_all_records)

    # 자산번호 → ISBN 매핑 (ISBN이 비어 있으면 자산번호를 그대로 열쇠로 씀)
    a2i, no_isbn = {}, []
    for r in old_books:
        a = str(r.get("asset_id", "")).strip()
        i = _norm_isbn(r.get("isbn"))
        if a:
            a2i[a] = i or a
            if not i:
                no_isbn.append(f"{r.get('title','')} ({a})")

    # 대출 기록: asset_id 열을 isbn 열로 바꿔 옮긴다
    new_loans, out_cnt = [], {}
    for r in old_loans:
        a = str(r.get("asset_id", "") or r.get("isbn", "")).strip()
        key = a2i.get(a) or _norm_isbn(a) or a
        status = str(r.get("status", "")).strip()
        new_loans.append([r.get("loan_id", ""), key, r.get("title", ""), r.get("saban", ""),
                          r.get("name", ""), r.get("loan_date", ""), r.get("due_date", ""),
                          r.get("return_date", ""), _to_int(r.get("renew_count")), status])
        if status == "대출중":
            out_cnt[key] = out_cnt.get(key, 0) + 1

    # 도서: 같은 ISBN끼리 묶어 수량으로 만든다
    agg, order = {}, []
    for r in old_books:
        a = str(r.get("asset_id", "")).strip()
        key = a2i.get(a) or _norm_isbn(r.get("isbn")) or a
        if not key:
            continue
        if key not in agg:
            agg[key] = {"isbn": key, "total": 0, "dead": 0,
                        **{f: r.get(f, "") for f in
                           ["title", "author", "publisher", "year", "category", "location", "cover"]}}
            order.append(key)
        g = agg[key]
        for f in ["title", "author", "publisher", "year", "category", "location", "cover"]:
            if not str(g[f]).strip() and str(r.get(f, "")).strip():
                g[f] = r.get(f, "")
        if str(r.get("status", "")).strip() == "폐기":
            g["dead"] += 1
        else:
            g["total"] += 1

    new_books = []
    for key in order:
        g = agg[key]
        tot = g["total"]
        avail = max(0, tot - out_cnt.get(key, 0))
        new_books.append([g["isbn"], g["title"], g["author"], g["publisher"], g["year"],
                          g["category"], g["location"], tot, avail,
                          "폐기" if tot == 0 else "정상", g["cover"]])
    return {"books": new_books, "loans": new_loans,
            "old_book_rows": len(old_books), "no_isbn": no_isbn}

def _apply_migration(plan):
    """예전 탭은 이름만 바꿔 백업으로 남기고, 새 형식 탭을 만들어 옮겨 담는다."""
    stamp = datetime.datetime.now().strftime("%m%d_%H%M")
    for name in ["books", "loans", "reservations"]:
        try:
            _retry(_ws(name).update_title, f"{name}_backup_{stamp}")
        except Exception:
            pass
    _reset_conn()                      # 캐시를 비워 새 탭이 자동 생성되게 함
    if plan["books"]:
        _retry(_ws("books").append_rows, plan["books"])
    if plan["loans"]:
        _retry(_ws("loans").append_rows, plan["loans"])
    _ws("reservations")                # 빈 탭으로 새로 생성
    _reset_conn()
    return stamp

def _audit_stock():
    """books 탭의 '대출가능 수량'이 실제 대출 현황과 맞는지 검사한다. (고치지는 않음)"""
    _refresh()
    out_cnt = {}
    for l in _records("loans"):
        if l.get("status") == "대출중":
            k = _norm_isbn(l.get("isbn"))
            out_cnt[k] = out_cnt.get(k, 0) + 1
    bad = []
    for i, b in enumerate(_records("books")):
        if b.get("status") == "폐기":
            continue
        k = _norm_isbn(b.get("isbn"))
        tot = _to_int(b.get("total_qty"))
        cur = _to_int(b.get("available_qty"))
        out = out_cnt.get(k, 0)
        should = max(0, tot - out)
        if should != cur:
            bad.append({"row": i + 2, "제목": b.get("title", ""), "ISBN": b.get("isbn", ""),
                        "총권수": tot, "대출중": out,
                        "시트값(대출가능)": cur, "올바른값": should})
    return bad

def _fix_stock(bad):
    """검사에서 나온 어긋난 값을 올바른 값으로 되돌린다."""
    if not bad:
        return 0
    ws = _ws("books"); ca = _col("books", "available_qty")
    for r in bad:
        _retry(ws.update_cell, r["row"], ca, r["올바른값"])
    _refresh()
    return len(bad)

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
            if not str(info.get("cover", "")).strip():
                g = _lookup_google(isbn) or {}
                info["cover"] = g.get("cover", "")
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
    summary = str(b.get("summary", "") or "").strip()
    if summary:
        _ensure_col("books", "summary")
    vals = {"isbn": isbn, "title": b.get("title", ""), "author": b.get("author", ""),
            "publisher": b.get("publisher", ""), "year": b.get("year", ""),
            "category": b.get("category", ""), "location": b.get("location", ""),
            "total_qty": qty, "available_qty": qty, "status": "정상",
            "cover": b.get("cover", ""), "summary": summary[:1500]}
    hdr = _header("books")
    _retry(_ws("books").append_row, [vals.get(h, "") for h in hdr])
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

MENU = ["🏠 홈", "📕 대출·반납", "🔍 도서 검색", "🙋 내 대출·희망도서", "👑 관리자"]

def _goto_detail(isbn):
    """책 카드의 [자세히] → 책 상세 화면으로."""
    isbn = _norm_isbn(isbn)
    if not isbn:
        return
    st.session_state["lib_detail"] = isbn
    st.session_state["lib_detail_back"] = st.session_state.get("lib_menu", MENU[0])
    st.rerun()

def _goto_lend(book):
    """[바로 대출하기] → 대출·반납 메뉴로 이동하면서 ISBN을 미리 채워 둔다."""
    st.session_state.pop("lib_detail", None)
    st.session_state["lib_menu"] = MENU[1]
    st.session_state["lib_mode_want"] = "📕 대출하기"
    st.session_state["lib_prefill_isbn"] = _norm_isbn(book.get("isbn", ""))
    st.session_state["lib_prefill_title"] = str(book.get("title", ""))
    st.rerun()

def _esc(x):
    """HTML에 그대로 넣어도 안전하도록 특수문자를 바꿔 준다."""
    return (str(x if x is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

_ST_CLASS = {"대출가능": "ok", "대출중": "no", "예약중": "wait", "폐기": "off"}

def _clean_author(raw):
    """'지은이: 고현숙,김병헌,...' 처럼 지저분한 저자 값을 보기 좋게 정리한다.
       - 앞에 붙은 '지은이:' '저자:' 같은 말머리를 떼고
       - 사람이 여럿이면 '고현숙 외 8명' 으로 줄인다."""
    s = str(raw or "").strip()
    if not s:
        return ""
    # 말머리 제거 (지은이: / 저자 : / 글·그림 : ...)
    for head in ("지은이", "저자", "엮은이", "글쓴이", "글", "author", "Author"):
        for sep in (":", "："):
            if s.startswith(head + sep) or s.startswith(head + " " + sep):
                s = s.split(sep, 1)[1]
                break
    s = s.strip(" ·,;")
    # 옮긴이/그림 등 뒤에 붙은 부분은 잘라 낸다
    for cut in ("옮긴이", "번역", "그림", "감수"):
        idx = s.find(cut)
        if idx > 0:
            s = s[:idx]
    s = s.strip(" ·,;|/")
    names = [n.strip() for n in s.replace(";", ",").replace("|", ",").replace("/", ",").split(",")]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0][:24]
    return f"{names[0][:20]} 외 {len(names) - 1}명"

def _cover_html(book, title):
    """표지 그림. 표지가 없으면 책등(스파인) 모양을 그려서 대신 보여준다."""
    url = str((book or {}).get("cover", "") or "").strip()
    if url:
        return f"<div class='lib-cv'><img src='{_esc(url)}' loading='lazy' alt=''></div>"
    short = _esc(title)[:28]
    return (f"<div class='lib-cv lib-cv-none'><div class='lib-cv-txt'>{short}</div>"
            f"<div class='lib-cv-emb'>大韓飼料<br>圖書</div></div>")

def _shelf_item(it, key):
    """책장 한 칸: 표지 + 제목 + 상태 + (대출가능일 때) 대출 버튼."""
    b = it.get("book") or None
    title = str((b or {}).get("title", "") or it.get("fallback", "") or "제목 없음")
    author_raw = str((b or {}).get("author", "") or "")
    author = _clean_author(author_raw)
    loc = str((b or {}).get("location", "") or "")
    label = _book_avail_label(b)
    cls = _ST_CLASS.get(label, "off")
    rank = it.get("rank")
    cnt = it.get("count")

    rank_html = f"<div class='lib-rank'>{rank}</div>" if rank else ""
    qty = _qty_text(b) if b else ""
    meta2 = " · ".join([x for x in [loc and f"위치 {loc}", qty] if x])
    cnt_html = f"<div class='lib-cnt'>누적 대출 {cnt}회</div>" if cnt else ""

    st.markdown(
        f"<div class='lib-bk'>{rank_html}{_cover_html(b, title)}"
        f"<div class='lib-tt' title='{_esc(title)}'>{_esc(title)}</div>"
        f"<div class='lib-au' title='{_esc(author_raw)}'>{_esc(author) or '&nbsp;'}</div>"
        f"<div class='lib-mt'>{_esc(meta2) or '&nbsp;'}</div>"
        f"{cnt_html}"
        f"<div class='lib-st {cls}'>● {label}</div></div>",
        unsafe_allow_html=True)

    isbn = _norm_isbn((b or {}).get("isbn", ""))
    if label == "대출가능":
        bc1, bc2 = st.columns(2)
        if bc1.button("자세히", key=f"dt_{key}", use_container_width=True):
            _goto_detail(isbn)
        if bc2.button("빌리기", key=f"go_{key}", use_container_width=True, type="primary"):
            _goto_lend(b)
    else:
        if st.button("자세히", key=f"dt_{key}", use_container_width=True, disabled=not isbn):
            _goto_detail(isbn)
        st.markdown("<div class='lib-btn-off'>대출 불가</div>", unsafe_allow_html=True)

def _shelf(items, keyprefix, per_row=4):
    """책장처럼 한 줄에 여러 권 + 아래에 나무 선반."""
    if not items:
        return
    for start in range(0, len(items), per_row):
        chunk = items[start:start + per_row]
        cols = st.columns(per_row)
        for j in range(per_row):
            with cols[j]:
                if j < len(chunk):
                    _shelf_item(chunk[j], f"{keyprefix}_{start + j}")
        st.markdown("<div class='lib-plank'></div>", unsafe_allow_html=True)

def _next_due_text(isbn):
    """대출 중인 이 책이 언제 돌아오는지(가장 빠른 반납예정일)."""
    isbn = _norm_isbn(isbn)
    dues = []
    for l in _records("loans"):
        if _norm_isbn(l.get("isbn")) != isbn:
            continue
        if str(l.get("status", "")).strip() in ("반납", "반납완료"):
            continue
        if str(l.get("return_date", "")).strip():
            continue
        d = str(l.get("due_date", "")).strip()
        if d:
            dues.append(d)
    return sorted(dues)[0] if dues else ""

def _book_summary_text(book):
    """책 소개 글. 시트에 없으면 빈 문자열."""
    return str((book or {}).get("summary", "") or "").strip()

def _detail_page(isbn):
    """책 한 권의 자세한 정보 화면."""
    b = _find_book(isbn)
    if st.button("◀ 목록으로 돌아가기", key="dt_back"):
        st.session_state.pop("lib_detail", None)
        st.rerun()
    if not b:
        st.warning("책을 찾지 못했습니다. 목록으로 돌아가 주세요.")
        return

    title = str(b.get("title", "") or "제목 없음")
    label = _book_avail_label(b)
    cls = _ST_CLASS.get(label, "off")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f"<div class='lib-bk lib-bk-big'>{_cover_html(b, title)}</div>",
                    unsafe_allow_html=True)
    with c2:
        rows = [("저자", _clean_author(b.get("author")) or "-"),
                ("출판사", str(b.get("publisher", "") or "-")),
                ("출판연도", str(b.get("year", "") or "-")),
                ("분류", str(b.get("category", "") or "-")),
                ("책 위치", str(b.get("location", "") or "-")),
                ("ISBN", str(b.get("isbn", "") or "-"))]
        info = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)
        st.markdown(
            f"<div class='lib-dt'><h2>{_esc(title)}</h2>"
            f"<div class='lib-st {cls}' style='font-size:.95rem'>● {label} "
            f"<span class='lib-hint'>({_esc(_qty_text(b))})</span></div>"
            f"<table class='lib-tb'>{info}</table></div>", unsafe_allow_html=True)

        if label == "대출가능":
            if st.button("📕 이 책 빌리기", key="dt_lend", type="primary", use_container_width=True):
                _goto_lend(b)
        elif label in ("대출중", "예약중"):
            nxt = _next_due_text(b.get("isbn"))
            if nxt:
                st.markdown(f"<p class='lib-hint'>반납 예정일 : {_esc(nxt)}</p>", unsafe_allow_html=True)
            with st.expander("🔖 이 책 예약하기"):
                with st.form(f"dt_res_{_norm_isbn(isbn)}", clear_on_submit=True):
                    rc1, rc2 = st.columns(2)
                    rs = rc1.text_input("사번")
                    rn = rc2.text_input("이름 (처음 이용 시 1회)")
                    if st.form_submit_button("예약 신청", use_container_width=True, type="primary"):
                        ok, msg = _reserve(b.get("isbn"), rs, rn)
                        (st.success if ok else st.error)(msg)

    _sec_title("책 소개", "어떤 책인가요")
    summ = _book_summary_text(b)
    if summ:
        st.markdown(f"<div class='lib-sm'>{_esc(summ)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='lib-sm lib-sm-none'>아직 등록된 책 소개가 없습니다.</div>",
                    unsafe_allow_html=True)

    cnt = sum(1 for l in _records("loans")
              if _norm_isbn(l.get("isbn")) == _norm_isbn(isbn))
    if cnt:
        st.markdown(f"<p class='lib-hint'>지금까지 {cnt}번 대출되었습니다.</p>", unsafe_allow_html=True)

def _sec_title(text, sub=""):
    sub_html = f"<span class='lib-sec-sub'>{_esc(sub)}</span>" if sub else ""
    st.markdown(f"<div class='lib-sec'><h2>{_esc(text)}</h2>{sub_html}</div>", unsafe_allow_html=True)

# ==========================================================
# 화면
# ==========================================================
def run_library():
    """바깥 껍데기: 구글 시트 오류가 나도 앱이 죽지 않고 안내 메시지를 보여준다."""
    try:
        _run_library()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"구글 시트 '{LIB_DB}' 를 열 수 없습니다. 시트 이름과 서비스 계정 공유(편집자) 설정을 확인해 주세요.")
    except LibSchema as e:
        st.error(str(e))
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

LIB_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap');

/* ---------- 바탕: 크림색 종이 ---------- */
.stApp, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 500px at 50% -8%, #FFFDF7 0%, rgba(255,253,247,0) 70%),
    repeating-linear-gradient(0deg, rgba(169,120,46,.028) 0 2px, rgba(0,0,0,0) 2px 5px),
    #FAF6EE;
}
[data-testid="stHeader"] { background: transparent; }

/* ---------- 글꼴 ----------
   본문은 읽기 편한 고딕체(Noto Sans KR), 큰 제목만 명조체로 멋을 냅니다. */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  font-family:'Noto Sans KR','Malgun Gothic','맑은 고딕',sans-serif;
}
/* 버튼·입력칸은 브라우저 기본 글꼴을 쓰므로 따로 물려받게 한다 */
.stApp button, .stApp input, .stApp textarea, .stApp select { font-family:inherit; }
/* ⚠️ 스트림릿의 화살표·아이콘은 '아이콘 전용 글꼴'을 씁니다.
   여기에 한글 글꼴을 씌우면 화살표 대신 arrow_right 같은 글자가 그대로 보입니다. */
[data-testid="stIconMaterial"], .material-icons, .material-icons-outlined,
[class*="material-symbols"], [class*="material-icons"], .stApp [data-testid*="Icon"] i {
  font-family:'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important;
  letter-spacing:normal !important;
}
.lib-wrap, .lib-wrap * { color:#2B2620; }
.stApp { font-size:15px; }
.lib-serif, .lib-head h1, .lib-head .em, .lib-sec h2, .lib-cv-txt, .lib-cv-emb, .lib-rank {
  font-family:'Nanum Myeongjo', Batang, serif !important; letter-spacing:-.01em;
}

/* ---------- 간판 ---------- */
.lib-head { text-align:center; padding:26px 10px 14px; }
.lib-head .em { font-family:'Nanum Myeongjo',serif; font-size:.72rem; letter-spacing:.34em;
  color:#A9782E; text-transform:uppercase; margin-bottom:8px; }
.lib-head h1 { font-size:2.35rem; font-weight:800; margin:0; color:#1F4A3C;
  font-family:'Nanum Myeongjo',serif; }
.lib-head .rule { width:220px; height:0; margin:14px auto 12px; border-top:2px solid #1F4A3C;
  border-bottom:1px solid #1F4A3C; padding-top:3px; }
.lib-head .sub { font-size:.88rem; color:#645B4E; line-height:1.6; }
.lib-head .ver { font-size:.7rem; color:#A79A85; margin-top:6px; }

/* ---------- 구역 제목 ---------- */
.lib-sec { display:flex; align-items:baseline; gap:12px; margin:26px 0 14px;
  border-bottom:1px solid #E0D6C3; padding-bottom:8px; }
.lib-sec h2 { font-size:1.28rem !important; font-weight:800; margin:0 !important; color:#1F4A3C;
  padding:0 !important; }
.lib-sec .lib-sec-sub { font-size:.82rem; color:#8C806E; }

/* ---------- 책 한 칸 ---------- */
.lib-bk { position:relative; padding:2px 2px 6px; text-align:center; }
.lib-cv { position:relative; width:100%; max-width:170px; margin:0 auto;
  aspect-ratio:3/4; border-radius:2px 7px 7px 2px; overflow:hidden;
  background:#F1E9D9; border:1px solid #DCCFB6;
  box-shadow:0 12px 16px -12px rgba(43,38,32,.65), 0 2px 3px rgba(43,38,32,.14);
  transition:transform .16s ease, box-shadow .16s ease; }
.lib-bk:hover .lib-cv { transform:translateY(-4px);
  box-shadow:0 18px 22px -12px rgba(43,38,32,.6), 0 3px 5px rgba(43,38,32,.18); }
.lib-cv img { width:100%; height:100%; object-fit:contain; display:block;
  background:#F1E9D9; }
@supports not (aspect-ratio: 3 / 4) { .lib-cv { height:226px; } }
.lib-cv::before { content:""; position:absolute; left:0; top:0; bottom:0; width:10px; z-index:2;
  background:linear-gradient(90deg, rgba(0,0,0,.30), rgba(0,0,0,.05) 62%, rgba(255,255,255,.20)); }
.lib-cv-none { display:flex; flex-direction:column; justify-content:space-between; padding:16px 12px 12px 18px;
  background:linear-gradient(135deg,#2E5B4A 0%, #1F4A3C 60%, #17392E 100%); }
.lib-cv-txt { font-family:'Nanum Myeongjo',serif; font-weight:700; font-size:.92rem; line-height:1.45;
  color:#F3EAD6; }
.lib-cv-emb { font-family:'Nanum Myeongjo',serif; font-size:.62rem; line-height:1.35; text-align:right;
  color:#C9A96A; letter-spacing:.12em; }

.lib-tt { font-weight:700; font-size:.95rem; line-height:1.45;
  margin:12px 0 4px; color:#241F19; min-height:2.9em; letter-spacing:-.01em;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.lib-au { font-size:.82rem; color:#6B6154; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.lib-mt { font-size:.78rem; color:#8C806E; margin-top:3px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.lib-cnt { font-size:.78rem; color:#96691F; font-weight:700; margin-top:3px; }
.lib-st { font-size:.82rem; font-weight:700; margin:7px 0 9px; }
.lib-st.ok   { color:#1F6B4F; }
.lib-st.no   { color:#A33A2E; }
.lib-st.wait { color:#B07A16; }
.lib-st.off  { color:#948A79; }

.lib-rank { position:absolute; top:-8px; left:-6px; z-index:3; width:32px; height:32px; border-radius:50%;
  background:linear-gradient(145deg,#D7B25E,#A9782E); color:#FFF8E7; font-family:'Nanum Myeongjo',serif;
  font-weight:800; font-size:.95rem; display:flex; align-items:center; justify-content:center;
  box-shadow:0 3px 6px rgba(43,38,32,.35); border:1px solid #8C6320; }

.lib-btn-off { text-align:center; font-size:.82rem; color:#A79A85; border:1px dashed #DCCFB6;
  border-radius:6px; padding:7px 0; background:rgba(255,255,255,.4); }

/* ---------- 책 상세 화면 ---------- */
.lib-bk-big { text-align:center; }
.lib-bk-big .lib-cv { max-width:230px; }
@supports not (aspect-ratio: 3 / 4) { .lib-bk-big .lib-cv { height:306px; } }
.lib-dt h2 { font-size:1.5rem !important; font-weight:800; color:#1F4A3C;
  margin:0 0 8px !important; padding:0 !important; line-height:1.4; }
.lib-tb { width:100%; border-collapse:collapse; margin:14px 0 16px; font-size:.9rem; }
.lib-tb th { text-align:left; width:92px; padding:7px 0; color:#8C806E; font-weight:500;
  vertical-align:top; border-bottom:1px solid #EDE5D6; }
.lib-tb td { padding:7px 0; color:#3A3327; border-bottom:1px solid #EDE5D6;
  word-break:break-all; }
.lib-sm { background:#FFFDF7; border:1px solid #E0D6C3; border-left:5px solid #1F4A3C;
  border-radius:6px; padding:18px 20px; line-height:1.85; font-size:.94rem; color:#3A3327;
  white-space:pre-wrap; }
.lib-sm-none { border-left-color:#D6C9B0; color:#8C806E; }

/* ---------- 나무 선반 ---------- */
.lib-plank { height:15px; margin:4px 0 30px; border-radius:2px;
  background:linear-gradient(180deg,#D2A868 0%, #B98B41 40%, #8E6526 78%, #6E4C1B 100%);
  box-shadow:0 9px 14px -8px rgba(70,46,12,.55), inset 0 1px 0 rgba(255,255,255,.40),
             inset 0 -2px 3px rgba(0,0,0,.22); }

/* ---------- 버튼 ---------- */
.stButton > button {
  font-weight:700 !important; font-size:.92rem !important;
  border-radius:6px !important; border:1px solid #C9BCA3 !important;
  background:#FFFDF7 !important; color:#3A3327 !important;
  box-shadow:0 1px 2px rgba(43,38,32,.08) !important; transition:all .15s ease !important;
}
.stButton > button:hover { border-color:#1F4A3C !important; color:#1F4A3C !important;
  background:#F5EFE1 !important; }
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  background:linear-gradient(180deg,#2A5C49,#1F4A3C) !important; color:#FBF7EE !important;
  border:1px solid #163A2E !important;
  box-shadow:0 2px 4px rgba(22,58,46,.28) !important;
}
.stButton > button[kind="primary"]:hover { background:linear-gradient(180deg,#316B55,#245445) !important;
  color:#FFF !important; }

/* ---------- 입력칸 ---------- */
.stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input {
  background:#FFFDF7 !important; border:1px solid #D6C9B0 !important; border-radius:6px !important;
  color:#2B2620 !important;
}
.stTextInput input:focus, .stTextArea textarea:focus { border-color:#1F4A3C !important;
  box-shadow:0 0 0 2px rgba(31,74,60,.14) !important; }

[data-testid="stWidgetLabel"] p { font-weight:700 !important; color:#4A4234 !important; }

/* ---------- 알림상자 / 펼침 ---------- */
[data-testid="stExpander"] { border:1px solid #E0D6C3 !important; border-radius:8px !important;
  background:#FFFDF7 !important; }
[data-testid="stNotification"] { border-radius:8px !important; font-size:.92rem; }
hr { border-color:#E0D6C3 !important; }

/* ---------- 대출 안내 쪽지 ---------- */
.lib-note { border:1px solid #C9A96A; border-left:5px solid #A9782E; background:#FFF9EC;
  border-radius:6px; padding:14px 16px; line-height:1.7; }
.lib-note b { color:#1F4A3C; }
.lib-hint { color:#8C806E; font-size:.84em; }

/* ---------- 좁은 화면(휴대폰) ---------- */
@media (max-width: 640px) {
  .lib-head h1 { font-size:1.7rem; }
  .lib-cv { max-width:128px; }
  @supports not (aspect-ratio: 3 / 4) { .lib-cv { height:170px; } }
  .lib-tt { font-size:.88rem; }
}
</style>
"""

def _run_library():
    st.markdown(LIB_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='lib-head'>"
        "<div class='em'>Daehan Feed &middot; Library</div>"
        "<h1>대한사료 사내도서관</h1>"
        "<div class='rule'></div>"
        "<div class='sub'>책에 인쇄된 ISBN 바코드로 직접 빌리고 반납하세요 &middot; "
        "개인정보는 사번과 이름만 사용합니다</div>"
        f"<div class='ver'>{LIB_VER}</div>"
        "</div>", unsafe_allow_html=True)

    if not _SCAN_OK:
        st.info("ℹ️ 휴대폰 카메라 스캔을 쓰려면 requirements.txt에 zxing-cpp, pillow가 필요합니다. (직접 입력·USB 스캐너는 지금도 가능)")

    _old_sheet = _needs_migration()
    if _old_sheet:
        st.error("⚠️ 구글 시트가 아직 **예전 형식(자산번호 방식)** 입니다. "
                 "그래서 모든 책이 '대출중'으로 보이고, 대출·반납이 정상 동작하지 않습니다.\n\n"
                 "👑 **관리자 메뉴 → 🔧 시트 형식 변환** 을 한 번 실행해 주세요. "
                 "기존 도서·대출 기록은 그대로 옮겨지고, 예전 탭은 백업으로 남습니다.")

    st.markdown("---")

    # 탭(st.tabs) 대신 메뉴 '버튼'을 씁니다.
    #  - 탭은 프로그램이 대신 눌러 줄 수 없어서 [바로 대출하기] 이동이 안 됩니다.
    #  - 라디오는 화면이 새로 그려질 때 첫 칸으로 되돌아가는 문제가 있었습니다.
    #  - 버튼은 '누를 때만' 바뀌므로, 글자를 입력하다 딴 곳을 클릭해도 화면이 그대로 있습니다.
    menu = st.session_state.get("lib_menu", MENU[0])
    if menu not in MENU:
        menu = MENU[0]
    _mcols = st.columns(len(MENU))
    for _i, _m in enumerate(MENU):
        if _mcols[_i].button(_m, key=f"lib_nav_{_i}", use_container_width=True,
                             type=("primary" if _m == menu else "secondary")):
            if _m != menu or st.session_state.get("lib_detail"):
                st.session_state["lib_menu"] = _m
                st.session_state.pop("lib_detail", None)
                st.rerun()
    st.session_state["lib_menu"] = menu
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # 책 카드의 [자세히]를 누르면 목록 대신 상세 화면을 보여준다.
    if st.session_state.get("lib_detail"):
        _detail_page(st.session_state["lib_detail"])
        return

    # ---------------- 홈 ----------------
    if menu == MENU[0]:
        home_books = [b for b in _records("books") if b.get("status") != "폐기"]
        home_loans = _records("loans")

        _sec_title("새로 들어온 책", "신착 도서")
        recent = list(reversed(home_books))[:8]
        if not recent:
            st.info("아직 등록된 도서가 없습니다. 👑 관리자 메뉴에서 도서를 등록해 주세요.")
        else:
            _shelf([{"book": b} for b in recent], "recent")

        _sec_title("가장 많이 읽은 책", "누적 대출 TOP 5")
        counts = {}
        for l in home_loans:
            t = str(l.get("title", "")).strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:5]
        if not top:
            st.info("아직 대출 기록이 없습니다.")
        else:
            items = []
            for rank, (title, c) in enumerate(top, start=1):
                book = next((b for b in home_books if str(b.get("title")).strip() == title), None)
                items.append({"book": book, "rank": rank, "count": c, "fallback": title})
            _shelf(items, "top")

    # ---------------- 대출 / 반납 ----------------
    if menu == MENU[1]:
      if _old_sheet:
        st.warning("시트 형식 변환이 끝난 뒤에 이용할 수 있습니다. (👑 관리자 메뉴 → 🔧 시트 형식 변환)")
      else:
        MODES = ["📕 대출하기", "📗 반납하기"]
        _want = st.session_state.pop("lib_mode_want", None)
        if _want in MODES:
            st.session_state["lib_mode_cur"] = _want
        _mc = st.session_state.get("lib_mode_cur", MODES[0])
        if _mc not in MODES:
            _mc = MODES[0]
        mode = st.radio("무엇을 하시겠어요?", MODES, index=MODES.index(_mc), horizontal=True)
        st.session_state["lib_mode_cur"] = mode
        use_cam = st.checkbox("📷 휴대폰 카메라로 스캔", key="lib_usecam",
                              help="체크하면 카메라가 켜집니다. USB 스캐너·직접 입력은 체크 없이 사용하세요.")

        # ===== 대출 =====
        if mode == "📕 대출하기":
            # 홈·검색에서 [📕 바로 대출하기]로 넘어온 경우 ISBN이 미리 채워져 있다.
            prefill = str(st.session_state.get("lib_prefill_isbn", "") or "")
            ptitle = str(st.session_state.get("lib_prefill_title", "") or "")
            if prefill:
                pc1, pc2 = st.columns([5, 1])
                pc1.markdown(
                    f"<div class='lib-note'>📕 <b>{_esc(ptitle)}</b> 을(를) 빌립니다."
                    f"<br><span class='lib-hint'>ISBN {_esc(prefill)}</span>"
                    "<br>아래에 <b>사번</b>을 넣고 [대출하기]를 누르세요. 바코드는 찍지 않아도 됩니다.</div>",
                    unsafe_allow_html=True)
                if pc2.button("취소", key="co_clear", use_container_width=True):
                    st.session_state.pop("lib_prefill_isbn", None)
                    st.session_state.pop("lib_prefill_title", None)
                    st.rerun()

            c1, c2 = st.columns(2)
            saban = c1.text_input("사번", key="co_saban", placeholder="사번 입력")
            known = _member_name(saban)
            if known:
                # 이미 한 번이라도 이용한 사번 → 이름을 자동으로 채워 보여준다.
                c2.text_input("이름 (자동 입력됨)", value=known, disabled=True, key="co_name_auto")
                name = known
                c1.caption(f"👤 **{known}** 님, 반갑습니다.")
            else:
                name = c2.text_input("이름 (처음 이용 시 1회)", key="co_name", placeholder="이름")
                if str(saban).strip():
                    c1.caption("🆕 처음 보는 사번이에요. 오른쪽에 이름을 한 번만 적어 주세요. "
                               "다음부터는 사번만 넣으면 이름이 자동으로 나옵니다.")

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
                    manual = st.text_input("책 ISBN 바코드 (USB 스캐너로 스캔 또는 숫자 직접 입력)",
                                           value=prefill)
                    if st.form_submit_button("대출하기", use_container_width=True):
                        ok, res = _checkout(manual, saban, name)
                        if ok:
                            st.session_state.pop("lib_prefill_isbn", None)
                            st.session_state.pop("lib_prefill_title", None)
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
    if menu == MENU[2]:
        q = st.text_input("제목 · 저자 · ISBN 검색", key="lib_q", placeholder="검색어를 입력하세요")
        books = [b for b in _records("books") if b.get("status") != "폐기"]
        ql = q.strip().lower()
        if ql:
            books = [b for b in books if any(
                ql in str(b.get(k, "")).lower() for k in ["title", "author", "isbn", "category", "publisher"])]
        books = sorted(books, key=lambda b: str(b.get("title", "")))
        _sec_title("서가 둘러보기", f"총 {len(books)}종")
        shown = books[:60]
        if not shown:
            st.info("찾으시는 책이 없습니다. 🙋 메뉴에서 '희망도서'로 신청해 보세요.")
        else:
            _shelf([{"book": b} for b in shown], "search")
        if len(books) > len(shown):
            st.markdown(f"<p class='lib-hint'>{len(books) - len(shown)}종이 더 있습니다. "
                        f"검색어를 넣어 좁혀 주세요.</p>", unsafe_allow_html=True)

        out_books = [b for b in books if _to_int(b.get("available_qty")) <= 0]
        if out_books:
            with st.expander("🔖 대출 중인 책 예약하기"):
                _opts = {f"{b.get('title')} ({b.get('author') or '저자 미상'})": b for b in out_books}
                _pick = st.selectbox("예약할 책", list(_opts.keys()), key="res_pick")
                with st.form("res_form", clear_on_submit=True):
                    rc1, rc2 = st.columns(2)
                    rs = rc1.text_input("사번", key="res_saban")
                    rn = rc2.text_input("이름 (처음 이용 시 1회)", key="res_name")
                    if st.form_submit_button("예약 신청", use_container_width=True, type="primary"):
                        _b = _opts.get(_pick)
                        ok, msg = _reserve((_b or {}).get("isbn"), rs, rn)
                        (st.success if ok else st.error)(msg)

    # ---------------- 내 대출 / 희망도서 ----------------
    if menu == MENU[3]:
        _sec_title("내 대출 현황", "사번으로 조회")
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

        _sec_title("희망도서 신청", "읽고 싶은 책을 알려주세요")
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
    if menu == MENU[4]:
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

            with st.expander("🔧 시트 형식 변환  (예전 자산번호 방식 → ISBN·수량 방식)",
                             expanded=_old_sheet):
                if not _old_sheet:
                    st.success("시트는 이미 새 형식입니다. 변환할 것이 없습니다.")
                else:
                    st.write("**무엇을 하나요?** 예전에는 책 한 권마다 한 줄(자산번호)이었는데, "
                             "지금 방식은 같은 책을 한 줄로 묶고 '총 권수 / 대출가능 권수'로 관리합니다. "
                             "아래 버튼이 그 변환을 대신 해 줍니다.")
                    st.write("**안전한가요?** 예전 `books`·`loans`·`reservations` 탭은 지우지 않고 "
                             "`books_backup_날짜시간` 처럼 **이름만 바꿔 그대로 남깁니다.** "
                             "문제가 생기면 언제든 되돌아볼 수 있어요.")
                    if st.button("① 변환 결과 미리보기", key="lib_mig_plan"):
                        st.session_state["lib_mig"] = _build_migration()
                    plan = st.session_state.get("lib_mig")
                    if plan:
                        st.info(f"예전 도서 {plan['old_book_rows']}줄 → **{len(plan['books'])}종**으로 묶입니다. "
                                f"대출 기록 {len(plan['loans'])}건이 함께 옮겨집니다.")
                        st.dataframe(pd.DataFrame(plan["books"], columns=HEADERS["books"])
                                     [["isbn", "title", "total_qty", "available_qty", "status"]],
                                     use_container_width=True, hide_index=True)
                        if plan["no_isbn"]:
                            st.warning("ISBN이 비어 있는 도서는 자산번호를 임시 열쇠로 사용합니다. "
                                       "변환 후 관리자 탭에서 ISBN을 채워 주세요: "
                                       + ", ".join(plan["no_isbn"][:10])
                                       + (" 외" if len(plan["no_isbn"]) > 10 else ""))
                        st.caption("⚠️ 예약 대기 기록은 초기화됩니다(백업에는 남습니다). 대출 기록은 유지됩니다.")
                        if st.checkbox("위 내용을 확인했습니다.", key="lib_mig_ok"):
                            if st.button("② 변환 실행", key="lib_mig_go", type="primary"):
                                stamp = _apply_migration(plan)
                                st.session_state["lib_mig"] = None
                                st.success(f"변환이 끝났습니다. 예전 자료는 `books_backup_{stamp}` 등에 있습니다.")
                                st.rerun()

            with st.expander("🧮 재고 점검  (‘대출가능’ 표시가 실제와 다를 때)"):
                st.caption("각 책의 '대출가능 수량'이 **총 권수 − 지금 대출 중인 권수**와 맞는지 확인합니다. "
                           "대출·반납 도중 오류가 났거나 시트를 손으로 고친 경우 어긋날 수 있어요.")
                if st.button("검사하기", key="lib_audit"):
                    st.session_state["lib_audit_result"] = _audit_stock()
                res = st.session_state.get("lib_audit_result")
                if res is not None:
                    if not res:
                        st.success("모든 도서의 수량이 정상입니다.")
                    else:
                        st.warning(f"{len(res)}종의 수량이 맞지 않습니다.")
                        st.dataframe(pd.DataFrame(res).drop(columns=["row"]),
                                     use_container_width=True, hide_index=True)
                        if st.button("✅ 올바른 값으로 자동 수정", key="lib_audit_fix"):
                            n = _fix_stock(res)
                            st.session_state["lib_audit_result"] = None
                            st.success(f"{n}종을 수정했습니다."); st.rerun()

            with st.expander("➕ 도서 등록  (같은 ISBN을 다시 등록하면 수량이 늘어납니다)", expanded=True):
                ic1, ic2 = st.columns([3, 1])
                isbn_in = ic1.text_input("ISBN (스캔 또는 입력) *", key="reg_isbn")
                if ic2.button("ISBN 조회", key="reg_lookup", use_container_width=True):
                    with st.spinner("도서 정보를 찾는 중입니다..."):
                        info, err = _lookup_isbn(isbn_in)
                    if info:
                        for k in ["title", "author", "publisher", "year", "category", "cover"]:
                            st.session_state[f"reg_{k}"] = info.get(k, "")
                        st.success("제목·저자·표지를 불러왔습니다. 확인 후 등록하세요.")
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
                    st.caption("책 소개는 등록 후 구글 시트 books 탭의 summary 열에 적어 주세요.")
                    if st.form_submit_button("등록", use_container_width=True):
                      with st.spinner("등록 중입니다..."):
                        ok, msg = _add_book({
                            "isbn": isbn_in, "title": title, "author": author, "publisher": publisher,
                            "year": year, "category": category, "location": location,
                            "qty": qty, "cover": st.session_state.get("reg_cover", "")})
                      if ok:
                          for k in ["reg_title", "reg_author", "reg_publisher", "reg_year",
                                    "reg_category", "reg_cover"]:
                              st.session_state[k] = ""
                          st.success(msg)
                      else:
                          st.error(msg)

            with st.expander("📖 책 소개가 비어 있는 책 (구글 시트에 직접 적어 주세요)"):
                _nosum = [b for b in _records("books")
                          if not str(b.get("summary", "") or "").strip()
                          and str(b.get("status", "")).strip() != "폐기"]
                st.markdown(f"소개가 비어 있는 책 : **{len(_nosum)}종**")
                st.caption("구글 시트 `대한사료_도서관_DB` → **books** 탭 → **summary** 열에 "
                           "소개 글을 적고 저장하시면, 1분 안에 도서관 화면에 반영됩니다.")
                if "summary" not in _header("books"):
                    if st.button("시트에 summary 열 만들기", key="mk_sum_col"):
                        if _ensure_col("books", "summary"):
                            st.success("books 탭 맨 오른쪽에 summary 열을 만들었습니다.")
                            st.rerun()
                        else:
                            st.error("열을 만들지 못했습니다. 구글 시트 공유 권한을 확인해 주세요.")
                if _nosum:
                    st.dataframe(pd.DataFrame([{"ISBN": b.get("isbn"), "제목": b.get("title"),
                                                "저자": _clean_author(b.get("author"))}
                                               for b in _nosum]),
                                 use_container_width=True, hide_index=True)
                else:
                    st.success("모든 책에 소개가 들어 있습니다.")

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
