from utils import *
import re
import json

# ==========================================================
# 📄 AX 역량진단 개인별 리포트 (axreport.py)
#   - 사번 + 이름으로 로그인합니다. ("개인별 데이터" 시트)
#   - 결과지를 화면에 그리고, 인쇄 / PDF 저장을 할 수 있습니다.
#   - 추천 교육에 링크가 있으면 눌러서 바로 들어갈 수 있습니다.
#   - DB : 구글 시트 "대한사료_AX역량 진단_DB"
#
#   👉 시트의 글을 고치면 이 화면도 같이 바뀝니다. (코드 수정 불필요)
# ==========================================================

AX_DB = "대한사료_AX역량 진단_DB"
AX_TITLE = "대한사료 2026년 AX역량진단 결과 안내"
AX_SUBTITLE = "나의 현재 위치를 확인하고, 다음 성장을 설계합니다."
AX_NOTE = ("이번 진단은 평가를 위한 것이 아니라, 현재의 역량에 맞는 교육과 "
           "성장 경로를 안내하기 위한 진단입니다.")
AX_FOOT_L = "※ 본 결과는 교육 참여 및 성장 지원을 위한 참고자료이며, 인사평가와 무관합니다."
AX_FOOT_R = "DAEHANFEED | AX Learning Roadmap"

# 역량 영역 3가지 (순서대로 화면에 나옵니다)
AREAS = ["AI의 이해", "AI 활용 및 자동화", "데이터 활용 및 분석"]

# 역량 레벨 4가지 (낮은 것부터)
LEVELS = ["기초", "L1", "L2", "L3"]

# 레벨별 색 (글자색, 배경색)
LEVEL_COLOR = {
    "기초": ("#6B7480", "#EEF0F3"),
    "L1":  ("#2F6FB5", "#EAF2FB"),
    "L2":  ("#2E7D5B", "#E9F4EE"),
    "L3":  ("#C8892A", "#FBF2DA"),
}

AX_SCOPE = ["https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"]


class AxBusy(Exception):
    """구글 시트가 잠깐 응답하지 않을 때."""
    pass


class AxError(Exception):
    """시트 모양이 예상과 다를 때."""
    pass


def _ax_retry(fn, *a, **kw):
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
    raise AxBusy(str(last))


def _norm(s):
    """띄어쓰기·줄바꿈을 없애고 소문자로 바꿔서 비교하기 쉽게 만듭니다."""
    return re.sub(r"\s+", "", str(s if s is not None else "")).lower()


def _clean(s):
    """앞뒤 공백과 '- ' 같은 글머리표를 떼어 냅니다."""
    t = str(s if s is not None else "").strip()
    t = re.sub(r"^[-•·]\s*", "", t)
    return t.strip()


def _ax_esc(x):
    return (str(x if x is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _match_area(text):
    """시트에 적힌 이름을 3개 영역 중 하나로 맞춰 줍니다."""
    t = _norm(text)
    if not t:
        return ""
    for a in AREAS:
        if _norm(a) == t:
            return a
    for a in AREAS:
        if _norm(a) in t or t in _norm(a):
            return a
    # 띄어쓰기·기호가 달라도 찾아 봅니다.
    key = re.sub(r"[^가-힣a-z0-9]", "", t)
    for a in AREAS:
        if re.sub(r"[^가-힣a-z0-9]", "", _norm(a)) == key:
            return a
    return ""


def _fix_level(v):
    """'L2', 'l2', '레벨2', '기초' 등을 표준 레벨 이름으로 바꿉니다."""
    t = _norm(v)
    if not t:
        return ""
    if "기초" in t or t in ("basic", "base", "lv0", "l0"):
        return "기초"
    m = re.search(r"([123])", t)
    if m and ("l" in t or "레벨" in t or "lv" in t or t == m.group(1)):
        return "L" + m.group(1)
    for lv in LEVELS:
        if _norm(lv) == t:
            return lv
    return str(v).strip()


# ==========================================================
# 구글 시트 읽기
# ==========================================================
@st.cache_resource(show_spinner=False)
def _ax_doc():
    """구글 로그인은 서버당 한 번만. 실패하면 기억하지 않습니다."""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], AX_SCOPE)
    client = gspread.authorize(creds)
    return _ax_retry(client.open, AX_DB)


@st.cache_data(ttl=600, show_spinner=False)
def _ax_grid(keys):
    """탭 이름에 keys 가 모두 들어간 시트를 찾아 통째로 읽어 옵니다.
       (탭 이름의 띄어쓰기나 오타가 조금 달라도 찾습니다)"""
    doc = _ax_doc()
    titles = []
    for ws in _ax_retry(doc.worksheets):
        t = _norm(ws.title)
        titles.append(ws.title)
        if all(k in t for k in keys):
            return _ax_retry(ws.get_all_values)
    raise AxError("시트에서 '%s' 탭을 찾지 못했습니다. (지금 있는 탭 : %s)"
                  % (" + ".join(keys), ", ".join(titles)))


def _reset_ax():
    for f in (_ax_doc, _ax_grid, load_people, load_level_def,
              load_need, load_courses, load_summary):
        try:
            f.clear()
        except Exception:
            pass


@st.cache_data(ttl=600, show_spinner=False)
def load_people():
    """개인별 데이터 : 사번·이름·소속·직급과 영역별 레벨을 읽어 옵니다.
       머리글이 두 줄(영역 / 항목)이라 직접 짚어 가며 읽습니다."""
    g = _ax_grid(("개인별",))
    if len(g) < 3:
        raise AxError("'개인별 데이터' 탭에 자료가 없습니다.")

    row1, row2 = g[0], g[1]
    width = max(len(row1), len(row2))
    row1 = list(row1) + [""] * (width - len(row1))
    row2 = list(row2) + [""] * (width - len(row2))

    # 첫 줄의 영역 이름을 오른쪽으로 이어서 채웁니다. (병합된 칸 처리)
    area_of = []
    cur = ""
    for c in row1:
        if str(c).strip():
            cur = str(c).strip()
        area_of.append(cur)

    # 기본 정보 칸 찾기
    def _basic(*names):
        for j in range(width):
            n = _norm(row1[j])
            if not _norm(row2[j]) and n in [_norm(x) for x in names]:
                return j
        for j in range(width):
            if _norm(row1[j]) in [_norm(x) for x in names]:
                return j
        return -1

    c_saban = _basic("사원번호", "사번", "사원 번호", "employee_id")
    c_name = _basic("사원명", "성명", "이름", "name")
    c_team = _basic("팀명", "소속팀", "부서", "team")
    c_gubun = _basic("사원구분", "구분", "직군", "gubun")
    c_pos = _basic("직급", "직위", "position")

    if c_saban < 0 or c_name < 0:
        raise AxError("'개인별 데이터' 탭에서 사원번호·사원명 칸을 찾지 못했습니다.")

    # 영역별 '레벨' 칸과 '합계' 칸 찾기
    lv_col, sc_col = {}, {}
    for j in range(width):
        sub = _norm(row2[j])
        area = _match_area(area_of[j])
        if not area:
            continue
        if "레벨" in sub or "level" in sub:
            lv_col[area] = j
        elif "합계" in sub or "점수" in sub or "total" in sub:
            sc_col[area] = j

    missing = [a for a in AREAS if a not in lv_col]
    if missing:
        raise AxError("'개인별 데이터' 탭에서 %s 의 레벨 칸을 찾지 못했습니다."
                      % ", ".join(missing))

    people = []
    for r in g[2:]:
        r = list(r) + [""] * (width - len(r))
        saban = _digits(r[c_saban])
        name = str(r[c_name]).strip()
        if not saban or not name:
            continue
        people.append({
            "saban": saban,
            "name": name,
            "team": str(r[c_team]).strip() if c_team >= 0 else "",
            "gubun": str(r[c_gubun]).strip() if c_gubun >= 0 else "",
            "position": str(r[c_pos]).strip() if c_pos >= 0 else "",
            "levels": {a: _fix_level(r[lv_col[a]]) for a in AREAS},
            "scores": {a: str(r[sc_col[a]]).strip() if a in sc_col else ""
                       for a in AREAS},
        })
    return people


def _digits(v):
    """'111610003.0' 처럼 적혀 있어도 숫자만 남깁니다."""
    s = str(v if v is not None else "").strip()
    s = re.sub(r"\.0+$", "", s)
    d = re.sub(r"\D", "", s)
    return d or s


def find_ax_person(saban, name):
    """사번 + 이름이 모두 맞는 사람을 찾습니다."""
    s = _digits(saban)
    n = str(name).strip()
    if not s or not n:
        return None
    for p in load_people():
        if p["saban"] == s and p["name"] == n:
            return p
    return None


@st.cache_data(ttl=600, show_spinner=False)
def load_level_def():
    """영역 및 레벨별 수준 정의 : {(레벨, 영역) : '~하는 수준'}"""
    g = _ax_grid(("수준", "정의"))
    return _table_by_level(g, one_per_cell=True)


@st.cache_data(ttl=600, show_spinner=False)
def load_need():
    """레벨별 필요역량 : {(레벨, 영역) : [역량, 역량, ...]}"""
    g = _ax_grid(("필요역량",))
    return _table_by_level(g, one_per_cell=False)


def _table_by_level(g, one_per_cell):
    """첫 줄이 영역 이름, 첫 칸이 레벨인 표를 읽어 옵니다.
       레벨 칸이 비어 있으면 '바로 위 레벨'이 계속되는 것으로 봅니다."""
    if not g:
        return {}
    hdr = g[0]
    col = {}
    for j, h in enumerate(hdr):
        a = _match_area(h)
        if a and a not in col:
            col[a] = j
    out = {}
    cur = ""
    for r in g[1:]:
        r = list(r) + [""] * (len(hdr) - len(r))
        first = str(r[0]).strip() if r else ""
        if first:
            cur = _fix_level(first)
        if not cur:
            continue
        for a, j in col.items():
            v = _clean(r[j]) if j < len(r) else ""
            if not v or v == "-":
                continue
            if one_per_cell:
                out.setdefault((cur, a), v)
            else:
                out.setdefault((cur, a), []).append(v)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def load_courses():
    """추천 교육 : {(레벨, 영역) : [(교육명, 링크), ...]}
       머리글이 두 줄(영역 / 교육명·링크)입니다."""
    g = _ax_grid(("추천",))
    if len(g) < 3:
        return {}
    row1, row2 = g[0], g[1]
    width = max(len(row1), len(row2))
    row1 = list(row1) + [""] * (width - len(row1))
    row2 = list(row2) + [""] * (width - len(row2))

    area_of = []
    cur = ""
    for c in row1:
        if str(c).strip():
            cur = str(c).strip()
        area_of.append(cur)

    pair = {}          # 영역 : (교육명 칸, 링크 칸)
    for j in range(width):
        a = _match_area(area_of[j])
        if not a:
            continue
        sub = _norm(row2[j])
        nm, lk = pair.get(a, (-1, -1))
        if "교육" in sub or "과정" in sub or "강의" in sub:
            nm = j
        elif "링크" in sub or "url" in sub or "주소" in sub:
            lk = j
        pair[a] = (nm, lk)

    out = {}
    cur_lv = ""
    for r in g[2:]:
        r = list(r) + [""] * (width - len(r))
        first = str(r[0]).strip()
        if first:
            cur_lv = _fix_level(first)
        if not cur_lv:
            continue
        for a, (nm, lk) in pair.items():
            if nm < 0:
                continue
            title = _clean(r[nm])
            if not title or title == "-":
                continue
            link = str(r[lk]).strip() if lk >= 0 else ""
            if not link.lower().startswith("http"):
                link = ""
            out.setdefault((cur_lv, a), []).append((title, link))
    return out


@st.cache_data(ttl=600, show_spinner=False)
def load_summary():
    """종합문구 : 세 영역의 레벨 조합에 맞는 한 문단을 찾습니다."""
    g = _ax_grid(("종합",))
    if len(g) < 2:
        return []
    hdr = g[0]
    col = {}
    for j, h in enumerate(hdr):
        a = _match_area(h)
        if a and a not in col:
            col[a] = j
    txt_col = -1
    for j, h in enumerate(hdr):
        if "문구" in _norm(h) or "프로필" in _norm(h):
            txt_col = j
    if txt_col < 0:
        txt_col = len(hdr) - 1

    rules = []
    for r in g[1:]:
        r = list(r) + [""] * (len(hdr) - len(r))
        text = str(r[txt_col]).strip()
        if not text:
            continue
        cond = {}
        ok = True
        for a, j in col.items():
            raw = str(r[j]).strip()
            if not raw:
                ok = False
                break
            cond[a] = [_fix_level(x) for x in re.split(r"[,/·]", raw) if x.strip()]
        if ok and cond:
            rules.append((cond, text))
    return rules


def pick_summary(levels):
    """내 레벨 조합에 맞는 종합 문구를 고릅니다."""
    try:
        for cond, text in load_summary():
            if all(levels.get(a, "") in cond.get(a, []) for a in AREAS):
                return text
    except Exception:
        pass
    return ""


# ==========================================================
# 🎨 결과지 그리기
# ==========================================================
AX_CSS = """
<style>
.ax-rep { background:#ffffff; border:1px solid #E1E5EA; border-radius:12px;
  overflow:hidden; color:#1B1F24; margin-top:6px;
  font-family:'Noto Sans KR','Malgun Gothic','맑은 고딕',sans-serif; }
.ax-head { background:#12253F; padding:16px 22px; display:flex;
  justify-content:space-between; align-items:flex-start; gap:14px; }
.ax-head .h1 { margin:0; font-size:1.12rem; font-weight:800; color:#ffffff;
  letter-spacing:-.02em; line-height:1.35; }
.ax-head .h2 { margin:5px 0 0; font-size:.76rem; color:#AEBDD0; }
.ax-head .nm { font-size:1.02rem; font-weight:700; color:#ffffff; text-align:right;
  white-space:nowrap; }
.ax-head .sub { font-size:.73rem; color:#AEBDD0; text-align:right; margin-top:4px;
  white-space:nowrap; }
.ax-body { padding:15px 22px 18px; }
.ax-note { font-size:.76rem; color:#6B7480; background:#F5F7F9; border-radius:8px;
  padding:9px 12px; margin:0 0 15px; line-height:1.5; }
.ax-h3 { font-size:1.0rem; font-weight:800; margin:0 0 4px; color:#1B1F24; }
.ax-sum { font-size:.82rem; color:#5B6472; line-height:1.6; margin:0 0 12px; }
.ax-cards { display:flex; gap:9px; margin:0 0 16px; flex-wrap:wrap; }
.ax-card { flex:1 1 200px; border-radius:10px; padding:11px 13px; }
.ax-card .t { font-size:.73rem; color:#5B6472; margin:0 0 8px; font-weight:500; }
.ax-card .row { display:flex; align-items:center; gap:9px; }
.ax-badge { min-width:44px; text-align:center; color:#ffffff; font-weight:800;
  font-size:.85rem; padding:7px 9px; border-radius:8px; }
.ax-card .d { font-size:.75rem; color:#3C4650; line-height:1.4; }
.ax-h2 { font-size:1.05rem; font-weight:800; margin:0 0 9px; color:#1B1F24; }
.ax-blk { border:1px solid #E4E7EB; border-radius:10px; background:#FAFBFC;
  padding:13px 16px; margin:0 0 9px; }
.ax-tag { display:inline-block; font-size:.65rem; font-weight:700; color:#5B6472;
  background:#EBEEF2; padding:3px 9px; border-radius:99px; margin:0 0 6px; }
.ax-two { display:flex; gap:16px; flex-wrap:wrap; }
.ax-l { flex:1 1 320px; min-width:250px; }
.ax-r { flex:0 1 300px; min-width:230px; border-left:1px solid #E4E7EB;
  padding-left:16px; }
.ax-aname { font-size:1.02rem; font-weight:800; margin:0 0 5px; }
.ax-lv { font-size:.82rem; font-weight:700; margin:0; }
.ax-lvd { font-size:.79rem; color:#5B6472; margin:1px 0 9px; }
.ax-lb { font-size:.78rem; font-weight:700; color:#3C4650; margin:0 0 4px; }
.ax-li { font-size:.76rem; color:#3C4650; line-height:1.5; margin:3px 0; }
.ax-li a { color:#2059A8; text-decoration:none; border-bottom:1px solid #BED2EA; }
.ax-li a:hover { color:#12253F; border-bottom-color:#12253F; }
.ax-none { font-size:.76rem; color:#98A1AC; margin:3px 0; }
.ax-foot { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
  border-top:1px solid #E4E7EB; margin-top:12px; padding-top:9px;
  font-size:.68rem; color:#98A1AC; }
@media (max-width: 760px) {
  .ax-r { border-left:0; padding-left:0; border-top:1px solid #E4E7EB; padding-top:10px; }
}
</style>
"""

AX_PRINT_CSS = """
<style>
@media print {
  @page { size: A4; margin: 9mm; }
  body { margin:0; background:#ffffff;
    font-family:'Noto Sans KR','Malgun Gothic','맑은 고딕',sans-serif; }
  .ax-rep { border:0 !important; border-radius:0 !important; margin:0 !important; }
  /* 종이 한 장을 끝까지 채우고 넘어가도록 합니다. (빈 여백 줄이기) */
  .ax-blk { break-inside: auto; page-break-inside: auto; }
  .ax-tag, .ax-aname, .ax-lv, .ax-lvd, .ax-lb {
    break-after: avoid; page-break-after: avoid; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  /* 종이에서도 왼쪽(추천 교육) · 오른쪽(필요 역량) 두 칸을 그대로 지킵니다. */
  .ax-two { display:flex !important; flex-wrap:nowrap !important; gap:12px !important; }
  .ax-l { flex:1 1 62% !important; min-width:0 !important; }
  .ax-r { flex:0 0 34% !important; min-width:0 !important; border-top:0 !important;
    padding-top:0 !important; border-left:1px solid #E4E7EB !important;
    padding-left:12px !important; }
  .ax-cards { flex-wrap:nowrap !important; margin-bottom:11px !important; }
  .ax-card { min-width:0 !important; padding:9px 11px !important; }
  /* 종이에서는 여백과 글자를 조금 줄여 한 장에 담기도록 합니다. */
  .ax-head { padding:12px 16px !important; }
  .ax-body { padding:11px 16px 12px !important; }
  .ax-note { padding:7px 10px !important; margin-bottom:11px !important;
    font-size:.72rem !important; }
  .ax-sum { margin-bottom:10px !important; font-size:.78rem !important; }
  .ax-blk { padding:9px 13px !important; margin-bottom:6px !important; }
  .ax-aname { font-size:.95rem !important; margin-bottom:3px !important; }
  .ax-lvd { margin-bottom:6px !important; font-size:.75rem !important; }
  .ax-li { font-size:.71rem !important; line-height:1.42 !important;
    margin:2px 0 !important; }
  .ax-none { font-size:.71rem !important; }
  .ax-tag { margin-bottom:3px !important; }
  .ax-foot { margin-top:9px !important; padding-top:7px !important; }
}
</style>
"""


def _lv_color(level):
    return LEVEL_COLOR.get(level, ("#6B7480", "#EEF0F3"))


def _course_html(level, area, courses):
    items = courses.get((level, area), [])
    if not items:
        return "<div class='ax-none'>• 이 수준에서는 별도 추천 교육이 없습니다.</div>"
    out = []
    for title, link in items:
        if link:
            out.append("<div class='ax-li'>• <a href=\"%s\" target=\"_blank\" "
                       "rel=\"noopener\">%s</a></div>"
                       % (_ax_esc(link), _ax_esc(title)))
        else:
            out.append("<div class='ax-li'>• %s</div>" % _ax_esc(title))
    return "".join(out)


def build_report_html(person):
    """결과지 본문(HTML)을 만듭니다."""
    level_def = load_level_def()
    need = load_need()
    courses = load_courses()

    levels = person["levels"]
    name = person["name"]
    pos = person.get("position", "")
    gubun = person.get("gubun", "")
    team = person.get("team", "")

    who_r = " | ".join([x for x in (gubun, pos) if x]) or "-"
    if team:
        who_r = "%s | %s" % (who_r, team)

    # ----- 머리말 -----
    head = ("<div class='ax-head'>"
            "<div><div class='h1'>%s</div><div class='h2'>%s</div></div>"
            "<div><div class='nm'>%s %s</div><div class='sub'>%s</div></div>"
            "</div>"
            % (_ax_esc(AX_TITLE), _ax_esc(AX_SUBTITLE),
               _ax_esc(name), _ax_esc(pos), _ax_esc(who_r)))

    # ----- 역량 프로필 (3칸 요약) -----
    cards = []
    for a in AREAS:
        lv = levels.get(a, "")
        fg, bg = _lv_color(lv)
        cards.append(
            "<div class='ax-card' style='background:%s'>"
            "<div class='t'>%s</div>"
            "<div class='row'><div class='ax-badge' style='background:%s'>%s</div>"
            "<div class='d'>%s</div></div></div>"
            % (bg, _ax_esc(a), fg, _ax_esc(lv or "-"),
               _ax_esc(level_def.get((lv, a), "-"))))

    summary = pick_summary(levels)
    sum_html = _ax_esc(summary).replace("\n", "<br>") if summary else ""

    # ----- 영역별 결과와 추천 학습 -----
    blocks = []
    for i, a in enumerate(AREAS, start=1):
        lv = levels.get(a, "")
        fg, _bg = _lv_color(lv)
        needs = need.get((lv, a), [])
        need_html = ("".join("<div class='ax-li'>• %s</div>" % _ax_esc(x) for x in needs)
                     or "<div class='ax-none'>• 등록된 내용이 없습니다.</div>")
        blocks.append(
            "<div class='ax-blk'>"
            "<div class='ax-tag'>영역 %d</div>"
            "<div class='ax-two'>"
            "<div class='ax-l'>"
            "<div class='ax-aname'>%s</div>"
            "<div class='ax-lv' style='color:%s'>현재 수준 &nbsp;%s</div>"
            "<div class='ax-lvd'>%s</div>"
            "<div class='ax-lb' style='color:%s'>추천 교육</div>%s"
            "</div>"
            "<div class='ax-r'>"
            "<div class='ax-lb'>현재 필요한 역량</div>%s"
            "</div></div></div>"
            % (i, _ax_esc(a), fg, _ax_esc(lv or "-"),
               _ax_esc(level_def.get((lv, a), "-")), fg,
               _course_html(lv, a, courses), need_html))

    body = ("<div class='ax-body'>"
            "<div class='ax-note'>%s</div>"
            "<div class='ax-h3'>%s님의 AX 역량 프로필</div>"
            "<div class='ax-sum'>%s</div>"
            "<div class='ax-cards'>%s</div>"
            "<div class='ax-h2'>영역별 결과와 추천 학습</div>"
            "%s"
            "<div class='ax-foot'><div>%s</div><div>%s</div></div>"
            "</div>"
            % (_ax_esc(AX_NOTE), _ax_esc(name), sum_html, "".join(cards),
               "".join(blocks), _ax_esc(AX_FOOT_L), _ax_esc(AX_FOOT_R)))

    return "<div class='ax-rep'>%s%s</div>" % (head, body)


def build_print_doc(person, report_html):
    """인쇄·PDF 저장용 '한 장짜리 파일'을 만듭니다."""
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>%s_%s_AX역량진단 결과</title>%s%s</head><body>%s</body></html>"
            % (_ax_esc(person.get("saban", "")), _ax_esc(person.get("name", "")),
               AX_CSS, AX_PRINT_CSS, report_html))


def _print_button_html(doc_html):
    """[인쇄 / PDF로 저장] 단추. 눌리면 결과지만 따로 띄워 인쇄창을 엽니다."""
    payload = json.dumps(doc_html)
    return """
    <html><head><style>
      body { margin:0; font-family:'Noto Sans KR',sans-serif; }
      .pb { width:100%%; padding:11px 10px; font-size:.92rem; font-weight:700;
            color:#fff; background:#12253F; border:0; border-radius:9px;
            cursor:pointer; }
      .pb:hover { background:#1D3A62; }
    </style></head><body>
      <button class="pb" onclick="axPrint()">🖨️ 인쇄 / PDF로 저장</button>
      <script>
        const AX_DOC = %s;
        function axPrint() {
            try {
                const w = window.open('', '_blank');
                if (w && w.document) {
                    w.document.open();
                    w.document.write(AX_DOC);
                    w.document.close();
                    w.focus();
                    setTimeout(function () { try { w.print(); } catch (e) {} }, 600);
                    return;
                }
            } catch (e) {}
            // 새 창이 막혔을 때 : 이 자리에 결과지를 펼쳐서 인쇄합니다.
            try {
                document.open();
                document.write(AX_DOC);
                document.close();
                setTimeout(function () { window.print(); }, 600);
            } catch (e) {
                alert('브라우저가 인쇄창을 막았습니다. 아래 [결과지 파일 저장] 을 눌러 주세요.');
            }
        }
      </script>
    </body></html>
    """ % payload


# ==========================================================
# 화면
# ==========================================================
def run_ax_report():
    """바깥 껍데기 : 구글 시트가 잠깐 말썽이어도 앱이 죽지 않게 합니다."""
    try:
        _run_ax_report()
    except AxError as e:
        st.markdown("### 📄 AX 역량진단 결과 리포트")
        st.error(str(e))
        if st.button("🔄 다시 시도", key="ax_retry0", type="primary"):
            _reset_ax()
            st.rerun()
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        st.markdown("### 📄 AX 역량진단 결과 리포트")
        if code in (429, 500, 502, 503) or isinstance(e, AxBusy):
            st.warning("⏳ 구글 시트가 잠시 응답하지 않고 있습니다. "
                       "**5~10초 뒤 아래 [다시 시도] 버튼을 눌러 주세요.**")
        elif code == 403:
            st.error("구글 시트 접근 권한이 없습니다. `%s` 파일을 "
                     "서비스 계정 이메일에 **뷰어 이상**으로 공유해 주세요." % AX_DB)
        else:
            st.error("자료를 불러오는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
            st.caption("자세한 내용 : %s" % str(e)[:200])
        if st.button("🔄 다시 시도", key="ax_retry", type="primary"):
            _reset_ax()
            st.rerun()


def _run_ax_report():
    st.markdown(AX_CSS, unsafe_allow_html=True)
    st.header("📄 AX 역량진단 결과 리포트")
    st.caption("나의 현재 위치를 확인하고, 다음 성장을 설계합니다.")
    st.markdown("---")

    if "ax_user" not in st.session_state:
        st.session_state.ax_user = None

    # ---------- 로그인 ----------
    if not st.session_state.ax_user:
        st.subheader("🔒 본인 확인")
        st.caption("사번과 이름을 입력해 주세요. 본인 결과만 볼 수 있습니다.")
        with st.form("ax_login", clear_on_submit=False):
            c1, c2 = st.columns(2)
            in_saban = c1.text_input("사번", placeholder="사번 입력")
            in_name = c2.text_input("이름", placeholder="이름 입력")
            go = st.form_submit_button("결과 보기", type="primary",
                                       use_container_width=True)
        if go:
            if not str(in_saban).strip() or not str(in_name).strip():
                st.warning("사번과 이름을 모두 입력해 주세요.")
            else:
                with st.spinner("진단 결과를 찾는 중입니다..."):
                    who = find_ax_person(in_saban, in_name)
                if who:
                    st.session_state.ax_user = who
                    st.rerun()
                else:
                    st.error("사번 또는 이름이 진단 자료와 맞지 않습니다. "
                             "다시 확인해 주시고, 계속 안 되면 인사총무팀에 문의해 주세요.")
        return

    person = st.session_state.ax_user

    # ---------- 결과지 ----------
    report_html = build_report_html(person)
    doc_html = build_print_doc(person, report_html)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    with c1:
        components.html(_print_button_html(doc_html), height=56)
    with c2:
        st.download_button(
            "📥 결과지 파일 저장",
            data=doc_html.encode("utf-8"),
            file_name="AX역량진단_%s_%s.html" % (person.get("saban", ""),
                                             person.get("name", "")),
            mime="text/html",
            use_container_width=True,
            key="ax_dl")
    with c3:
        if st.button("로그아웃", key="ax_logout", use_container_width=True):
            st.session_state.ax_user = None
            st.rerun()

    st.markdown(report_html, unsafe_allow_html=True)

    st.markdown("")
    st.caption("🖨️ [인쇄 / PDF로 저장] 을 누르면 인쇄창이 열립니다. "
               "**인쇄 대상을 'PDF로 저장'** 으로 바꾸면 PDF 파일로 남길 수 있습니다. "
               "새 창이 뜨지 않으면 브라우저 주소창 오른쪽의 팝업 차단을 풀어 주세요.")
