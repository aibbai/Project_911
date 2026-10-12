"""
서울 응급의료 허브 v2 - 웹 공개용 서버 (v1 단축판, 기능·API 응답 동일)
- 23개 구: NMC 실시간 응급실 가용병상 / 강북·마포: 정적 병상 수 + 인접 구 안내
- templates/base.html 을 main·real_time·predict.html 이 상속
"""
import os, re, json, time, shutil, threading, webbrowser, unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request, render_template, send_from_directory, abort
from jinja2 import BaseLoader, TemplateNotFound
from dotenv import load_dotenv

# py 실행: 파일 폴더 / 노트북 실행: 현재 폴더
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
app = Flask(__name__, static_folder=None, root_path=BASE_DIR)   # static 은 아래 static_files()에서 직접 찾음
app.json.ensure_ascii = False


# ------------------------------------------------------------
# 1. 환경변수
# ------------------------------------------------------------
def env(name, default=""):
    return os.getenv(name, str(default)).strip()

def env_bool(name, default):
    return env(name, default).lower() in {"1", "true", "yes", "y", "on"}

DATA_GO_KR_KEY = env("DATA_GO_KR_KEY") or env("DATA_GO_KR_SERVICE_KEY")
HOST = env("APP_HOST", "0.0.0.0")                       # 0.0.0.0 = 외부 접속 허용
PORT = int(env("PORT") or env("APP_PORT", 5000))        # 클라우드는 PORT 자동 지정
AUTO_OPEN_BROWSER = env_bool("AUTO_OPEN_BROWSER", False)
ADMIN_TOKEN = env("ADMIN_TOKEN")
ON_VERCEL = bool(env("VERCEL"))                          # Vercel 서버에서 자동으로 1
START_SCHEDULER = env_bool("START_SCHEDULER", not ON_VERCEL)   # Vercel: 스케줄러 없음
REFRESH_ON_REQUEST = env_bool("REFRESH_ON_REQUEST", ON_VERCEL)   # Vercel: 스케줄러 대신 요청 시 갱신
CHATBOT_ON = env_bool("CHATBOT", not ON_VERCEL)          # Vercel: 챗봇 끔
AUTO_REFRESH_MINUTES = int(env("AUTO_REFRESH_MINUTES", 60))
STALE_HOURS = int(env("STALE_HOURS", 24))
FULL_REFRESH_LIMIT = int(env("FULL_REFRESH_LIMIT", 3))
DAILY_LIMIT = int(env("DAILY_API_LIMIT", 100))
API_CACHE_SECONDS = 60 * 60
SNAPSHOT_SCHEMA = 1

DATA_DIR = env("DATA_DIR") or ("/tmp/hub" if ON_VERCEL else BASE_DIR)   # Vercel: /tmp 만 쓰기 가능
os.makedirs(DATA_DIR, exist_ok=True)
SNAPSHOT_FILE, REFRESH_STATE_FILE, API_USAGE_FILE = [
    os.path.join(DATA_DIR, f) for f in ("realtime_beds_cache.json", "refresh_state.json", "api_usage.json")]

# 저장 폴더가 따로면: 함께 올린 캐시를 첫 화면용으로 복사
_seed = os.path.join(BASE_DIR, "realtime_beds_cache.json")
if DATA_DIR != BASE_DIR and not os.path.isfile(SNAPSHOT_FILE) and os.path.isfile(_seed):
    shutil.copy(_seed, SNAPSHOT_FILE)

NIA_URL = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"
BED_SOURCE = "NMC 실시간 병상 API (23개 구) + 강북·마포 정적 응급실 병상"


# ------------------------------------------------------------
# 2. 파일 찾기 · 화면 렌더링
# ------------------------------------------------------------
SEARCH_ROOTS = [BASE_DIR] if ON_VERCEL else [BASE_DIR, os.path.dirname(BASE_DIR)]   # Vercel: 상위 폴더 검색 안 함
SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", ".ipynb_checkpoints"}

def loose_name(x):
    """파일명 비교용: 자모·대소문자·' (1)'·'- 복사본'·중복 확장자 무시"""
    x = unicodedata.normalize("NFC", str(x)).strip().lower()
    x = re.sub(r"(\.(?:txt|html?|css|js))\1+$", r"\1", x)      # a.html.html → a.html
    x = re.sub(r"\.html\.txt$", ".html", x)                      # a.html.txt  → a.html
    return re.sub(r"\s*(\(\d+\)|-\s*복사본)(?=\.[a-z]+$)", "", x)  # a (1).html  → a.html

def walk_files(max_depth=3):
    for root in SEARCH_ROOTS:
        for folder, dirs, files in os.walk(root):
            too_deep = folder[len(root):].count(os.sep) >= max_depth
            dirs[:] = [] if too_deep else [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                yield os.path.join(folder, f)

def find_file(*names, subfolders=("templates", "data", "")):
    """1) 정해진 폴더에서 정확한 이름 → 2) 하위 폴더에서 비슷한 이름 (없으면 None)"""
    names = [n.strip() for n in names if n and n.strip()]
    exact = (os.path.join(r, s, n) for r in SEARCH_ROOTS for s in subfolders for n in names)
    found = next((p for p in exact if os.path.isfile(p)), None)
    if found:
        return found
    targets = {loose_name(n) for n in names}
    return next((p for p in walk_files() if loose_name(os.path.basename(p)) in targets), None)

def first_existing(names):
    return next((n for n in names if find_file(n)), None)

def html_candidates():
    return sorted({p for p in walk_files() if p.lower().endswith((".html", ".htm", ".html.txt"))})[:30]

# 화면 파일 순서: .env 지정 → base.html 상속 템플릿 → 예전 단독 HTML
def page_names(env_name, *defaults):
    return tuple(n for n in (env(env_name), *defaults) if n)

HOME_NAMES = page_names("HOME_FILE", "main.html", "SEOUL_EMERGENCY_HUB.html")
BEDS_NAMES = page_names("BEDS_FILE", "real_time.html", "실시간_병상관제_v1.html")
ANALYSIS_NAMES = page_names("ANALYSIS_FILE", "predict.html", "데이터분석_예측.html")
SHARED_TEMPLATES = ("base.html", "header.html", "footer.html")
DASHBOARD_NAMES = ("dashboard_data.json", "dashboard_data.js")   # 예측 노트북 결과 (json 우선)

class FindFileLoader(BaseLoader):
    """{% extends %}·{% include %} 도 find_file()로 찾는 로더 (html 수정 시 자동 반영)"""
    def get_source(self, environment, template):
        path = find_file(template)
        if not path:
            raise TemplateNotFound(template)
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), path, lambda: os.path.isfile(path) and os.path.getmtime(path) == mtime

app.jinja_env.loader = FindFileLoader()
app.jinja_env.auto_reload = True
app.jinja_env.globals["chatbot_enabled"] = CHATBOT_ON   # base.html 챗봇 창 표시 여부

@app.get("/static/<path:filename>", endpoint="static")
def static_files(filename):
    path = find_file(filename, os.path.basename(filename),
                     subfolders=("static", "static/css", "static/js", "public/static",
                                 "public/static/css", "public/static/js", "outputs", ""))
    if not path:
        abort(404)
    return send_from_directory(*os.path.split(path))

def serve_html(names):
    name = first_existing(names)
    if name is None:
        return jsonify(error="HTML 파일 없음", 찾은_파일명=list(names), 검색한_폴더=SEARCH_ROOTS,
                       실제_있는_html=html_candidates()), 404
    try:
        return render_template(name)
    except TemplateNotFound as e:   # base·header·footer 가 없는 경우
        return jsonify(error="공통 템플릿 파일 없음", 화면_파일=name, 없는_파일=e.name,
                       필요한_파일=list(SHARED_TEMPLATES), 실제_있는_html=html_candidates()), 500

def find_dashboard_file():
    custom = env("DASHBOARD_FILE")
    if custom:
        return custom if os.path.isfile(custom) else None
    paths = (find_file(n, subfolders=("outputs", "static", "data", "")) for n in DASHBOARD_NAMES)
    return next((p for p in paths if p), None)

def load_dashboard_data():
    """json 은 그대로, js 는 'const DASHBOARD_DATA = {...};' 의 { } 부분만"""
    path = find_dashboard_file()
    if not path:
        return None, None
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    if path.lower().endswith(".js"):
        text = text[text.index("{"): text.rindex("}") + 1]
    return json.loads(text), path


# ------------------------------------------------------------
# 3. 자치구 정보
# ------------------------------------------------------------
ZONES = {
    "도심권": "종로구 중구 용산구",
    "동북권": "성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 노원구",
    "서북권": "은평구 서대문구 마포구",
    "서남권": "양천구 강서구 구로구 금천구 영등포구 동작구 관악구",
    "동남권": "서초구 강남구 송파구 강동구",
}
ZONE_OF = {gu: zone for zone, gus in ZONES.items() for gu in gus.split()}
SEOUL_GU_LIST = list(ZONE_OF)
VALID_GU = set(SEOUL_GU_LIST)

# 실시간 API 미제공 자치구 (병원명, 응급실 병상 수)
STATIC_ER_HOSPITALS = {
    "강북구": [("의료법인성화의료재단 대한병원", 7), ("서울현대병원", 7), ("강북으뜸병원", 3)],
    "마포구": [("신촌연세병원", 6)],
}
STATIC_ER_GU = set(STATIC_ER_HOSPITALS)
REALTIME_GU_LIST = [gu for gu in SEOUL_GU_LIST if gu not in STATIC_ER_GU]

# 맞닿은 자치구 (가까운 순) - 없으면 같은 권역 사용
NEIGHBOR_GU = {"마포구": ["서대문구", "은평구", "용산구", "영등포구", "강서구"],
               "강북구": ["성북구", "도봉구", "노원구"]}
NEARBY_PER_GU = 2


# ------------------------------------------------------------
# 4. 한국시간 · json 파일 도구
# ------------------------------------------------------------
KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST).replace(tzinfo=None)   # 클라우드(UTC)에서도 한국시간

def today_key():
    return now_kst().strftime("%Y-%m-%d")

def seconds_since(iso_text):
    try:
        return max(0, int((now_kst() - datetime.fromisoformat(iso_text)).total_seconds()))
    except (TypeError, ValueError):
        return None

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data):
    with open(path + ".tmp", "w", encoding="utf-8") as f:   # 임시 파일 → 교체 (읽는 중 깨짐 방지)
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)

def daily_state(path, empty):
    """오늘 날짜 파일이면 그대로, 아니면 초기값"""
    data = read_json(path, {})
    return data if data.get("date") == today_key() else {"date": today_key(), **empty}


# ------------------------------------------------------------
# 5. 일일 API 호출 횟수 관리 · 재시도 요청
# ------------------------------------------------------------
class RateLimitExhausted(Exception):
    pass

_usage_lock = threading.Lock()

def api_usage_status():
    with _usage_lock:
        data = daily_state(API_USAGE_FILE, {"counts": {}})
    used = int(data.get("counts", {}).get("data_go_kr", 0))
    return {"date": data["date"],
            "data_go_kr": {"used": used, "limit": DAILY_LIMIT, "remaining": max(0, DAILY_LIMIT - used)}}

def reserve_api_call():
    with _usage_lock:
        data = daily_state(API_USAGE_FILE, {"counts": {}})
        counts = data.setdefault("counts", {})
        used = int(counts.get("data_go_kr", 0))
        if used >= DAILY_LIMIT:
            raise RateLimitExhausted(f"data_go_kr 일일 호출 제한 {DAILY_LIMIT}회 소진")
        counts["data_go_kr"] = used + 1
        write_json(API_USAGE_FILE, data)
        return used + 1

def get_with_retry(url, params, retries=3, delay=1.5):
    """429·5xx·연결 오류 → 대기 후 재시도 (1.5초 → 3초 → 6초)"""
    status = None
    for i in range(retries):
        wait, last = delay * 2 ** i, i == retries - 1
        try:
            print(f"[API] {reserve_api_call()}/{DAILY_LIMIT} {url.rsplit('/', 1)[-1]}")
            r = requests.get(url, params=params, timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            if last:
                raise
            time.sleep(wait)
            continue
        if r.status_code == 200:
            return r
        status = r.status_code
        if status != 429 and status < 500:
            r.raise_for_status()
        if not last:
            time.sleep(float(r.headers.get("Retry-After", wait)))
    if status == 429:
        raise RateLimitExhausted("API 호출 한도 초과 (HTTP 429)")
    raise RuntimeError(f"API 요청 실패 (HTTP {status})")


# ------------------------------------------------------------
# 6. NMC 실시간 병상 수집
# ------------------------------------------------------------
def parse_xml_items(xml_text):
    root = ET.fromstring(xml_text)
    for code_tag, msg_tag in (("returnReasonCode", "returnAuthMsg"), ("resultCode", "resultMsg")):
        code = root.findtext(f".//{code_tag}")
        if code not in (None, "00"):
            msg = root.findtext(f".//{msg_tag}") or ""
            if code == "22" or "LIMITED" in msg.upper():
                raise RateLimitExhausted(msg)
            raise RuntimeError(f"API 오류 {code}: {msg}")
    return [{c.tag: c.text for c in item} for item in root.findall(".//item")]

def parse_updated_at(value):
    digits = re.sub(r"\D", "", str(value or ""))
    for fmt, n in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(digits) >= n:
            try:
                return datetime.strptime(digits[:n], fmt)
            except ValueError:
                pass
    return None

def to_hospital(x, gu):
    """API 한 줄 → 병원 정보 (음수 병상 = 과밀 → 0 / 오래된 값 → 미확인)"""
    try:
        raw = int(float(x.get("hvec")))
    except (TypeError, ValueError):
        raw = None
    updated = parse_updated_at(x.get("hvidate"))
    stale = updated is None or now_kst() - updated > timedelta(hours=STALE_HOURS)
    beds = None if stale or raw is None else max(0, raw)
    return {"Hospital_ID": x.get("hpid"), "Hospital_Name": x.get("dutyName"), "Tel": x.get("dutyTel3"),
            "Updated_At": x.get("hvidate"), "Ambulance_Available": x.get("hvamyn"), "District": gu,
            "data_source": "existing_realtime_API", "Available_Beds": beds,
            "Beds_Raw": x.get("hvec") if raw is None else raw,
            "Is_Overcrowded": raw is not None and raw < 0, "Is_Stale": stale, "Beds_Unknown": beds is None}

def fetch_nia_realtime(gu):
    params = {"serviceKey": DATA_GO_KR_KEY, "STAGE1": "서울특별시", "STAGE2": gu, "pageNo": 1, "numOfRows": 100}
    return [to_hospital(x, gu) for x in parse_xml_items(get_with_retry(NIA_URL, params).text)]


# ------------------------------------------------------------
# 7. 전체 갱신 (스케줄러 또는 관리자만 실행)
# ------------------------------------------------------------
_snapshot_lock = threading.Lock()
_snap_mem = {"mtime": None, "data": {}}

def load_snapshot():
    """캐시 파일이 바뀌었을 때만 다시 읽기"""
    try:
        mtime = os.path.getmtime(SNAPSHOT_FILE)
    except OSError:
        return {}
    if _snap_mem["mtime"] != mtime:
        data = read_json(SNAPSHOT_FILE, {})
        _snap_mem.update(mtime=mtime, data=data if isinstance(data, dict) else {})
    return _snap_mem["data"]

def refresh_state():
    return daily_state(REFRESH_STATE_FILE, {"full_refresh_count": 0, "last_refresh": None})

def can_full_refresh():
    state = refresh_state()
    passed = seconds_since(state.get("last_refresh"))
    if not DATA_GO_KR_KEY:
        return False, "DATA_GO_KR_KEY 없음"
    if state["full_refresh_count"] >= FULL_REFRESH_LIMIT:
        return False, "오늘 전체 갱신 횟수 소진"
    if passed is not None and passed < API_CACHE_SECONDS:
        return False, f"다음 갱신까지 {(API_CACHE_SECONDS - passed) // 60 + 1}분"
    if api_usage_status()["data_go_kr"]["remaining"] < len(REALTIME_GU_LIST):
        return False, "공공데이터포털 일일 잔여 호출 부족"
    return True, None

def refresh_all_districts(force=False):
    with _snapshot_lock:
        old = load_snapshot()
        ok, reason = can_full_refresh()
        if not (ok or force):
            return old, False, reason

        old_districts = old.get("districts", {}) if old.get("schema") == SNAPSHOT_SCHEMA else {}
        payloads, errors = {}, []
        for gu in REALTIME_GU_LIST:
            try:
                payloads[gu] = {"district": gu, "hospitals": fetch_nia_realtime(gu)}
            except Exception as e:   # 실패한 구는 이전 캐시 유지
                errors.append(f"{gu}: {e}")
                payloads[gu] = {**old_districts.get(gu, {"district": gu, "hospitals": []}), "cache_stale": True}
        payloads.update({gu: {"district": gu, "hospitals": []} for gu in STATIC_ER_GU})

        counts = [len(payloads[gu]["hospitals"]) for gu in REALTIME_GU_LIST]
        snapshot = {
            "schema": SNAPSHOT_SCHEMA, "updated_at": now_kst().isoformat(timespec="seconds"),
            "source": BED_SOURCE, "districts": payloads, "errors": errors,
            "stats": {"realtime_district_count": len(REALTIME_GU_LIST),
                      "static_er_districts": sorted(STATIC_ER_GU),
                      "empty_realtime_districts": [g for g, n in zip(REALTIME_GU_LIST, counts) if n == 0],
                      "max_district_count": max(counts, default=0)},
        }
        write_json(SNAPSHOT_FILE, snapshot)

        state = refresh_state()
        state["full_refresh_count"] += 1
        state["last_refresh"] = snapshot["updated_at"]
        write_json(REFRESH_STATE_FILE, state)
        return snapshot, True, None

_request_lock = threading.Lock()

def refresh_if_old():
    """스케줄러가 없을 때: 캐시가 오래됐으면 이 요청에서 갱신 (동시에 1번만)"""
    if not REFRESH_ON_REQUEST or AUTO_REFRESH_MINUTES <= 0:
        return
    age = seconds_since(load_snapshot().get("updated_at"))
    if age is not None and age < AUTO_REFRESH_MINUTES * 60:
        return
    if not _request_lock.acquire(blocking=False):
        return   # 다른 요청이 갱신 중 → 기존 캐시로 응답
    try:
        _, refreshed, reason = refresh_all_districts()
        print(f"[REQUEST] {'갱신 완료' if refreshed else '건너뜀: ' + str(reason)}")
    except Exception as e:
        print(f"[REQUEST] 갱신 오류: {e}")
    finally:
        _request_lock.release()


# ------------------------------------------------------------
# 8. 자치구별 응답 (강북·마포 인접 구 안내 포함)
# ------------------------------------------------------------
def build_nearby(snapshot, gu):
    """가까운 구 순서로, 구마다 가용 병상 많은 병원 2곳씩"""
    near_list = NEIGHBOR_GU.get(gu) or [g for g in SEOUL_GU_LIST if ZONE_OF[g] == ZONE_OF[gu] and g != gu]
    nearby = []
    for near in near_list:
        hs = [dict(h, From_District=near) for h in snapshot.get("districts", {}).get(near, {}).get("hospitals", [])]
        hs.sort(key=lambda h: (h.get("Available_Beds") is None, -(h.get("Available_Beds") or 0)))
        nearby += hs[:NEARBY_PER_GU]
    return nearby

def district_payload(snapshot, gu):
    if gu in STATIC_ER_GU:   # 강북·마포: 등록 병상 수 + 인접 구 실시간
        return {"district": gu, "data_type": "static_er_beds", "realtime_available": False,
                "hospitals": [{"Hospital_Name": n, "ER_Beds": b, "District": gu, "data_source": "static_er_beds"}
                              for n, b in STATIC_ER_HOSPITALS[gu]],
                "notice": "실시간 가용병상 정보가 제공되지 않아 등록 응급실 병상 수를 표시합니다.",
                "nearby_notice": "인접 자치구의 실시간 가용병상 정보입니다.",
                "nearby_hospitals": build_nearby(snapshot, gu)}

    payload = {"district": gu, "hospitals": [], **snapshot.get("districts", {}).get(gu, {}),
               "data_type": "realtime", "realtime_available": True, "nearby_hospitals": [], "notice": None}
    if not snapshot:
        payload["error"] = "병상 데이터를 준비 중입니다. 잠시 후 새로고침하세요."
    elif not payload["hospitals"]:
        payload.update(notice=f"{gu} 병상 정보가 없어 인접 자치구 병원을 안내합니다.",
                       nearby_hospitals=build_nearby(snapshot, gu))
    return payload


# ------------------------------------------------------------
# 9. 웹 경로 (방문자는 저장된 캐시만 읽음)
# ------------------------------------------------------------
@app.get("/")
def index():
    return serve_html(HOME_NAMES)

@app.get("/analysis")
def analysis_page():
    return serve_html(ANALYSIS_NAMES)

@app.get("/beds")
def beds_page():
    return serve_html(BEDS_NAMES)

@app.get("/api/dashboard-data")
def dashboard_data():
    """요청마다 파일을 다시 읽음 → 노트북 재실행 시 바로 반영"""
    try:
        data, _ = load_dashboard_data()
    except (ValueError, OSError) as e:
        return jsonify(error=f"대시보드 데이터 파일을 읽지 못했습니다: {e}"), 500
    if data is None:
        return jsonify(error="dashboard_data.json 파일이 없습니다. 예측 노트북을 실행한 뒤 "
                             "outputs 폴더째 이 서버 폴더에 두세요.",
                       찾은_파일명=list(DASHBOARD_NAMES), 검색한_폴더=SEARCH_ROOTS), 404
    # jsonify 는 키를 정렬함 → 파일 순서 유지를 위해 json.dumps 사용
    res = app.response_class(json.dumps(data, ensure_ascii=False), mimetype="application/json")
    res.headers["Cache-Control"] = "no-store"
    return res

@app.get("/api/realtime-beds")
def realtime_beds():
    gu = request.args.get("district", "강남구").strip()
    if gu not in VALID_GU:
        return jsonify(error="서울시 자치구 이름이 올바르지 않습니다."), 400
    refresh_if_old()
    snapshot = load_snapshot()
    return jsonify({**district_payload(snapshot, gu), "snapshot_updated_at": snapshot.get("updated_at")})

@app.get("/api/realtime-beds/all")
def realtime_beds_all():
    refresh_if_old()
    snapshot = load_snapshot()   # 25개 구를 한 번에 → 브라우저 요청 1회
    return jsonify(snapshot_updated_at=snapshot.get("updated_at"),
                   snapshot_age_seconds=seconds_since(snapshot.get("updated_at")),
                   districts=[district_payload(snapshot, gu) for gu in SEOUL_GU_LIST])

@app.post("/api/refresh")
def manual_refresh():
    token = request.headers.get("X-Admin-Token") or request.args.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return jsonify(error="관리자만 갱신할 수 있습니다."), 403
    snapshot, refreshed, reason = refresh_all_districts()
    return jsonify(refreshed=refreshed, reason=reason, updated_at=snapshot.get("updated_at"),
                   api_usage=api_usage_status())

@app.get("/api/status")
def status():
    snap = load_snapshot()
    return jsonify(bed_source=BED_SOURCE, data_go_kr=bool(DATA_GO_KR_KEY),
                   static_er_districts=sorted(STATIC_ER_GU), snapshot_stats=snap.get("stats"),
                   snapshot_updated_at=snap.get("updated_at"),
                   snapshot_age_seconds=seconds_since(snap.get("updated_at")),
                   cached_districts=len(snap.get("districts", {})), api_usage=api_usage_status(),
                   refresh_state=refresh_state(), full_refresh_limit=FULL_REFRESH_LIMIT,
                   auto_refresh_minutes=AUTO_REFRESH_MINUTES, dashboard_file=find_dashboard_file())

@app.get("/healthz")
def healthz():
    return "ok"


# ------------------------------------------------------------
# 10. 자동 갱신 스케줄러 (1분마다 확인, 서버당 1개)
# ------------------------------------------------------------
def _auto_refresh_loop():
    last_reason = None
    time.sleep(3)
    while True:
        try:
            age = seconds_since(load_snapshot().get("updated_at"))
            if age is None or age >= AUTO_REFRESH_MINUTES * 60:
                _, refreshed, reason = refresh_all_districts()
                if refreshed:
                    print(f"[AUTO] 갱신 완료 {now_kst():%H:%M}")
                elif reason != last_reason:
                    print(f"[AUTO] 건너뜀: {reason}")
                last_reason = reason
        except Exception as e:
            print(f"[AUTO] 오류: {e}")
        time.sleep(60)

# import 시점에 시작 (gunicorn 대응) / 노트북 셀 재실행 시 중복 방지
if START_SCHEDULER and AUTO_REFRESH_MINUTES > 0 and not globals().get("_scheduler_started"):
    _scheduler_started = True
    threading.Thread(target=_auto_refresh_loop, daemon=True).start()


# ------------------------------------------------------------
# 11. 챗봇 연결 (chatbot_exaone.py 가 같은 폴더에 있어야 함, Vercel 에서는 끔)
# ------------------------------------------------------------
if CHATBOT_ON:
    try:
        from chatbot_exaone import init_chatbot
        init_chatbot(app)
    except ImportError as e:
        CHATBOT_ON = app.jinja_env.globals["chatbot_enabled"] = False
        print(f"[CHATBOT] 연결 안 함: {e}")


# ------------------------------------------------------------
# 12. 서버 실행
# ------------------------------------------------------------
def print_startup():
    usage = api_usage_status()["data_go_kr"]
    print("=" * 58 + "\nSEOUL EMERGENCY HUB V2 - WEB SERVER\n" + "=" * 58)
    print(f"[KEY]       {'OK' if DATA_GO_KR_KEY else 'DATA_GO_KR_KEY 없음 → 갱신 불가'}")
    print(f"[ADMIN]     {'ON' if ADMIN_TOKEN else 'OFF (ADMIN_TOKEN 없음)'}")
    pages = [("HOME", HOME_NAMES), ("BEDS", BEDS_NAMES), ("ANALYSIS", ANALYSIS_NAMES)]
    missing = False
    for label, names in pages + [("COMMON", (n,)) for n in SHARED_TEMPLATES]:
        name = first_existing(names)
        print(f"[{label:9}] {find_file(name) if name else '없음 ' + names[0]}")
        missing |= name is None and label != "ANALYSIS"
    if missing:
        print("[안내] 실제로 있는 html 파일:", *html_candidates(), sep="\n    ")
    print(f"[DASHBOARD] {find_dashboard_file() or '없음 → 분석 페이지에 안내 문구 표시'}")
    print(f"[LIMIT]     {usage['used']}/{usage['limit']} 사용")
    print(f"[SNAPSHOT]  {load_snapshot().get('updated_at') or '없음 → 자동 수집 시작'}")
    print(f"[START]     http://{'127.0.0.1' if HOST == '0.0.0.0' else HOST}:{PORT}/")

def run_server():
    print_startup()
    if AUTO_OPEN_BROWSER:
        threading.Timer(1.5, webbrowser.open_new, [f"http://127.0.0.1:{PORT}/"]).start()
    try:
        from waitress import serve   # 동시 접속에 안정적인 서버
        print("[SERVER]    waitress")
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("[SERVER]    flask 개발 서버 (pip install waitress 권장)")
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_server()
