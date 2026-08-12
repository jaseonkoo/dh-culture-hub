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
import smtplib
from email.message import EmailMessage

# 휴대폰 카메라 바코드 해석용 (없어도 나머지 기능은 동작)
try:
    from PIL import Image
    import numpy as np
    import zxingcpp
    _SCAN_OK = True
except Exception:
    _SCAN_OK = False

# ---------------- 설정값 ----------------
LIB_VER    = "v25 (2026-07-30 · 목록 정리)"   # 👑 관리자 화면 맨 아래에 표시됩니다. 배포 확인용.
LIB_DB     = "대한사료_도서관_DB"
ADMIN_PW   = "dhfeed1947"    # 👈 관리자 비밀번호 (반드시 변경)

# 대출할 때 받는 이메일은 이 도메인만 허용합니다. (회사 메일만)
MAIL_DOMAIN = "daehanfeed.co.kr"

# 메일서버를 직접 정하고 싶을 때만 적으세요. 비워 두면 알아서 찾습니다.
# (회사 메일이 구글·네이버·다음이 아니라면 전산 담당자에게 물어보고 적어 주세요)
MAIL_HOST  = ""     # 예) "smtp.gmail.com"
MAIL_PORT  = 0      # 예) 465 또는 587

# 희망도서가 접수되면 이 주소로 알림 메일이 갑니다.
WISH_TO    = "jsgu@daehanfeed.co.kr"
# 반납 며칠 전에 미리 안내 메일을 보낼지
DUE_SOON   = 2
# 한 번에 보낼 수 있는 메일 최대 통수 (앱이 느려지지 않도록 제한)
MAIL_MAX   = 20

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
    "members":      ["saban", "name", "joined", "email"],
    "loans":        ["loan_id", "isbn", "title", "saban", "name",
                     "loan_date", "due_date", "return_date", "renew_count", "status"],
    "reservations": ["res_id", "isbn", "title", "saban", "name", "res_date", "status"],
    "wishlist":     ["wish_id", "title", "author", "isbn", "saban", "name", "reason", "date", "status"],
    # 같은 안내 메일을 두 번 보내지 않도록 기록해 두는 탭 (자동 생성됩니다)
    "maillog":      ["date", "kind", "key", "to", "result"],
    # 관리자가 화면에서 켜고 끈 설정을 담아 두는 탭 (자동 생성됩니다)
    "settings":     ["key", "value"],
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

def _setting(key, default=""):
    """관리자가 화면에서 켜고 끈 설정을 읽는다. (구글 시트 settings 탭)"""
    try:
        for r in _records("settings"):
            if str(r.get("key", "")).strip() == key:
                return str(r.get("value", "")).strip()
    except Exception:
        pass
    return default

def _set_setting(key, value):
    """설정을 시트에 적어 둔다. 이미 있으면 고치고, 없으면 새로 한 줄 만든다."""
    try:
        ws = _ws("settings")
        for i, r in enumerate(_records("settings")):
            if str(r.get("key", "")).strip() == key:
                _retry(ws.update_cell, i + 2, _col("settings", "value"), str(value))
                _refresh()
                return True
        vals = {"key": key, "value": str(value)}
        _retry(ws.append_row, [vals.get(h, "") for h in _header("settings")])
        _refresh()
        return True
    except Exception:
        return False

def _wish_on():
    """희망도서 신청 화면을 직원들에게 보여줄지 여부. (기본값: 보여줌)"""
    return _setting("wish_on", "1") != "0"

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
# 이메일 알림
#  - 보내는 계정 정보는 앱 설정(Secrets)에만 넣습니다. 코드에 적지 마세요.
#      [mail]
#      sender = "dhfeed.hr.ai@gmail.com"
#      app_password = "구글 앱 비밀번호 16자리"
#  - 설정이 없으면 메일만 조용히 건너뛰고, 도서관 기능은 그대로 동작합니다.
# ==========================================================
# ----- 메일 계정 자동 찾기 --------------------------------------------------
# 이미 다른 프로그램(멘토링 등)에서 메일을 쓰고 계시면, Secrets 안의 이름이
# [mail] 이 아닐 수 있습니다. 그래서 이름을 정해 놓고 찾지 않고,
# Secrets 전체를 훑어서 '메일 주소처럼 생긴 값 + 비밀번호처럼 생긴 값'을 찾아 씁니다.

# 이 묶음들은 구글 시트 열쇠라서 절대 건드리지 않습니다.
_MAIL_SKIP = ("gcp", "service_account", "serviceaccount", "google_service",
              "firebase", "credential", "connections", "sheet")
# 보내는 사람이 아니라 '받는 사람'을 적어 둔 칸 (여기서 계정을 읽으면 안 됩니다)
_MAIL_NOT_SENDER = ("to", "recv", "receiv", "target", "받는", "수신", "manager", "admin_mail")
# 비밀번호가 들어 있을 만한 칸 이름
_MAIL_PW_KEY = ("pass", "pw", "secret", "token", "key", "app_", "비밀번호", "암호")

def _looks_mail(v):
    v = str(v or "").strip()
    return ("@" in v) and ("." in v.split("@")[-1]) and (" " not in v) and 6 <= len(v) <= 120

def _secret_groups():
    """Secrets 안의 묶음들을 [(묶음이름, 사전)] 으로 돌려준다.
       맨 앞은 묶음 없이 그냥 적어 둔 값들."""
    out, top = [], {}
    try:
        keys = list(st.secrets.keys())
    except Exception:
        return out
    for k in keys:
        try:
            v = st.secrets[k]
        except Exception:
            continue
        if hasattr(v, "keys"):
            out.append((str(k), v))
        else:
            top[str(k)] = v
    if top:
        out.insert(0, ("(묶음 없음)", top))
    return out

def _mail_pick(name, d):
    """묶음 하나에서 보내는 주소·비밀번호를 찾아본다. 못 찾으면 None."""
    try:
        items = [(str(k), d[k]) for k in d.keys()]
    except Exception:
        return None
    sender = pw = ""
    for k, v in items:
        if hasattr(v, "keys"):
            continue
        kl = k.lower()
        val = str(v or "").strip()
        if not val:
            continue
        if (not sender) and _looks_mail(val) and not any(b in kl for b in _MAIL_NOT_SENDER):
            sender = val
        elif (not pw) and any(b in kl for b in _MAIL_PW_KEY) and not _looks_mail(val):
            if 4 <= len(val) <= 100 and "BEGIN" not in val:
                pw = val
    if not (sender and pw):
        return None
    host = ""
    port = 0
    for k, v in items:
        kl = str(k).lower()
        if "host" in kl or "server" in kl:
            host = str(v or "").strip()
        if kl == "port" or kl.endswith("_port"):
            port = _to_int(v, 0)
    if MAIL_HOST:
        host = MAIL_HOST
    if MAIL_PORT:
        port = _to_int(MAIL_PORT, 0)
    if not host:
        host = _mail_host_guess(sender)
    if not port:
        port = 587 if ("outlook" in host or "office365" in host) else 465
    return {"sender": sender, "pw": pw, "host": host, "port": port, "where": name}

def _mail_host_guess(sender):
    """메일 주소를 보고 서버 주소를 짐작한다."""
    dom = str(sender).split("@")[-1].lower()
    table = {"gmail.com": "smtp.gmail.com",
             "naver.com": "smtp.naver.com",
             "daum.net": "smtp.daum.net",
             "hanmail.net": "smtp.daum.net",
             "nate.com": "smtp.mail.nate.com",
             "outlook.com": "smtp-mail.outlook.com",
             "hotmail.com": "smtp-mail.outlook.com"}
    return table.get(dom, "smtp.gmail.com")

def _mail_cfg():
    """앱 설정(Secrets)에서 메일 보내는 계정을 찾는다. 없으면 None."""
    groups = _secret_groups()
    # 이름이 메일 같아 보이는 묶음을 먼저 살펴본다.
    likely = ("mail", "smtp", "gmail", "naver")
    groups.sort(key=lambda t: 0 if any(w in t[0].lower() for w in likely) else 1)
    for name, d in groups:
        if any(b in name.lower() for b in _MAIL_SKIP):
            continue
        got = _mail_pick(name, d)
        if got:
            return got
    return None

def _mail_seen():
    """관리자 화면에서 '무엇이 보이는지'를 알려주기 위한 목록.
       비밀번호 값은 절대 보여주지 않습니다."""
    rows = []
    for name, d in _secret_groups():
        skip = any(b in name.lower() for b in _MAIL_SKIP)
        try:
            keys = [str(k) for k in d.keys()]
        except Exception:
            keys = []
        rows.append({"묶음 이름": name,
                     "안에 있는 칸 이름": ", ".join(keys[:12]) if keys else "-",
                     "메일 계정으로 볼까요?": "아니오 (구글 시트 열쇠)" if skip else "예"})
    return rows

def _mail_ready():
    return _mail_cfg() is not None

def _send_mail(to, subject, body):
    """메일 한 통 보내기. 반환: (성공여부, 메시지)"""
    cfg = _mail_cfg()
    if not cfg:
        return False, "메일 계정을 찾지 못했습니다. (👑 관리자 → 📧 이메일 알림 설정 에서 확인)"
    to = str(to or "").strip()
    if not _valid_mail(to):
        return False, "이메일 주소가 올바르지 않습니다."
    msg = EmailMessage()
    msg["Subject"] = str(subject)
    msg["From"] = "대한사료 사내도서관 <%s>" % cfg["sender"]
    msg["To"] = to
    msg.set_content(str(body))
    # 465(SSL)와 587(TLS) 중 어느 쪽인지 몰라서 실패하는 일이 많습니다.
    # 그래서 정해진 포트로 먼저 해 보고, 안 되면 나머지 포트로 한 번 더 해 봅니다.
    first = int(cfg["port"] or 465)
    ports = [first, 587 if first != 587 else 465]
    err = ""
    for pt in ports:
        try:
            if pt == 587:
                with smtplib.SMTP(cfg["host"], pt, timeout=20) as sv:
                    sv.ehlo(); sv.starttls(); sv.login(cfg["sender"], cfg["pw"]); sv.send_message(msg)
            else:
                with smtplib.SMTP_SSL(cfg["host"], pt, timeout=20) as sv:
                    sv.login(cfg["sender"], cfg["pw"]); sv.send_message(msg)
            return True, "보냈습니다."
        except smtplib.SMTPAuthenticationError:
            # 비밀번호 문제는 포트를 바꿔도 똑같으므로 여기서 멈춥니다.
            return False, ("메일 계정 로그인에 실패했습니다. 앱 비밀번호(16자리)를 다시 확인해 주세요. "
                           "· 계정 %s" % cfg["sender"])
        except Exception as e:
            err = "%s (서버 %s:%s)" % (str(e)[:100], cfg["host"], pt)
    return False, "메일 발송 실패: %s" % err

_MAIL_TAIL = ("\n\n───────────────\n대한사료 사내도서관\n"
              "이 메일은 자동으로 발송되었습니다. 문의는 인사팀으로 부탁드립니다.")

def _mail_quiet(to, subject, body):
    """실패해도 대출·반납 자체는 성공 처리한다. (메일은 부가 기능)"""
    if not _valid_mail(to) or not _mail_ready():
        return False
    ok, _ = _send_mail(to, subject, body + _MAIL_TAIL)
    return ok

# ---------------- 같은 안내를 두 번 보내지 않게 기록 ----------------
def _mailed_keys():
    """이미 '성공적으로' 보낸 안내의 (kind, key) 모음.
       실패한 것은 넣지 않으므로, 다음에 다시 시도합니다."""
    out = set()
    for r in _records("maillog"):
        if str(r.get("result", "")).strip() != "성공":
            continue
        out.add((str(r.get("kind", "")).strip(), str(r.get("key", "")).strip()))
    return out

def _log_mail(kind, key, to, result):
    try:
        vals = {"date": str(_today()), "kind": kind, "key": key, "to": to, "result": result}
        hdr = _header("maillog")
        _retry(_ws("maillog").append_row, [vals.get(h, "") for h in hdr])
        _refresh()
    except Exception:
        pass

def _due_date(loan):
    try:
        return datetime.datetime.strptime(str(loan.get("due_date", "")).strip(), "%Y-%m-%d").date()
    except Exception:
        return None

def _run_reminders():
    """반납 예정 안내(D-2)와 연체 안내 메일을 보낸다.
       같은 안내는 두 번 보내지 않는다. 반환: (보낸 수, 실패 수, 안내문)"""
    if not _mail_ready():
        return 0, 0, "메일 계정이 설정되어 있지 않습니다."
    done = _mailed_keys()
    sent = fail = miss = 0
    today = _today()
    for l in _records("loans"):
        if sent + fail >= MAIL_MAX:
            break
        if str(l.get("status", "")).strip() != "대출중":
            continue
        due = _due_date(l)
        if not due:
            continue
        lid = str(l.get("loan_id", "")).strip()
        saban = str(l.get("saban", "")).strip()
        to = _member_email(saban)
        if not _valid_mail(to):
            continue
        left = (due - today).days
        title = str(l.get("title", ""))
        name = str(l.get("name", ""))
        kind = key = subject = body = None
        if 0 < left <= DUE_SOON:
            kind, key = "due", lid
            subject = "[사내도서관] 반납 예정 안내 · %s" % title
            body = ("%s님 안녕하세요.\n\n"
                    "빌려 가신 책의 반납일이 다가왔습니다.\n\n"
                    "  · 도서 : %s\n"
                    "  · 반납 예정일 : %s (%d일 남았습니다)\n\n"
                    "더 읽고 싶으시면 도서관 화면의 [%s] 에서 "
                    "사번을 넣고 [연장] 을 누르시면 %d일 연장됩니다. "
                    "(예약 대기자가 있으면 연장되지 않습니다.)") % (name, title, str(due), left,
                                                        _menu_label(MENU[3]), RENEW_DAYS)
        elif left < 0:
            over = -left
            kind, key = "over", "%s_%d" % (lid, over // 7)
            subject = "[사내도서관] 반납이 늦어지고 있습니다 · %s" % title
            body = ("%s님 안녕하세요.\n\n"
                    "빌려 가신 책의 반납일이 지났습니다.\n\n"
                    "  · 도서 : %s\n"
                    "  · 반납 예정일 : %s\n"
                    "  · 연체 : %d일\n\n"
                    "다른 분이 기다리고 있을 수 있으니 반납을 부탁드립니다. "
                    "이미 반납하셨다면 이 메일은 무시해 주세요.") % (name, title, str(due), over)
        if not kind:
            continue
        if (kind, key) in done:
            continue
        ok = _mail_quiet(to, subject, body)
        _log_mail(kind, key, to, "성공" if ok else "실패")
        done.add((kind, key))
        if ok:
            sent += 1
            miss = 0
        else:
            fail += 1
            miss += 1
            # 계속 실패하면(메일 계정 문제 등) 화면이 멈추지 않도록 여기서 멈춘다.
            if miss >= 3:
                break
    msg = "안내 메일 %d통을 보냈습니다." % sent
    if fail:
        msg += " (%d통 실패)" % fail
    if sent == 0 and fail == 0:
        msg = "지금 보낼 안내 메일이 없습니다."
    if miss >= 3:
        msg += " 계속 실패해서 중간에 멈췄습니다. 메일 계정 설정을 확인해 주세요."
    return sent, fail, msg

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

def _member_email(saban):
    """저장해 둔 개인 이메일. 없으면 빈 문자열."""
    saban = str(saban).strip()
    if not saban:
        return ""
    for m in _records("members"):
        if str(m.get("saban")).strip() == saban:
            return str(m.get("email", "") or "").strip()
    return ""

def _valid_mail(addr):
    """일반적인 이메일 모양인지만 본다. (시험 발송 등 내부용)"""
    a = str(addr or "").strip()
    return ("@" in a) and ("." in a.split("@")[-1]) and (" " not in a) and len(a) >= 6

def _fix_mail(addr):
    """'@' 없이 아이디만 적었으면 회사 도메인을 붙여 준다.
       예) hong  →  hong@daehanfeed.co.kr
       대문자로 적어도 소문자로 고쳐 준다."""
    a = str(addr or "").strip().replace(" ", "").lower()
    if not a:
        return ""
    if "@" not in a:
        return a + "@" + MAIL_DOMAIN
    return a

def _company_mail(addr):
    """회사 이메일(@daehanfeed.co.kr) 인지 확인."""
    a = _fix_mail(addr)
    if not a or a.count("@") != 1:
        return False
    user, dom = a.split("@")
    return bool(user) and dom == MAIL_DOMAIN

MAIL_RULE = "회사 이메일(@%s)만 사용할 수 있습니다." % MAIL_DOMAIN

def _save_member_email(saban, email):
    """회원의 이메일을 members 탭에 적어 둔다. (바뀌었을 때만 씀)"""
    saban = str(saban).strip(); email = _fix_mail(email)
    if not saban or not _company_mail(email):
        return False
    if not _ensure_col("members", "email"):
        return False
    ws = _ws("members"); c = _col("members", "email")
    for i, m in enumerate(_records("members")):
        if str(m.get("saban")).strip() == saban:
            if str(m.get("email", "") or "").strip() == email:
                return True
            _retry(ws.update_cell, i + 2, c, email)
            _refresh()
            return True
    return False

def _ensure_member(saban, name, email=""):
    saban = str(saban).strip(); name = str(name).strip(); email = str(email or "").strip()
    if not saban:
        return None, "사번을 입력하세요."
    for m in _records("members"):
        if str(m.get("saban")).strip() == saban:
            kept = str(m.get("email", "") or "").strip()
            if email and email != kept:
                _save_member_email(saban, email)
                kept = email
            return {"saban": saban, "name": str(m.get("name", "")).strip(), "email": kept}, None
    if not name:
        return None, "처음 이용하시는 사번입니다. 이름도 함께 입력해 주세요."
    if email:
        _ensure_col("members", "email")
    vals = {"saban": saban, "name": name, "joined": str(_today()), "email": email}
    hdr = _header("members")
    _retry(_ws("members").append_row, [vals.get(h, "") for h in hdr])
    _refresh()
    return {"saban": saban, "name": name, "email": email}, None

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
def _checkout(isbn, saban, name, email=""):
    isbn = _norm_isbn(isbn)
    if not isbn:
        return False, "책의 ISBN 바코드를 스캔하세요."
    # 이메일은 반드시 있어야 하고, 회사 메일이어야 합니다.
    email = _fix_mail(email)
    if not email:
        return False, "이메일을 입력해 주세요. 반납 예정일과 연체 안내를 메일로 보내드립니다."
    if not _company_mail(email):
        return False, "이메일 주소를 확인해 주세요. %s (예: hong@%s)" % (MAIL_RULE, MAIL_DOMAIN)
    member, err = _ensure_member(saban, name, email)
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

    # 대출 확인 + 반납 예정일 안내 메일
    mailed = _mail_quiet(
        member.get("email", ""),
        "[사내도서관] 대출 완료 · %s" % book.get("title", ""),
        ("%s님 안녕하세요.\n\n대출이 완료되었습니다.\n\n"
         "  · 도서 : %s\n"
         "  · 대출일 : %s\n"
         "  · 반납 예정일 : %s (%d일)\n\n"
         "반납일이 다가오면 다시 안내 메일을 보내 드립니다. "
         "연장은 도서관 화면의 [%s] 에서 %d회까지 가능합니다.")
        % (member["name"], book.get("title", ""), str(loan_date), str(due), LOAN_DAYS,
           _menu_label(MENU[3]), MAX_RENEW))
    return True, {"title": book.get("title", ""), "due": str(due), "name": member["name"],
                  "mailed": mailed, "email": member.get("email", "")}

# ---------------- 반납 ----------------
def _pick_loan(isbn, saban=""):
    """반납할 대출 기록 하나를 고른다.
       반환 : (성공여부, 결과)  결과는 (줄번호, 대출기록) 또는 안내문
       ※ 확인 화면과 실제 반납이 똑같은 기준으로 고르도록 여기 한 곳에 모아 두었습니다."""
    open_loans = [(i + 2, r) for i, r in enumerate(_records("loans"))
                  if _norm_isbn(r.get("isbn")) == isbn and r.get("status") == "대출중"]
    if not open_loans:
        return False, "대출 중이 아닌 책입니다. (이미 반납되었을 수 있어요)"
    if len(open_loans) == 1:
        return True, open_loans[0]
    saban = str(saban).strip()
    if not saban:
        return False, {"need_saban": True,
                       "msg": "이 책은 여러 권이 대출 중이에요. 반납자의 사번을 입력한 뒤 다시 시도해 주세요."}
    cand = [t for t in open_loans if str(t[1].get("saban")).strip() == saban]
    if not cand:
        return False, {"need_saban": True, "msg": "해당 사번으로 이 책을 대출한 기록이 없어요. 사번을 확인해 주세요."}
    cand.sort(key=lambda t: str(t[1].get("due_date", "")))
    return True, cand[0]

def _checkin(isbn, saban=""):
    isbn = _norm_isbn(isbn)
    if not isbn:
        return False, "책의 ISBN 바코드를 스캔하세요."
    book = _find_book(isbn)
    if not book:
        return False, f"등록되지 않은 도서입니다. (ISBN {isbn})"
    ws = _ws("loans")
    _got, target = _pick_loan(isbn, saban)
    if not _got:
        return False, target

    row, loan = target
    _retry(ws.update_cell, row, _col("loans", "return_date"), str(_today()))
    _retry(ws.update_cell, row, _col("loans", "status"), "반납완료")
    _adjust_available(isbn, +1)
    waiting = _first_reservation(isbn)
    overdue = _is_overdue(loan)
    _refresh()

    # 반납한 사람에게 확인 메일
    _mail_quiet(
        _member_email(loan.get("saban")),
        "[사내도서관] 반납 완료 · %s" % book.get("title", ""),
        ("%s님 안녕하세요.\n\n반납이 확인되었습니다.\n\n"
         "  · 도서 : %s\n"
         "  · 반납일 : %s\n\n"
         "이용해 주셔서 감사합니다.") % (str(loan.get("name", "")), book.get("title", ""), str(_today())))
    # 예약해 둔 사람에게 '들어왔습니다' 메일
    if waiting:
        _mail_quiet(
            _member_email(waiting.get("saban")),
            "[사내도서관] 예약하신 책이 들어왔습니다 · %s" % book.get("title", ""),
            ("%s님 안녕하세요.\n\n예약해 두신 책이 반납되었습니다.\n\n"
             "  · 도서 : %s\n"
             "  · 위치 : %s\n\n"
             "다른 분이 먼저 빌려 갈 수 있으니 가능하면 오늘 중에 대출해 주세요.")
            % (str(waiting.get("name", "")), book.get("title", ""),
               str(book.get("location", "") or "안내데스크에 문의")))

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
            _mail_quiet(
                _member_email(r.get("saban")),
                "[사내도서관] 대출 연장 완료 · %s" % str(r.get("title", "")),
                ("%s님 안녕하세요.\n\n대출 기간이 연장되었습니다.\n\n"
                 "  · 도서 : %s\n"
                 "  · 새 반납 예정일 : %s\n\n"
                 "연장 횟수 %d/%d회를 사용하셨습니다.")
                % (str(r.get("name", "")), str(r.get("title", "")), str(newdue), cnt + 1, MAX_RENEW))
            return True, {"due": str(newdue)}
    return False, "대출 기록을 찾을 수 없습니다."

# ---------------- 예약 / 희망도서 ----------------
def _reserve(isbn, saban, name, email=""):
    email = _fix_mail(email)
    if email and not _company_mail(email):
        return False, "이메일 주소를 확인해 주세요. %s" % MAIL_RULE
    member, err = _ensure_member(saban, name, email)
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

def _add_wish(saban, name, title, author, reason, email=""):
    email = _fix_mail(email)
    if email and not _company_mail(email):
        return False, "이메일 주소를 확인해 주세요. %s" % MAIL_RULE
    member, err = _ensure_member(saban, name, email)
    if err:
        return False, err
    if not str(title).strip():
        return False, "희망 도서 제목을 입력하세요."
    wid = str(uuid.uuid4())[:8]
    _retry(_ws("wishlist").append_row,
           [wid, title, author, "", member["saban"],
            member["name"], reason, str(_today()), "접수"])
    _refresh()

    # 담당자에게 접수 알림
    _mail_quiet(
        WISH_TO,
        "[사내도서관] 희망도서 신청 · %s" % str(title),
        ("희망도서가 접수되었습니다.\n\n"
         "  · 도서 : %s\n"
         "  · 저자 : %s\n"
         "  · 신청자 : %s (%s)\n"
         "  · 신청자 이메일 : %s\n"
         "  · 신청일 : %s\n"
         "  · 신청 사유 : %s\n\n"
         "구글 시트 '%s' 의 wishlist 탭에서 처리 상태를 바꿀 수 있습니다.")
        % (str(title), str(author) or "-", member["name"], member["saban"],
           member.get("email", "") or "-", str(_today()),
           str(reason).strip() or "-", LIB_DB))
    # 신청자에게 접수 확인
    _mail_quiet(
        member.get("email", ""),
        "[사내도서관] 희망도서 신청이 접수되었습니다",
        ("%s님 안녕하세요.\n\n신청해 주신 희망도서가 접수되었습니다.\n\n"
         "  · 도서 : %s\n"
         "  · 신청일 : %s\n\n"
         "구입 여부가 결정되면 담당자가 안내해 드립니다.")
        % (member["name"], str(title), str(_today())))
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

@st.cache_data(ttl=3600, show_spinner=False)
def _img_ok(url):
    """그 주소로 그림이 실제로 열리는지 확인한다.
       확인할 수 없을 때(인터넷 차단 등)는 '열린다'고 보고 넘어갑니다."""
    u = str(url or "").strip()
    if not u:
        return False
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            code = getattr(r, "status", 200) or 200
            ctype = str(r.headers.get("Content-Type", "")).lower()
            clen = _to_int(r.headers.get("Content-Length", 0), 0)
        if code >= 400:
            return False
        if ctype and not ctype.startswith("image"):
            return False          # 그림이 아니라 '없는 페이지'가 온 경우
        if clen and clen < 900:
            return False          # 1KB도 안 되면 '표지 없음' 안내 그림일 때가 많습니다
        return True
    except Exception:
        return True

def _pick_cover(isbn, nl_url=""):
    """표지 그림을 정해진 순서대로 찾는다.
       ① 국립중앙도서관  ② 교보문고  ③ 구글
       반환 : (그림 주소, 어디서 가져왔는지)"""
    nl = _fix_cover_url(nl_url)
    if nl and _img_ok(nl):
        return nl, "국립중앙도서관"
    kb = _kyobo_cover(isbn)
    if kb and _img_ok(kb):
        return kb, "교보문고"
    gg = _fix_cover_url((_lookup_google(isbn) or {}).get("cover", ""))
    if gg and _img_ok(gg):
        return gg, "구글"
    # 셋 다 확인이 안 되면, 그래도 주소가 있는 것 중 앞선 것을 씁니다.
    for cand, src in ((nl, "국립중앙도서관"), (kb, "교보문고"), (gg, "구글")):
        if cand:
            return cand, src
    return "", ""

def _lookup_isbn(isbn):
    """반환값: (정보 dict 또는 None, 안내 메시지 또는 None)"""
    isbn = "".join(ch for ch in str(isbn) if ch.isdigit() or ch in "Xx")
    if not isbn:
        return None, "ISBN을 입력하세요."
    key = _get_nl_key()
    if key:
        info = _lookup_nl(isbn, key)
        if info:
            # 표지는 ① 국립중앙도서관 → ② 교보문고 → ③ 구글 순서로 찾습니다.
            info["cover"], info["cover_src"] = _pick_cover(isbn, info.get("cover", ""))
            return info, None
    info = _lookup_google(isbn)
    if info:
        info["cover"], info["cover_src"] = _pick_cover(isbn, "")
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

def _menu_label(m):
    """화면에 보이는 메뉴 이름.
       희망도서를 꺼 두면 네 번째 메뉴 이름이 '🙋 내 대출 현황'으로 바뀝니다.
       (프로그램 안에서 쓰는 이름은 그대로라서, 켜고 꺼도 화면이 헷갈리지 않습니다)"""
    if m == MENU[3] and not _wish_on():
        return "🙋 내 대출 현황"
    return m

def _goto_detail(isbn):
    """책 카드의 [자세히] → 책 상세 화면으로."""
    isbn = _norm_isbn(isbn)
    if not isbn:
        return
    st.session_state["lib_detail"] = isbn
    st.session_state["lib_detail_back"] = st.session_state.get("lib_menu", MENU[0])
    st.rerun()

def _back_to_list(key):
    """책 상세 화면 → 원래 보던 목록으로 되돌아간다.
       (플랫폼 메인으로 나가는 버튼과 헷갈리지 않도록 글자를 분명히 적어 둡니다)"""
    where = st.session_state.get("lib_detail_back", "")
    if where not in MENU:
        where = st.session_state.get("lib_menu", MENU[0])
    label = "◀ %s 화면으로 돌아가기" % _menu_label(where).split(" ", 1)[-1]
    if st.columns([1, 2])[0].button(label, key=key, use_container_width=True):
        st.session_state["lib_menu"] = where
        st.session_state.pop("lib_detail", None)
        st.session_state.pop("lib_detail_back", None)
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

def _fix_cover_url(u):
    """표지 그림 주소를 화면에서 잘 보이도록 다듬는다.
       · http:// 는 https:// 로 바꿉니다.
         (우리 도서관은 https 주소라서, http 그림은 브라우저가 막아 버립니다)
       · 구글 책 표지에 붙는 'edge=curl'(모서리 말림 효과)은 떼어 냅니다."""
    u = str(u or "").strip().strip('"').strip("'")
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if u.lower().startswith("http://"):
        u = "https://" + u[7:]
    if not u.lower().startswith("https://"):
        return ""
    u = u.replace("&edge=curl", "").replace("?edge=curl&", "?").replace("&zoom=1", "&zoom=2")
    return u

def _kyobo_cover(isbn):
    """교보문고에 올라와 있는 표지 그림 주소. (국내 책은 대부분 여기 있습니다)"""
    code = "".join(ch for ch in str(isbn or "") if ch.isdigit())
    if len(code) != 13:
        return ""
    return "https://contents.kyobobook.co.kr/sih/fit-in/458x0/pdt/%s.jpg" % code

def _cover_html(book, title):
    """표지 그림. 그림이 없거나 주소가 잘못되어 안 열리면
       뒤에 그려 둔 책등(스파인) 모양이 그대로 보입니다."""
    url = _fix_cover_url((book or {}).get("cover"))
    short = _esc(str(title)[:28])
    spine = ("<div class='lib-cv-fb'><div class='lib-cv-txt'>%s</div>"
             "<div class='lib-cv-emb'>大韓飼料<br>圖書</div></div>" % short)
    if url:
        return ("<div class='lib-cv'>%s<img src='%s' loading='lazy' alt=''></div>"
                % (spine, _esc(url)))
    return "<div class='lib-cv'>%s</div>" % spine

def _set_book_cover(isbn, url):
    """시트 books 탭의 cover 칸을 고쳐 쓴다."""
    key = _norm_isbn(isbn)
    if not key:
        return False
    try:
        ws = _ws("books")
        for i, r in enumerate(_records("books")):
            if _norm_isbn(r.get("isbn")) == key:
                _retry(ws.update_cell, i + 2, _col("books", "cover"), _fix_cover_url(url))
                _refresh()
                return True
    except Exception:
        pass
    return False

def _shelf_item(it, key):
    """책장 한 칸: 표지 + 제목 + 상태 + (대출가능일 때) 대출 버튼."""
    b = it.get("book") or None
    title = str((b or {}).get("title", "") or it.get("fallback", "") or "제목 없음")
    author_raw = str((b or {}).get("author", "") or "")
    author = _clean_author(author_raw)
    label = _book_avail_label(b)
    cls = _ST_CLASS.get(label, "off")
    rank = it.get("rank")
    cnt = it.get("count")

    rank_html = f"<div class='lib-rank'>{rank}</div>" if rank else ""
    # 책 위치는 목록에 넣지 않습니다. (책 자세히 보기 화면에서 볼 수 있습니다)
    meta2 = _qty_text(b) if b else ""
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

PER_ROW = 7      # 👈 한 줄에 몇 권씩 보여줄지. 숫자만 바꾸면 됩니다.

def _shelf(items, keyprefix, per_row=PER_ROW):
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

def _focus_isbn():
    """등록을 마친 뒤 커서를 다시 'ISBN' 칸으로 옮겨 준다.
       (브라우저에 아주 짧은 안내를 보내는 방식이라, 안 먹혀도 아무 문제 없습니다)"""
    try:
        import streamlit.components.v1 as components
    except Exception:
        return
    try:
        components.html(
            "<script>"
            "setTimeout(function(){try{"
            "var d=window.parent.document;"
            "var e=d.querySelectorAll('input[aria-label^=\"ISBN\"]');"
            "if(e.length){e[e.length-1].focus();e[e.length-1].select();}"
            "}catch(x){}},120);"
            "</script>", height=0)
    except Exception:
        pass

def _loan_counts():
    """책(ISBN)마다 지금까지 몇 번 빌려 갔는지 세어 둔다."""
    out = {}
    for l in _records("loans"):
        k = _norm_isbn(l.get("isbn"))
        if k:
            out[k] = out.get(k, 0) + 1
    return out

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

# 국립중앙도서관에서 받아 오는 '분류'는 한국십진분류(KDC)의 숫자입니다.
# 숫자만 보면 무슨 뜻인지 알 수 없어서, 화면에는 한글 이름으로 바꿔 보여줍니다.
KDC_NAME = {"0": "총류", "1": "철학", "2": "종교", "3": "사회과학", "4": "자연과학",
            "5": "기술과학", "6": "예술", "7": "언어", "8": "문학", "9": "역사"}

def _cat_text(v):
    """분류 값을 사람이 읽을 수 있게 바꾼다.
       '3' → '사회과학' / '325.1' → '사회과학 (325.1)' / '경영' → '경영' (그대로)"""
    raw = str(v or "").strip()
    if not raw:
        return ""
    core = raw.replace(".", "").replace(" ", "")
    if not core.isdigit():
        return raw          # 관리자가 직접 적은 글자는 손대지 않습니다.
    name = KDC_NAME.get(core[0], "")
    if not name:
        return raw
    return name if len(core) == 1 else "%s (%s)" % (name, raw)

def _book_summary_text(book):
    """책 소개 글. 시트에 없으면 빈 문자열."""
    return str((book or {}).get("summary", "") or "").strip()

def _stage_scan(kind, isbn):
    """스캔한 바코드를 '정말 하시겠어요?' 확인 대기 상태로 올려 둔다.
       kind : "co" = 대출, "ci" = 반납
       바코드가 이상하거나 없는 책이면 확인 화면까지 가지 않고 그 자리에서 알려 준다."""
    code = _norm_isbn(isbn)
    if not code:
        st.error("⚠️ 바코드를 읽지 못했습니다. 다시 스캔하거나 숫자를 직접 넣어 주세요.")
        return
    if not _find_book(code):
        st.error("⚠️ 등록되지 않은 도서입니다. (ISBN %s)" % code)
        return
    st.session_state["lib_%s_pend" % kind] = code
    st.rerun()

def _confirm_card(icon, head, rows, foot=""):
    """확인 화면에 보여 줄 노란 상자. (책 정보 + 안내문)"""
    body = "".join("<tr><th>%s</th><td>%s</td></tr>" % (_esc(k), _esc(v)) for k, v in rows)
    st.markdown(
        "<div class='lib-ask'><div class='lib-ask-h'>%s %s</div>"
        "<table class='lib-tb'>%s</table>%s</div>"
        % (icon, _esc(head), body,
           ("<div class='lib-ask-f'>%s</div>" % _esc(foot)) if foot else ""),
        unsafe_allow_html=True)

def _show_done():
    """확인 → 처리 → 화면 새로고침 뒤에 결과를 한 번 보여 준다."""
    m = st.session_state.pop("lib_done_msg", None)
    if not m:
        return
    if m.get("ok"):
        st.success(m.get("text", ""))
        if m.get("cap"):
            st.caption(m["cap"])
        if m.get("party"):
            st.balloons()
    else:
        st.error(m.get("text", ""))

def _detail_page(isbn):
    """책 한 권의 자세한 정보 화면."""
    b = _find_book(isbn)
    _back_to_list("dt_back")
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
                ("분류", _cat_text(b.get("category")) or "-"),
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
                    re_ = st.text_input("회사 이메일 (책이 들어오면 알려드립니다)",
                                        placeholder="hong@" + MAIL_DOMAIN)
                    if st.form_submit_button("예약 신청", use_container_width=True, type="primary"):
                        ok, msg = _reserve(b.get("isbn"), rs, rn, re_)
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

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _back_to_list("dt_back_bottom")

def _sec_title(text, sub=""):
    sub_html = f"<span class='lib-sec-sub'>{_esc(sub)}</span>" if sub else ""
    st.markdown(f"<div class='lib-sec'><h2>{_esc(text)}</h2>{sub_html}</div>", unsafe_allow_html=True)

# ==========================================================
# 화면
# ==========================================================
def run_library():
    """바깥 껍데기: 구글 시트 오류가 나도 앱이 죽지 않고 안내 메시지를 보여준다."""
    try:
        # 비밀번호는 플랫폼(app.py) 첫 화면에서 이미 한 번 확인합니다.
        # 도서관에서 또 묻지 않습니다.
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
.lib-head { text-align:center; padding:30px 10px 10px; }
.lib-head .em { font-family:'Nanum Myeongjo',serif; font-size:.72rem; letter-spacing:.34em;
  color:#A9782E; text-transform:uppercase; margin-bottom:10px; }
.lib-head h1 { font-size:2.35rem; font-weight:800; margin:0; color:#1F4A3C;
  font-family:'Nanum Myeongjo',serif; }

/* ---------- 확인 상자 (정말 대출/반납할까요?) ---------- */
.lib-ask { border:2px solid #A9782E; background:#FFF9EC; border-radius:12px;
  padding:16px 18px 14px; margin:6px 0 12px; }
.lib-ask-h { font-family:'Nanum Myeongjo',serif; font-size:1.15rem; font-weight:800;
  color:#7A5518; margin-bottom:10px; }
.lib-ask-f { margin-top:10px; font-size:.86rem; color:#7A5518; }
.lib-ask .lib-tb th { width:96px; color:#7A5518; }

/* ---------- 책 아래 버튼([자세히]·[빌리기])을 표지 너비에 맞춘다 ----------
   책 카드(.lib-bk) 바로 다음에 오는 버튼 줄만 좁혀 줍니다.
   (메뉴 버튼 등 다른 버튼은 건드리지 않습니다) */
[data-testid="stElementContainer"]:has(.lib-bk) + [data-testid="stHorizontalBlock"],
.element-container:has(.lib-bk) + [data-testid="stHorizontalBlock"],
[data-testid="stElementContainer"]:has(.lib-bk) + [data-testid="stElementContainer"],
.element-container:has(.lib-bk) + .element-container {
  max-width:var(--lib-cvw); margin-left:auto; margin-right:auto;
}
[data-testid="stElementContainer"]:has(.lib-bk) + [data-testid="stHorizontalBlock"] [data-testid="stColumn"],
.element-container:has(.lib-bk) + [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
  min-width:0;
}
[data-testid="stElementContainer"]:has(.lib-bk) + * button {
  padding-left:4px; padding-right:4px; font-size:.82rem;
}

/* ---------- 구역 제목 ---------- */
.lib-sec { display:flex; align-items:baseline; gap:12px; margin:26px 0 14px;
  border-bottom:1px solid #E0D6C3; padding-bottom:8px; }
.lib-sec h2 { font-size:1.28rem !important; font-weight:800; margin:0 !important; color:#1F4A3C;
  padding:0 !important; }
.lib-sec .lib-sec-sub { font-size:.82rem; color:#8C806E; }

/* ---------- 책 한 칸 ---------- */
.lib-bk { position:relative; padding:2px 2px 6px; text-align:center; }
/* 표지 너비. 아래 버튼 폭도 이 값에 맞춰집니다. */
:root { --lib-cvw: 150px; }
.lib-cv { position:relative; width:100%; max-width:var(--lib-cvw); margin:0 auto;
  aspect-ratio:3/4; border-radius:2px 7px 7px 2px; overflow:hidden;
  background:#F1E9D9; border:1px solid #DCCFB6;
  box-shadow:0 12px 16px -12px rgba(43,38,32,.65), 0 2px 3px rgba(43,38,32,.14);
  transition:transform .16s ease, box-shadow .16s ease; }
.lib-bk:hover .lib-cv { transform:translateY(-4px);
  box-shadow:0 18px 22px -12px rgba(43,38,32,.6), 0 3px 5px rgba(43,38,32,.18); }
/* 그림은 책등 위에 덮어씌웁니다. 그림이 안 열리면 뒤의 책등이 그대로 보입니다. */
.lib-cv img { position:relative; z-index:1; width:100%; height:100%;
  object-fit:cover; display:block; background:transparent; }
.lib-cv-fb { position:absolute; left:0; top:0; right:0; bottom:0;
  display:flex; flex-direction:column; justify-content:space-between;
  padding:16px 12px 12px 18px;
  background:linear-gradient(135deg,#2E5B4A 0%, #1F4A3C 60%, #17392E 100%); }
@supports not (aspect-ratio: 3 / 4) { .lib-cv { height:226px; } }
.lib-cv::before { content:""; position:absolute; left:0; top:0; bottom:0; width:10px; z-index:2;
  background:linear-gradient(90deg, rgba(0,0,0,.30), rgba(0,0,0,.05) 62%, rgba(255,255,255,.20)); }
.lib-cv-none { display:flex; flex-direction:column; justify-content:space-between; padding:16px 12px 12px 18px;
  background:linear-gradient(135deg,#2E5B4A 0%, #1F4A3C 60%, #17392E 100%); }
.lib-cv-txt { font-family:'Nanum Myeongjo',serif; font-weight:700; font-size:.82rem; line-height:1.4;
  color:#F3EAD6; }
.lib-cv-emb { font-family:'Nanum Myeongjo',serif; font-size:.62rem; line-height:1.35; text-align:right;
  color:#C9A96A; letter-spacing:.12em; }

.lib-tt { font-weight:700; font-size:.88rem; line-height:1.45;
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
  border-radius:6px; padding:7px 0; background:rgba(255,255,255,.4);
  max-width:var(--lib-cvw); margin:6px auto 0; }

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
        "</div>", unsafe_allow_html=True)

    if not _SCAN_OK:
        st.info("ℹ️ 휴대폰 카메라 스캔을 쓰려면 requirements.txt에 zxing-cpp, pillow가 필요합니다. (직접 입력·USB 스캐너는 지금도 가능)")

    _old_sheet = _needs_migration()
    if _old_sheet:
        st.error("⚠️ 구글 시트가 아직 **예전 형식(자산번호 방식)** 입니다. "
                 "그래서 모든 책이 '대출중'으로 보이고, 대출·반납이 정상 동작하지 않습니다.\n\n"
                 "👑 **관리자 메뉴 → 🔧 시트 형식 변환** 을 한 번 실행해 주세요. "
                 "기존 도서·대출 기록은 그대로 옮겨지고, 예전 탭은 백업으로 남습니다.")

    # 반납 예정·연체 안내 메일은 '누군가 도서관을 열었을 때' 하루 한 번만 보냅니다.
    # (스트림릿 앱은 아무도 접속하지 않으면 잠들어 있어서 스스로 시간을 재지 못합니다)
    if _mail_ready() and st.session_state.get("lib_mail_day") != str(_today()):
        st.session_state["lib_mail_day"] = str(_today())
        try:
            _s, _f, _ = _run_reminders()
            if _s:
                st.toast("반납 안내 메일 %d통을 보냈습니다." % _s)
        except Exception:
            pass

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
        if _mcols[_i].button(_menu_label(_m), key=f"lib_nav_{_i}", use_container_width=True,
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
        recent = list(reversed(home_books))[:PER_ROW * 2]
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

        # 바로 앞에서 처리한 결과(대출 완료·반납 완료)를 여기서 보여 줍니다.
        _show_done()
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

            # 회사 이메일 (필수). 한 번 넣으면 다음부터 자동으로 채워집니다.
            _saved_mail = _member_email(saban)
            email = st.text_input("회사 이메일 *필수*  (반납 예정일·연체 안내를 받습니다)",
                                  value=_saved_mail,
                                  placeholder="hong@" + MAIL_DOMAIN)
            _mail_ok = _company_mail(email)
            _typed = str(email).strip()
            if not _typed:
                st.caption("✉️ 회사 이메일을 반드시 적어 주세요. "
                           "`@` 앞의 아이디만 적으셔도 됩니다. (자동으로 @%s 가 붙습니다)" % MAIL_DOMAIN)
            elif not _mail_ok:
                st.warning("이메일 주소를 확인해 주세요. %s  (예: hong@%s)" % (MAIL_RULE, MAIL_DOMAIN))
            elif _saved_mail and _fix_mail(email) == _saved_mail:
                st.caption("✉️ 저장된 이메일 **%s** 로 안내가 갑니다. 바꾸시려면 위 칸을 고쳐 주세요."
                           % _fix_mail(email))
            else:
                st.caption("✉️ **%s** 로 안내가 갑니다." % _fix_mail(email))
            if not _mail_ready():
                st.caption("⚠️ 아직 메일 보내는 계정이 설정되지 않아 안내 메일은 발송되지 않습니다. "
                           "(관리자 메뉴 → 📧 이메일 알림 설정)")

            # 스캔하자마자 바로 빌려지지 않습니다.
            # 먼저 '이 책이 맞습니까?' 하고 한 번 더 물어봅니다.
            _pend = str(st.session_state.get("lib_co_pend", "") or "")
            if _pend:
                _pb = _find_book(_pend) or {}
                _rows = [("제목", str(_pb.get("title", "") or "-")),
                         ("저자", _clean_author(_pb.get("author")) or "-"),
                         ("책 위치", str(_pb.get("location", "") or "-")),
                         ("ISBN", _pend),
                         ("빌리는 분", ("%s (%s)" % (name, saban)) if str(name).strip() else "사번·이름을 위에 넣어 주세요"),
                         ("반납 예정일", str(_today() + datetime.timedelta(days=LOAN_DAYS)))]
                _confirm_card("📕", "이 책을 빌리시는 것이 맞습니까?", _rows,
                              "책 표지의 제목과 위 제목이 같은지 확인한 뒤 [네, 대출합니다]를 눌러 주세요.")
                _av = _to_int(_pb.get("available_qty"))
                if _av <= 0:
                    st.warning("지금 남은 수량이 없습니다. 그래도 진행하면 대출되지 않고 안내가 나옵니다.")
                yc, nc = st.columns(2)
                if yc.button("✅ 네, 대출합니다", key="co_yes", type="primary", use_container_width=True):
                    ok, res = _checkout(_pend, saban, name, email)
                    if ok:
                        st.session_state.pop("lib_co_pend", None)
                        st.session_state.pop("lib_prefill_isbn", None)
                        st.session_state.pop("lib_prefill_title", None)
                        st.session_state["lib_done_msg"] = {
                            "ok": True, "party": True,
                            "text": "✅ **%s** 대출 완료 · 반납예정일 **%s**" % (res["title"], res["due"]),
                            "cap": ("✉️ %s 로 안내 메일을 보냈습니다." % res["email"]) if res.get("mailed") else ""}
                        st.rerun()
                    else:
                        # 사번·이메일이 빠졌을 때는 확인 화면을 그대로 두어
                        # 위 칸을 고친 뒤 다시 누를 수 있게 합니다.
                        st.error("⚠️ %s" % res)
                if nc.button("✖ 아니요, 취소", key="co_no", use_container_width=True):
                    st.session_state.pop("lib_co_pend", None)
                    st.rerun()
            elif use_cam:
                img = st.camera_input("책의 ISBN 바코드를 비추고 촬영하세요", key="co_cam")
                code = _decode(img)
                _shot = getattr(img, "file_id", None) or getattr(img, "id", None) or code
                if code and st.session_state.get("co_last") != _shot:
                    st.session_state["co_last"] = _shot
                    _stage_scan("co", code)
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 조금 더 가까이서 다시 촬영해 주세요.")
            else:
                with st.form("co_form", clear_on_submit=True):
                    manual = st.text_input("책 ISBN 바코드 (USB 스캐너로 스캔 또는 숫자 직접 입력)",
                                           value=prefill)
                    _go = st.form_submit_button("확인 화면으로", use_container_width=True,
                                                type="primary")
                if _go:
                    _stage_scan("co", manual)
            st.markdown("<p class='lib-hint'>USB 스캐너는 입력칸에 커서를 두고 스캔하면 자동 입력됩니다. "
                        "스캔한 뒤에는 <b>책이 맞는지 한 번 더 확인</b>하고 [네, 대출합니다]를 눌러 주세요.</p>",
                        unsafe_allow_html=True)

        # ===== 반납 =====
        else:
            ci_saban = st.text_input("반납자 사번 (같은 책 여러 권이 대출 중일 때만 필요)", key="ci_saban", placeholder="보통은 비워두어도 됩니다")
            # 반납도 스캔하자마자 처리하지 않고, 한 번 더 확인합니다.
            _pendi = str(st.session_state.get("lib_ci_pend", "") or "")
            if _pendi:
                _cb = _find_book(_pendi) or {}
                _got, _tg = _pick_loan(_pendi, ci_saban)
                _rows = [("제목", str(_cb.get("title", "") or "-")),
                         ("ISBN", _pendi)]
                _foot = "책 표지의 제목과 위 제목이 같은지 확인한 뒤 [네, 반납합니다]를 눌러 주세요."
                _blocked = False
                if _got:
                    _loan = _tg[1]
                    _late = _is_overdue(_loan)
                    _rows += [("빌린 분", "%s (%s)" % (str(_loan.get("name", "")),
                                                     str(_loan.get("saban", "")))),
                              ("대출일", str(_loan.get("loan_date", "") or "-")),
                              ("반납 예정일", str(_loan.get("due_date", "") or "-")
                                              + ("  ⚠️ 연체" if _late else ""))]
                else:
                    _blocked = True
                    if isinstance(_tg, dict) and _tg.get("need_saban"):
                        _foot = _tg["msg"]
                    else:
                        _foot = str(_tg)
                _confirm_card("📗", "이 책을 반납하시는 것이 맞습니까?", _rows, _foot)
                if _blocked and isinstance(_tg, dict) and _tg.get("need_saban"):
                    st.info("위쪽 **반납자 사번** 칸에 사번을 넣은 뒤 [네, 반납합니다]를 눌러 주세요.")
                elif _blocked:
                    st.error("⚠️ %s" % _tg)
                yc, nc = st.columns(2)
                if yc.button("✅ 네, 반납합니다", key="ci_yes", type="primary", use_container_width=True):
                    ok, res = _checkin(_pendi, ci_saban)
                    if ok:
                        extra = " (연체 반납)" if res["overdue"] else ""
                        wait = (" · 🔔 예약자 %s님 대기" % res["waiting"]) if res["waiting"] else ""
                        st.session_state.pop("lib_ci_pend", None)
                        st.session_state["lib_done_msg"] = {
                            "ok": True,
                            "text": "✅ **%s** 반납 완료%s%s" % (res["title"], extra, wait)}
                        st.rerun()
                    elif isinstance(res, dict) and res.get("need_saban"):
                        st.info(res["msg"])
                    else:
                        st.session_state.pop("lib_ci_pend", None)
                        st.session_state["lib_done_msg"] = {"ok": False, "text": "⚠️ %s" % res}
                        st.rerun()
                if nc.button("✖ 아니요, 취소", key="ci_no", use_container_width=True):
                    st.session_state.pop("lib_ci_pend", None)
                    st.rerun()
            elif use_cam:
                img = st.camera_input("반납할 책의 ISBN 바코드를 촬영하세요", key="ci_cam")
                code = _decode(img)
                _shot = getattr(img, "file_id", None) or getattr(img, "id", None) or code
                if code and st.session_state.get("ci_last") != _shot:
                    st.session_state["ci_last"] = _shot
                    _stage_scan("ci", code)
                elif img is not None and not code:
                    st.warning("바코드를 인식하지 못했어요. 다시 촬영해 주세요.")
            else:
                with st.form("ci_form", clear_on_submit=True):
                    manual = st.text_input("반납할 책 ISBN 바코드")
                    _goi = st.form_submit_button("확인 화면으로", use_container_width=True,
                                                 type="primary")
                if _goi:
                    _stage_scan("ci", manual)
            st.markdown("<p class='lib-hint'>반납은 보통 책 바코드만 스캔하면 됩니다. 같은 책 여러 권이 동시에 "
                        "대출 중일 때만 사번을 넣어 주세요. 스캔한 뒤에는 <b>한 번 더 확인</b>하고 "
                        "[네, 반납합니다]를 눌러 주세요.</p>", unsafe_allow_html=True)

    # ---------------- 도서 검색 ----------------
    if menu == MENU[2]:
        q = st.text_input("제목 · 저자 · ISBN 검색", key="lib_q", placeholder="검색어를 입력하세요")
        books = [b for b in _records("books") if b.get("status") != "폐기"]
        ql = q.strip().lower()
        if ql:
            books = [b for b in books if any(
                ql in str(b.get(k, "")).lower() for k in ["title", "author", "isbn", "category", "publisher"])
                or ql in _cat_text(b.get("category")).lower()]
        # ----- 서가를 어떤 순서로 둘러볼지 고르는 곳 -----
        VIEWS = ["📚 전체 보기", "🏷️ 분류별 보기", "📅 출판연도순", "🔥 많이 빌린 순"]
        view = st.radio("어떻게 볼까요?", VIEWS, horizontal=True, key="lib_view")

        counts = _loan_counts()          # 책마다 몇 번 빌려 갔는지
        sub = "총 %d종" % len(books)
        items = []

        if view == VIEWS[1]:
            # 분류별 : 같은 갈래끼리 모아서 봅니다.
            groups = {}
            for b in books:
                groups.setdefault(_cat_text(b.get("category")) or "분류 없음", []).append(b)
            names = sorted(groups.keys(), key=lambda n: (n == "분류 없음", n))
            opts = ["전체 (%d종)" % len(books)] + ["%s (%d종)" % (n, len(groups[n])) for n in names]
            pick = st.selectbox("분류 고르기", opts, key="lib_cat")
            if pick != opts[0] and pick in opts:
                _one = names[opts.index(pick) - 1]
                books = groups[_one]
                sub = "%s · %d종" % (_one, len(books))
            books = sorted(books, key=lambda b: ((_cat_text(b.get("category")) or "힣"),
                                                 str(b.get("title", ""))))

        elif view == VIEWS[2]:
            # 출판연도순 : 최신 책부터 (연도가 비어 있는 책은 맨 뒤로)
            _neworder = st.selectbox("순서", ["최신 책부터", "오래된 책부터"], key="lib_year_order")
            _new_first = (_neworder == "최신 책부터")
            _has = [b for b in books if _to_int(b.get("year")) > 0]
            _none = sorted([b for b in books if _to_int(b.get("year")) <= 0],
                           key=lambda b: str(b.get("title", "")))
            _has = sorted(_has, key=lambda b: (_to_int(b.get("year")), str(b.get("title", ""))),
                          reverse=_new_first)
            books = _has + _none
            sub = "%s · 총 %d종" % (_neworder, len(books))

        elif view == VIEWS[3]:
            # 많이 빌린 순 : 대출 기록이 많은 책부터, 순위 번호도 붙여 줍니다.
            books = sorted(books, key=lambda b: (-counts.get(_norm_isbn(b.get("isbn")), 0),
                                                 str(b.get("title", ""))))
            sub = "누적 대출이 많은 순 · 총 %d종" % len(books)

        else:
            books = sorted(books, key=lambda b: str(b.get("title", "")))

        _sec_title("서가 둘러보기", sub)
        shown = books[:63]
        for i, b in enumerate(shown):
            it = {"book": b}
            if view == VIEWS[3]:
                _c = counts.get(_norm_isbn(b.get("isbn")), 0)
                if _c:
                    it["rank"] = i + 1
                    it["count"] = _c
            items.append(it)

        if not shown:
            if _wish_on():
                st.info("찾으시는 책이 없습니다. 🙋 메뉴에서 '희망도서'로 신청해 보세요.")
            else:
                st.info("찾으시는 책이 없습니다.")
        else:
            _shelf(items, "search")
        if len(books) > len(shown):
            st.markdown(f"<p class='lib-hint'>{len(books) - len(shown)}종이 더 있습니다. "
                        f"검색어를 넣거나 분류를 골라 좁혀 주세요.</p>", unsafe_allow_html=True)

        out_books = [b for b in books if _to_int(b.get("available_qty")) <= 0]
        if out_books:
            with st.expander("🔖 대출 중인 책 예약하기"):
                _opts = {f"{b.get('title')} ({b.get('author') or '저자 미상'})": b for b in out_books}
                _pick = st.selectbox("예약할 책", list(_opts.keys()), key="res_pick")
                with st.form("res_form", clear_on_submit=True):
                    rc1, rc2 = st.columns(2)
                    rs = rc1.text_input("사번", key="res_saban")
                    rn = rc2.text_input("이름 (처음 이용 시 1회)", key="res_name")
                    re_ = st.text_input("회사 이메일 (책이 들어오면 알려드립니다)",
                                        key="res_mail", placeholder="hong@" + MAIL_DOMAIN)
                    if st.form_submit_button("예약 신청", use_container_width=True, type="primary"):
                        _b = _opts.get(_pick)
                        ok, msg = _reserve((_b or {}).get("isbn"), rs, rn, re_)
                        (st.success if ok else st.error)(msg)

    # ---------------- 내 대출 / 희망도서 ----------------
    if menu == MENU[3]:
        _sec_title("내 대출 현황", "사번으로 조회")
        st.caption("사번을 입력하고 **엔터**를 누르시면 바로 조회됩니다. "
                   "(오른쪽 [🔍 조회] 버튼을 눌러도 됩니다)")
        # 폼 상자 안에 넣어 두면 엔터만 쳐도 조회됩니다.
        with st.form("my_loan_form", clear_on_submit=False):
            mq1, mq2 = st.columns(2)
            mq1.text_input("사번", key="my_saban",
                           placeholder="사번을 입력하고 엔터를 누르세요")
            # 오른쪽 버튼을 왼쪽 입력칸과 같은 높이에 맞추기 위한 빈 자리입니다.
            mq2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            mq2.form_submit_button("🔍 조회", use_container_width=True, type="primary")

        msaban = str(st.session_state.get("my_saban", "") or "")
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

        # 희망도서 접수는 관리자가 켜고 끌 수 있습니다.
        # (👑 관리자 → 🙋 희망도서 접수 → [보이기] / [감추기])
        if _wish_on():
            _sec_title("희망도서 신청", "읽고 싶은 책을 알려주세요")
            with st.form("wish_form", clear_on_submit=True):
                wc1, wc2 = st.columns(2)
                ws_ = wc1.text_input("사번")
                wn_ = wc2.text_input("이름")
                we_ = st.text_input("회사 이메일 (구입 여부를 알려드립니다)",
                                    placeholder="hong@" + MAIL_DOMAIN)
                wt_ = st.text_input("도서 제목")
                wa_ = st.text_input("저자 (선택)")
                wr_ = st.text_area("신청 사유 (선택)", height=70)
                if st.form_submit_button("신청하기", use_container_width=True):
                    ok, msg = _add_wish(ws_, wn_, wt_, wa_, wr_, we_)
                    (st.success if ok else st.error)(msg)
            st.caption(f"신청하시면 담당자({WISH_TO})에게 바로 알림 메일이 갑니다.")

    # ---------------- 관리자 ----------------
    if menu == MENU[4]:
        if "lib_admin" not in st.session_state:
            st.session_state.lib_admin = False
        if not st.session_state.lib_admin:
            # 폼 안에 넣어 두면 비밀번호를 적고 '엔터'만 쳐도 로그인됩니다.
            with st.form("lib_admin_form", clear_on_submit=True):
                pw = st.text_input("관리자 비밀번호", type="password",
                                   placeholder="비밀번호를 입력하고 엔터를 누르세요")
                _adm_go = st.form_submit_button("로그인", type="primary")
            if _adm_go:
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
                # 여러 권을 연달아 등록하기 좋게 만든 화면입니다.
                # 등록을 마치면 칸이 모두 비워지고 커서가 ISBN 칸으로 돌아갑니다.
                _seed = _to_int(st.session_state.get("reg_seed"), 0)

                def _rk(n):
                    """칸마다 붙는 이름표. 등록이 끝나면 번호가 하나 올라가면서
                       칸들이 '새 칸'으로 다시 그려집니다. = 내용이 비워집니다."""
                    return "reg_%s_%d" % (n, _seed)

                def _rget(n, d=""):
                    return st.session_state.get(_rk(n), d)

                def _reg_reset():
                    # 책 위치(서가 번호)는 보통 연달아 같은 곳이라 그대로 남겨 둡니다.
                    st.session_state["reg_loc_keep"] = _rget("location")
                    st.session_state["reg_seed"] = _seed + 1
                    st.session_state["reg_focus"] = True

                _keep_loc = str(st.session_state.get("reg_loc_keep", "") or "")
                if _keep_loc and _rk("location") not in st.session_state:
                    st.session_state[_rk("location")] = _keep_loc

                _rdone = st.session_state.pop("reg_done", None)
                if _rdone:
                    (st.success if _rdone[0] else st.error)(_rdone[1])

                # ---------- ① ISBN · 조회 · 등록 (한 줄) ----------
                with st.form("reg_scan_form", clear_on_submit=False):
                    r1, r2, r3 = st.columns([3, 1, 1])
                    isbn_in = r1.text_input("ISBN (스캔 또는 입력) *", key=_rk("isbn"),
                                            placeholder="바코드를 스캔하거나 숫자를 넣고 엔터")
                    # 버튼 높이를 왼쪽 입력칸에 맞추기 위한 빈 자리입니다.
                    r2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    _look = r2.form_submit_button("🔎 조회", use_container_width=True)
                    r3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    _save = r3.form_submit_button("✅ 등록", use_container_width=True,
                                                  type="primary")
                st.caption("① 바코드를 스캔하면 **엔터**가 자동으로 눌려 바로 조회됩니다. "
                           "(직접 칠 때도 엔터를 누르면 조회됩니다) → "
                           "② 아래 내용을 확인하고 → ③ **[✅ 등록]** 을 누르면 화면이 비워지고 "
                           "커서가 다시 ISBN 칸으로 돌아갑니다. 다음 책을 바로 스캔하세요.")

                # ---------- ② 조회 ----------
                # 아직 책 정보를 안 불러온 상태에서 [등록]이 눌렸으면(엔터 등),
                # 잘못 등록되지 않도록 '조회'부터 해 줍니다.
                _need_look = _save and not str(_rget("title")).strip() and str(isbn_in).strip()
                if _need_look:
                    _save = False
                if _look or _need_look:
                    with st.spinner("도서 정보를 찾는 중입니다..."):
                        info, err = _lookup_isbn(isbn_in)
                    if info:
                        for k in ["title", "author", "publisher", "year", "cover"]:
                            st.session_state[_rk(k)] = str(info.get(k, "") or "")
                        # 분류는 숫자로 오기 때문에 한글 이름으로 바꿔서 넣어 둡니다.
                        st.session_state[_rk("category")] = _cat_text(info.get("category", ""))
                        _src = str(info.get("cover_src", "") or "")
                        if _src:
                            st.success("제목·저자를 불러왔습니다. "
                                       "표지는 **%s** 에서 가져왔습니다. 확인 후 등록하세요." % _src)
                        else:
                            st.success("제목·저자를 불러왔습니다. "
                                       "표지 그림은 찾지 못했습니다. 확인 후 등록하세요.")
                    else:
                        _kb, _ = _pick_cover(isbn_in, "")
                        st.session_state[_rk("cover")] = _kb
                        st.warning(err or "도서 정보를 찾지 못했습니다. 직접 입력해 주세요.")
                    if _need_look:
                        st.info("책 정보를 먼저 불러왔습니다. 내용을 확인하고 "
                                "**[✅ 등록]** 을 한 번 더 눌러 주세요.")

                # ---------- ③ 등록 ----------
                if _save:
                    with st.spinner("등록 중입니다..."):
                        ok, msg = _add_book({
                            "isbn": isbn_in,
                            "title": _rget("title"), "author": _rget("author"),
                            "publisher": _rget("publisher"), "year": _rget("year"),
                            "category": _rget("category"), "location": _rget("location"),
                            "qty": max(1, _to_int(_rget("qty", 1), 1)),
                            "cover": _fix_cover_url(_rget("cover"))})
                    if ok:
                        st.session_state["reg_done"] = (True, msg)
                        _reg_reset()
                        st.rerun()
                    else:
                        st.error(msg)

                # ---------- 표지 확인 ----------
                _cv_now = _fix_cover_url(_rget("cover"))
                cv1, cv2 = st.columns([1, 3])
                with cv1:
                    st.markdown(
                        "<div style='max-width:120px'>%s</div>"
                        % _cover_html({"cover": _cv_now}, _rget("title") or "표지 미리보기"),
                        unsafe_allow_html=True)
                with cv2:
                    if _cv_now:
                        st.caption("👈 위 그림이 **책 표지**로 보이면 정상입니다. "
                                   "초록색 책등 모양이 보이면 그 주소로는 그림이 열리지 않는 것이니, "
                                   "아래 [표지 자동 찾기]를 눌러 보시거나 주소를 직접 넣어 주세요.")
                    else:
                        st.caption("👈 아직 표지 그림이 없습니다. "
                                   "아래 [표지 자동 찾기]를 눌러 보세요.")
                    kb1, kb2 = st.columns(2)
                    if kb1.button("🔎 표지 자동 찾기", key="reg_kyobo",
                                  use_container_width=True,
                                  help="국립중앙도서관 → 교보문고 → 구글 순서로 찾습니다."):
                        with st.spinner("표지를 찾는 중입니다..."):
                            _k2, _ksrc = _pick_cover(isbn_in, "")
                        if _k2:
                            st.session_state[_rk("cover")] = _k2
                            st.rerun()
                        else:
                            st.warning("표지 그림을 찾지 못했습니다. "
                                       "ISBN을 확인하시거나 주소를 직접 넣어 주세요.")
                    if kb2.button("🧹 표지 비우기", key="reg_nocover", use_container_width=True):
                        st.session_state[_rk("cover")] = ""
                        st.rerun()

                # ---------- 책 정보 (확인하고 고치는 칸) ----------
                st.text_input("제목 *", key=_rk("title"))
                bc1, bc2 = st.columns(2)
                bc1.text_input("저자", key=_rk("author"))
                bc2.text_input("출판사", key=_rk("publisher"))
                bc3, bc4 = st.columns(2)
                bc3.text_input("출판연도", key=_rk("year"))
                bc4.text_input("분류 (책의 갈래)", key=_rk("category"),
                               help="ISBN 조회를 하면 자동으로 채워집니다. "
                                    "원하시는 말로 바꿔 적으셔도 됩니다. (예: 경영, 자기계발)")
                bc5, bc6 = st.columns(2)
                bc5.text_input("위치 (예: A-3)", key=_rk("location"),
                               help="한 번 적어 두면 [등록] 뒤에도 그대로 남습니다.")
                bc6.text_input("수량(권수)", key=_rk("qty"), placeholder="1",
                               help="비워 두면 1권으로 등록됩니다.")
                st.text_input("표지 그림 주소 (인터넷 주소)", key=_rk("cover"),
                              help="인터넷에서 표지 그림을 오른쪽 클릭 → "
                                   "'이미지 주소 복사' 한 것을 붙여 넣으셔도 됩니다.")
                st.caption("책 소개는 등록 후 구글 시트 books 탭의 summary 열에 적어 주세요.")

                if st.session_state.pop("reg_focus", False):
                    _focus_isbn()

            with st.expander("🖼️ 책 표지 채우기 · 고치기"):
                st.caption("표지 그림이 안 나오는 책을 여기서 고칠 수 있습니다. "
                           "책을 고르면 왼쪽에 지금 표지가 보입니다. "
                           "**초록색 책등 모양**이 보이면 그림이 열리지 않는다는 뜻입니다.")
                _nocv = [b for b in live_books if not _fix_cover_url(b.get("cover"))]
                _cvall = st.checkbox("표지가 있는 책도 함께 보기", key="cv_showall",
                                     help="표지를 이미 넣었지만 그림이 안 나오는 책을 고칠 때 켜 주세요.")
                _cvb = live_books if _cvall else _nocv
                if not live_books:
                    st.info("등록된 도서가 없습니다.")
                elif not _cvb:
                    st.success("표지가 없는 책이 없습니다. 모든 책에 표지가 들어 있습니다.")
                else:
                    if _nocv:
                        st.warning("표지가 없는 책이 **%d종** 있습니다." % len(_nocv))
                    _cvopt = {}
                    for b in _cvb:
                        mark = "  ⬜" if not _fix_cover_url(b.get("cover")) else ""
                        _cvopt["%s (%s)%s" % (b.get("title"), b.get("isbn"), mark)] = b
                    _cvpick = st.selectbox("표지가 없는 책  (⬜ 표시)" if not _cvall
                                           else "책 고르기  (⬜ 표시는 표지가 없는 책)",
                                           list(_cvopt.keys()), key="cv_pick")
                    _cvb1 = _cvopt.get(_cvpick) or {}
                    _cvisbn = str(_cvb1.get("isbn", ""))
                    _k1, _k2 = st.columns([1, 3])
                    with _k1:
                        st.markdown("<div style='max-width:130px'>%s</div>"
                                    % _cover_html(_cvb1, _cvb1.get("title", "")),
                                    unsafe_allow_html=True)
                    with _k2:
                        # 스트림릿은 '이미 그려진 입력칸'의 내용을 프로그램이 나중에
                        # 바꾸는 것을 막습니다. 그래서 버튼으로 주소를 채워 넣을 때는
                        # 입력칸 이름표(key)를 새것으로 바꿔 다시 그립니다.
                        _cvseed = _to_int(st.session_state.get("cv_seed"), 0)
                        _cvsame = st.session_state.get("cv_buf_for") == _cvisbn
                        _cvstart = (st.session_state.get("cv_buf", "") if _cvsame
                                    else str(_cvb1.get("cover", "") or ""))
                        _cvkey = "cv_url_%s_%d" % (_norm_isbn(_cvisbn), _cvseed)
                        _cvurl = st.text_input("표지 그림 주소", value=_cvstart, key=_cvkey,
                                               placeholder="https:// 로 시작하는 그림 주소")

                        def _cv_put(val):
                            """입력칸을 새로 그려서 주소를 채워 넣는다."""
                            st.session_state["cv_buf"] = val
                            st.session_state["cv_buf_for"] = _cvisbn
                            st.session_state["cv_seed"] = _cvseed + 1

                        _z1, _z2, _z3 = st.columns(3)
                        if _z1.button("🔎 표지 자동 찾기", key="cv_kyobo", use_container_width=True,
                                      help="국립중앙도서관 → 교보문고 → 구글 순서로 찾습니다."):
                            with st.spinner("표지를 찾는 중입니다..."):
                                _kk, _ksrc = _pick_cover(_cvisbn, "")
                            if _kk:
                                _cv_put(_kk)
                                st.rerun()
                            else:
                                st.warning("표지 그림을 찾지 못했습니다. 주소를 직접 넣어 주세요.")
                        if _z2.button("💾 저장", key="cv_save", use_container_width=True,
                                      type="primary"):
                            if _set_book_cover(_cvisbn, _cvurl):
                                _cv_put(_fix_cover_url(_cvurl))
                                st.success("표지를 저장했습니다."); st.rerun()
                            else:
                                st.error("저장하지 못했습니다. 구글 시트 공유 권한을 확인해 주세요.")
                        if _z3.button("🧹 비우기", key="cv_clear", use_container_width=True):
                            _set_book_cover(_cvisbn, "")
                            _cv_put("")
                            st.rerun()
                        st.caption("주소를 넣고 **저장**을 누른 뒤, 왼쪽 그림이 표지로 바뀌는지 보세요. "
                                   "그대로 책등 모양이면 그 주소로는 그림이 열리지 않는 것입니다.")
                    st.caption("표지 그림 주소 구하는 법 : 인터넷 서점에서 그 책을 찾아 "
                               "표지 그림 위에서 **마우스 오른쪽 클릭 → '이미지 주소 복사'** 를 누르고, "
                               "위 칸에 붙여 넣으시면 됩니다. "
                               "주소는 반드시 **https** 로 시작해야 합니다.")

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

            with st.expander("🙋 희망도서 접수  (직원 화면에 보이기 / 감추기)"):
                _won = _wish_on()
                if _won:
                    st.success("지금은 **보이는 중**입니다. "
                               "직원 화면의 네 번째 메뉴 이름은 **🙋 내 대출·희망도서** 입니다.")
                else:
                    st.warning("지금은 **감춰져 있습니다.** "
                               "직원 화면의 네 번째 메뉴 이름은 **🙋 내 대출 현황** 이고, "
                               "희망도서 신청 칸은 보이지 않습니다.")
                st.caption("· 보이기 : 직원이 읽고 싶은 책을 신청할 수 있습니다. "
                           "신청되면 담당자(%s)에게 메일이 갑니다.\n"
                           "· 감추기 : 신청 칸이 사라지고, 메뉴 이름이 '내 대출 현황'으로 바뀝니다. "
                           "이미 접수된 신청 내용은 지워지지 않고 아래 목록에 그대로 남습니다." % WISH_TO)
                _wc1, _wc2 = st.columns(2)
                if _wc1.button("👀 보이기", key="wish_on_btn", use_container_width=True,
                               type=("secondary" if _won else "primary"), disabled=_won):
                    if _set_setting("wish_on", "1"):
                        st.success("희망도서 신청 화면을 켰습니다."); st.rerun()
                    else:
                        st.error("설정을 저장하지 못했습니다. 구글 시트 공유 권한을 확인해 주세요.")
                if _wc2.button("🙈 감추기", key="wish_off_btn", use_container_width=True,
                               type=("primary" if _won else "secondary"), disabled=not _won):
                    if _set_setting("wish_on", "0"):
                        st.success("희망도서 신청 화면을 감췄습니다."); st.rerun()
                    else:
                        st.error("설정을 저장하지 못했습니다. 구글 시트 공유 권한을 확인해 주세요.")
                st.caption("이 설정은 구글 시트 `settings` 탭에 저장되어, "
                           "앱을 다시 켜도 그대로 유지됩니다. 모든 직원에게 똑같이 적용됩니다.")

            with st.expander("📧 이메일 알림 설정"):
                _cfg = _mail_cfg()
                if _cfg:
                    st.success("메일 보내는 계정을 찾았습니다 : **%s**" % _cfg["sender"])
                    st.caption("Secrets 의 **[%s]** 묶음에서 읽었습니다. "
                               "(메일서버 %s · 포트 %s)"
                               % (_cfg.get("where", "?"), _cfg["host"], _cfg["port"]))
                else:
                    st.warning("메일 보내는 계정을 찾지 못했습니다. "
                               "지금은 안내 메일이 **발송되지 않습니다.**")
                    st.caption("도서관은 Secrets 안을 전부 훑어서 "
                               "**메일 주소처럼 생긴 값**과 **비밀번호 칸**이 "
                               "같이 들어 있는 묶음을 찾습니다. "
                               "아래 표에서 무엇이 보이는지 확인해 주세요.")

                with st.expander("🔎 Secrets 에 무엇이 보이나요? (값은 안 보여줍니다)"):
                    st.caption("비밀번호·열쇠 값은 절대 표시하지 않습니다. **칸 이름만** 보여드립니다. "
                               "메일 계정이 들어 있는 묶음에는 "
                               "**주소 칸(@가 들어간 값)** 과 **비밀번호 칸**(이름에 "
                               "password·pw·secret·token·key 중 하나가 들어간 칸)이 "
                               "둘 다 있어야 합니다.")
                    _seen = _mail_seen()
                    if _seen:
                        st.dataframe(pd.DataFrame(_seen), use_container_width=True, hide_index=True)
                    else:
                        st.error("Secrets 를 하나도 읽지 못했습니다. "
                                 "스트림릿 앱 설정(Settings → Secrets)을 확인해 주세요.")
                    st.caption("이름이 달라서 못 찾는 것 같으면, "
                               "Secrets 맨 아래에 아래 3줄을 **추가**해 주세요. "
                               "(기존 내용은 절대 지우지 마세요)")
                    st.code('[mail]\nsender = "보내는주소@daehanfeed.co.kr"\n'
                            'app_password = "앱 비밀번호 16자리"', language="toml")

                st.markdown("**어떤 메일이 나가나요?**")
                st.caption("· 대출할 때 : 반납 예정일 안내\n"
                           "· 반납할 때 : 반납 확인\n"
                           "· 연장할 때 : 새 반납 예정일\n"
                           "· 반납 %d일 전 : 미리 안내\n"
                           "· 반납일이 지나면 : 연체 안내 (일주일에 한 번)\n"
                           "· 예약한 책이 들어오면 : 도착 안내\n"
                           "· 희망도서가 접수되면 : 담당자(%s)에게 알림"
                           % (DUE_SOON, WISH_TO))
                st.caption("대출할 때 **회사 이메일(@%s)** 은 반드시 입력해야 합니다. "
                           "`@` 앞의 아이디만 적어도 자동으로 도메인이 붙습니다." % MAIL_DOMAIN)

                if _cfg:
                    st.markdown("---")
                    st.markdown("**시험 발송**")
                    with st.form("mail_test_form"):
                        _tm = st.text_input("받을 주소", value=_cfg["sender"])
                        if st.form_submit_button("시험 메일 보내기"):
                            if not _valid_mail(_tm):
                                st.error("이메일 주소를 확인해 주세요.")
                            else:
                                _ok, _msg = _send_mail(
                                    _tm, "[사내도서관] 메일 설정 시험",
                                    "이 메일이 보이면 사내도서관 메일 설정이 정상입니다." + _MAIL_TAIL)
                                (st.success("보냈습니다. 받은 편지함(또는 스팸함)을 확인해 주세요.")
                                 if _ok else st.error(_msg))

                    st.markdown("---")
                    st.markdown("**반납 예정·연체 안내 메일**")
                    st.caption("이 메일은 **누군가 도서관 화면을 열었을 때 하루 한 번** 자동으로 나갑니다. "
                               "아무도 접속하지 않는 날에는 나가지 않으니, 그럴 때는 아래 버튼을 눌러 주세요. "
                               "이미 보낸 안내는 다시 보내지 않습니다.")
                    if st.button("지금 안내 메일 보내기", key="mail_run_now"):
                        with st.spinner("메일을 보내는 중입니다..."):
                            _s, _f, _note = _run_reminders()
                        if _s or _f:
                            st.success("보냄 %d통 / 실패 %d통" % (_s, _f))
                        else:
                            st.info(_note or "지금 보낼 안내 메일이 없습니다.")

                    st.markdown("---")
                    st.markdown("**이메일이 없는 대출자**")
                    _noml = []
                    for _l in active:
                        if not _valid_mail(_member_email(_l.get("saban"))):
                            _noml.append({"대출자": "%s(%s)" % (_l.get("name"), _l.get("saban")),
                                          "도서": _l.get("title"),
                                          "반납예정": _l.get("due_date")})
                    if _noml:
                        st.caption("이 분들께는 안내 메일이 가지 않습니다. "
                                   "구글 시트 `members` 탭 → `email` 열에 적어 주시거나, "
                                   "다음 대출 때 이메일을 입력받으면 자동으로 저장됩니다.")
                        st.dataframe(pd.DataFrame(_noml), use_container_width=True, hide_index=True)
                    else:
                        st.success("대출 중인 모든 분의 이메일이 있습니다.")

                if "email" not in _header("members"):
                    st.markdown("---")
                    if st.button("시트에 email 열 만들기", key="mk_mail_col"):
                        if _ensure_col("members", "email"):
                            st.success("members 탭 맨 오른쪽에 email 열을 만들었습니다.")
                            st.rerun()
                        else:
                            st.error("열을 만들지 못했습니다. 구글 시트 공유 권한을 확인해 주세요.")

            st.caption("프로그램 버전 : %s" % LIB_VER)

            with st.expander("👤 회원 등록"):
                with st.form("member_form", clear_on_submit=True):
                    mc1, mc2, mc3 = st.columns([1, 1, 2])
                    ms = mc1.text_input("사번")
                    mn = mc2.text_input("이름")
                    me = mc3.text_input("이메일 (선택)", placeholder="hong@daehanfeed.co.kr")
                    if st.form_submit_button("회원 등록"):
                        mem, err = _ensure_member(ms, mn, me)
                        (st.error(err) if err else st.success(f"등록/확인 완료: {mem['name']}"))
                st.caption("이메일은 반납 예정일·연체·예약 도착 안내에만 사용합니다. "
                           "직원이 대출할 때 직접 입력해도 자동으로 저장됩니다. "
                           "회사 이메일(@%s)만 저장됩니다." % MAIL_DOMAIN)

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
                if not _wish_on():
                    st.caption("※ 지금은 직원 화면에서 희망도서 접수를 감춰 두었습니다. "
                               "지난 신청 내역은 아래에 그대로 남아 있습니다.")
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
