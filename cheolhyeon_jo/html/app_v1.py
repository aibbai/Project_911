"""
서울 응급의료 허브 v1 - 웹 공개용 서버

데이터 구조
- 일반 23개 구: 공공데이터포털 NMC 실시간 응급실 가용병상
- 강북구·마포구: 실시간 가용병상 API 미제공 예외 UI용 정적 응급실 병상 수
- 강북구·마포구에는 인접 자치구의 실시간 가용병상도 함께 안내
"""
import os
import json
import re
import time
import threading
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

app = Flask(__name__)
app.json.ensure_ascii = False


# ------------------------------------------------------------
# 1. 환경변수
# ------------------------------------------------------------
def env_bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}


DATA_GO_KR_KEY = (
    os.getenv("DATA_GO_KR_KEY", "").strip()
    or os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
)

# 0.0.0.0 = 같은 와이파이/외부에서 접속 허용, 127.0.0.1 = 내 PC만
HOST = os.getenv("APP_HOST", "0.0.0.0")
# 클라우드(Render 등)는 PORT 환경변수를 자동으로 넣어 줌
PORT = int(os.getenv("PORT") or os.getenv("APP_PORT", "5000"))
AUTO_OPEN_BROWSER = env_bool("AUTO_OPEN_BROWSER", False)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
START_SCHEDULER = env_bool("START_SCHEDULER", True)
AUTO_REFRESH_MINUTES = int(os.getenv("AUTO_REFRESH_MINUTES", "60"))

STALE_HOURS = int(os.getenv("STALE_HOURS", "24"))
FULL_REFRESH_LIMIT = int(os.getenv("FULL_REFRESH_LIMIT", "3"))
API_CACHE_SECONDS = 60 * 60
SNAPSHOT_SCHEMA = 1  # v1 캐시 구조

# 서비스별 일일 호출 한도
DAILY_LIMITS = {
    "data_go_kr": int(os.getenv("DAILY_API_LIMIT", "500")),
}

# 캐시 json 을 쓰는 폴더 (클라우드에서 쓰기 가능한 폴더로 바꿀 수 있음)
DATA_DIR = os.getenv("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

SNAPSHOT_FILE = os.path.join(DATA_DIR, "realtime_beds_cache.json")
REFRESH_STATE_FILE = os.path.join(DATA_DIR, "refresh_state.json")
API_USAGE_FILE = os.path.join(DATA_DIR, "api_usage.json")

NIA_BASE_URL = "http://apis.data.go.kr/B552657/ErmctInfoInqireService"


def find_file(*names):
    """data/ 폴더 우선, 없으면 실행 폴더에서 찾기"""
    for name in names:
        for folder in (os.path.join(BASE_DIR, "data"), BASE_DIR):
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return path
    return os.path.join(BASE_DIR, names[0])


HTML_FILE = find_file(
    os.getenv("HTML_FILE", "실시간_병상관제_v1.html"),
)


# ------------------------------------------------------------
# 2. 자치구 정보
# ------------------------------------------------------------
ZONE_OF = {
    "종로구": "도심권", "중구": "도심권", "용산구": "도심권",
    "성동구": "동북권", "광진구": "동북권", "동대문구": "동북권", "중랑구": "동북권",
    "성북구": "동북권", "강북구": "동북권", "도봉구": "동북권", "노원구": "동북권",
    "은평구": "서북권", "서대문구": "서북권", "마포구": "서북권",
    "양천구": "서남권", "강서구": "서남권", "구로구": "서남권", "금천구": "서남권",
    "영등포구": "서남권", "동작구": "서남권", "관악구": "서남권",
    "서초구": "동남권", "강남구": "동남권", "송파구": "동남권", "강동구": "동남권",
}
SEOUL_GU_LIST = list(ZONE_OF.keys())
VALID_GU = set(SEOUL_GU_LIST)

# 실시간 가용병상 API가 제공되지 않는 예외 자치구
STATIC_ER_HOSPITALS = {
    "강북구": [
        {"Hospital_Name": "의료법인성화의료재단 대한병원", "ER_Beds": 7},
        {"Hospital_Name": "서울현대병원", "ER_Beds": 7},
        {"Hospital_Name": "강북으뜸병원", "ER_Beds": 3},
    ],
    "마포구": [
        {"Hospital_Name": "신촌연세병원", "ER_Beds": 6},
    ],
}
STATIC_ER_GU = set(STATIC_ER_HOSPITALS)
REALTIME_GU_LIST = [gu for gu in SEOUL_GU_LIST if gu not in STATIC_ER_GU]

# 경계가 맞닿은 자치구 (가까운 순서)
NEIGHBOR_GU = {
    "마포구": ["서대문구", "은평구", "용산구", "영등포구", "강서구"],
    "강북구": ["성북구", "도봉구", "노원구"],
}
NEARBY_PER_GU = 2   # 인접 구마다 보여줄 병원 수


def neighbor_districts(gu):
    """지정된 인접 구가 없으면 같은 권역 자치구 사용"""
    if gu in NEIGHBOR_GU:
        return NEIGHBOR_GU[gu]
    return [g for g in SEOUL_GU_LIST if ZONE_OF[g] == ZONE_OF[gu] and g != gu]


# ------------------------------------------------------------
# 3. 한국시간 · json 파일 도구
# ------------------------------------------------------------
KST = timezone(timedelta(hours=9))


def now_kst():
    # 클라우드 서버는 보통 UTC → 항상 한국시간으로 맞춤
    return datetime.now(KST).replace(tzinfo=None)


def today_key():
    return now_kst().strftime("%Y-%m-%d")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    # 임시 파일에 쓴 뒤 교체 → 쓰는 도중 읽어도 깨지지 않음
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ------------------------------------------------------------
# 4. 일일 API 호출 횟수 관리
# ------------------------------------------------------------
class RateLimitExhausted(Exception):
    pass


_api_usage_lock = threading.Lock()


def _load_api_usage():
    data = read_json(API_USAGE_FILE, {})
    if data.get("date") != today_key():
        return {"date": today_key(), "counts": {}}
    counts = data.get("counts") or {}
    if not counts and "count" in data:
        # v6/v7 파일 형식 호환 (예전 count = 공공데이터포털 호출)
        counts = {"data_go_kr": int(data["count"])}
    return {"date": data["date"], "counts": counts}


def api_usage_status():
    with _api_usage_lock:
        data = _load_api_usage()
    result = {"date": data["date"]}
    for service, limit in DAILY_LIMITS.items():
        used = int(data["counts"].get(service, 0))
        result[service] = {"used": used, "limit": limit, "remaining": max(0, limit - used)}
    return result


def reserve_api_call(service):
    with _api_usage_lock:
        data = _load_api_usage()
        used = int(data["counts"].get(service, 0))
        if used >= DAILY_LIMITS[service]:
            raise RateLimitExhausted(f"{service} 일일 호출 제한 {DAILY_LIMITS[service]}회 소진")
        data["counts"][service] = used + 1
        write_json(API_USAGE_FILE, data)
        return used + 1


def request_get_with_retry(url, params, service, max_retries=3, base_delay=1.5,
                           timeout=20, verify=True):
    last_status = None
    for attempt in range(max_retries):
        wait = base_delay * (2 ** attempt)
        try:
            call_no = reserve_api_call(service)
            print(f"[API:{service}] {call_no}/{DAILY_LIMITS[service]} {url.rsplit('/', 1)[-1]}")
            r = requests.get(url, params=params, timeout=timeout, verify=verify)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == max_retries - 1:
                raise
            time.sleep(wait)
            continue

        if r.status_code == 200:
            return r

        last_status = r.status_code
        if r.status_code == 429 or 500 <= r.status_code < 600:
            if attempt == max_retries - 1:
                break
            time.sleep(float(r.headers.get("Retry-After", wait)))
            continue
        r.raise_for_status()

    if last_status == 429:
        raise RateLimitExhausted("API 호출 한도 초과 (HTTP 429)")
    raise RuntimeError(f"API 요청 실패 (HTTP {last_status})")


# ------------------------------------------------------------
# 5. 응답 정리 함수
# ------------------------------------------------------------
def parse_xml_items(xml_text):
    root = ET.fromstring(xml_text)

    for code_tag, msg_tag in (("returnReasonCode", "returnAuthMsg"),
                              ("resultCode", "resultMsg")):
        code = root.findtext(f".//{code_tag}")
        if code not in (None, "00"):
            msg = root.findtext(f".//{msg_tag}") or ""
            if code == "22" or "LIMITED" in msg.upper():
                raise RateLimitExhausted(msg)
            raise RuntimeError(f"API 오류 {code}: {msg}")

    rows = [{child.tag: child.text for child in item} for item in root.findall(".//item")]
    try:
        total = int(root.findtext(".//totalCount", default="0") or 0)
    except ValueError:
        total = len(rows)
    return rows, total


def extract_gu(text):
    if not text:
        return None
    m = re.search(r"([가-힣]+구)", str(text))
    if m and m.group(1) in VALID_GU:
        return m.group(1)
    return None


def parse_updated_at(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], fmt)
            except ValueError:
                pass
    return None


def normalize_bed(raw):
    try:
        raw_num = int(float(raw))
    except (TypeError, ValueError):
        return {"Available_Beds": None, "Beds_Raw": raw, "Is_Overcrowded": False}
    # 음수 = 대기 환자가 병상보다 많음(과밀) → 가용 0 으로 표시
    return {"Available_Beds": max(0, raw_num), "Beds_Raw": raw_num,
            "Is_Overcrowded": raw_num < 0}


def finalize_hospital(row):
    updated = parse_updated_at(row.get("Updated_At"))
    is_stale = updated is None or now_kst() - updated > timedelta(hours=STALE_HOURS)
    if is_stale:
        row["Available_Beds"] = None
    row["Is_Stale"] = is_stale
    row["Beds_Unknown"] = row.get("Available_Beds") is None
    return row


def _pick(row, *names):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


# ------------------------------------------------------------
# 6. NMC 실시간 병상 (메인)
# ------------------------------------------------------------
def fetch_nia_realtime(district):
    params = {
        "serviceKey": DATA_GO_KR_KEY,
        "STAGE1": "서울특별시",
        "STAGE2": district,
        "pageNo": 1,
        "numOfRows": 100,
    }
    r = request_get_with_retry(f"{NIA_BASE_URL}/getEmrrmRltmUsefulSckbdInfoInqire",
                               params, "data_go_kr")
    rows, total = parse_xml_items(r.text)

    hospitals = []
    for x in rows:
        hospitals.append(finalize_hospital({
            "Hospital_ID": x.get("hpid"),
            "Hospital_Name": x.get("dutyName"),
            "Tel": x.get("dutyTel3"),
            "Updated_At": x.get("hvidate"),
            "Ambulance_Available": x.get("hvamyn"),
            "District": district,
            "data_source": "existing_realtime_API",
            **normalize_bed(x.get("hvec")),
        }))
    return hospitals


# ------------------------------------------------------------
# 7. 전체 갱신 (서버 스케줄러 또는 관리자만 실행)
# ------------------------------------------------------------
_snapshot_lock = threading.Lock()
_snap_mem = {"mtime": None, "data": {}}


def load_snapshot():
    # 파일이 바뀌었을 때만 다시 읽기
    try:
        mtime = os.path.getmtime(SNAPSHOT_FILE)
    except OSError:
        return {}
    if _snap_mem["mtime"] != mtime:
        data = read_json(SNAPSHOT_FILE, {})
        _snap_mem.update(mtime=mtime, data=data if isinstance(data, dict) else {})
    return _snap_mem["data"]


def snapshot_age_seconds(snapshot):
    ts = snapshot.get("updated_at")
    if not ts:
        return None
    try:
        return max(0, int((now_kst() - datetime.fromisoformat(ts)).total_seconds()))
    except ValueError:
        return None


def refresh_state():
    state = read_json(REFRESH_STATE_FILE, {})
    if state.get("date") != today_key():
        state = {"date": today_key(), "full_refresh_count": 0, "last_refresh": None}
    return state


def can_full_refresh():
    if not DATA_GO_KR_KEY:
        return False, "DATA_GO_KR_KEY 없음"
    state = refresh_state()
    if state["full_refresh_count"] >= FULL_REFRESH_LIMIT:
        return False, "오늘 전체 갱신 횟수 소진"
    if state.get("last_refresh"):
        passed = (now_kst() - datetime.fromisoformat(state["last_refresh"])).total_seconds()
        if passed < API_CACHE_SECONDS:
            return False, f"다음 갱신까지 {int((API_CACHE_SECONDS - passed) // 60) + 1}분"
    if api_usage_status()["data_go_kr"]["remaining"] < len(REALTIME_GU_LIST):
        return False, "공공데이터포털 일일 잔여 호출 부족"
    return True, None


def refresh_all_districts(force=False):
    with _snapshot_lock:
        old = load_snapshot()
        ok, reason = can_full_refresh()
        if not ok and not force:
            return old, False, reason

        old_districts = (old.get("districts", {})
                         if old.get("schema") == SNAPSHOT_SCHEMA else {})
        payloads, errors = {}, []

        # 23개 구만 NMC 실시간 API 호출
        for gu in REALTIME_GU_LIST:
            try:
                hospitals = fetch_nia_realtime(gu)
                payloads[gu] = {"district": gu, "hospitals": hospitals}
            except Exception as e:
                errors.append(f"{gu}: {e}")
                prev = dict(old_districts.get(gu, {"district": gu, "hospitals": []}))
                prev["cache_stale"] = True
                payloads[gu] = prev

        # 강북·마포는 실시간 API 대신 별도 UI 데이터 사용
        for gu in STATIC_ER_GU:
            payloads[gu] = {"district": gu, "hospitals": []}

        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "updated_at": now_kst().isoformat(timespec="seconds"),
            "source": "NMC 실시간 병상 API (23개 구) + 강북·마포 정적 응급실 병상",
            "districts": payloads,
            "errors": errors,
            "stats": {
                "realtime_district_count": len(REALTIME_GU_LIST),
                "static_er_districts": sorted(STATIC_ER_GU),
                "empty_realtime_districts": [g for g in REALTIME_GU_LIST if not payloads[g]["hospitals"]],
                "max_district_count": max((len(payloads[g]["hospitals"]) for g in REALTIME_GU_LIST), default=0),
            },
        }
        write_json(SNAPSHOT_FILE, snapshot)

        state = refresh_state()
        state["full_refresh_count"] += 1
        state["last_refresh"] = snapshot["updated_at"]
        write_json(REFRESH_STATE_FILE, state)
        return snapshot, True, None


# ------------------------------------------------------------
# 8. 강북·마포 인접 구 병원 안내
# ------------------------------------------------------------
def build_nearby(snapshot, gu):
    """가까운 구 순서대로, 구마다 가용 병상이 많은 병원 2곳씩"""
    districts = snapshot.get("districts", {})
    nearby = []
    for near_gu in neighbor_districts(gu):
        hospitals = [dict(h, From_District=near_gu)
                     for h in districts.get(near_gu, {}).get("hospitals", [])]
        # 병상 확인 가능한 병원 먼저 → 가용 병상 많은 순
        hospitals.sort(key=lambda h: (h.get("Available_Beds") is None,
                                      -(h.get("Available_Beds") or 0)))
        nearby.extend(hospitals[:NEARBY_PER_GU])
    return nearby


def district_payload(snapshot, gu):
    # 강북·마포: 등록 응급실 병상 수 + 실시간 미제공 안내 + 인접구 실시간 정보
    if gu in STATIC_ER_GU:
        static_hospitals = [dict(h, District=gu, data_source="static_er_beds")
                            for h in STATIC_ER_HOSPITALS[gu]]
        return {
            "district": gu,
            "hospitals": static_hospitals,
            "data_type": "static_er_beds",
            "realtime_available": False,
            "notice": "실시간 가용병상 정보가 제공되지 않아 등록 응급실 병상 수를 표시합니다.",
            "nearby_notice": "인접 자치구의 실시간 가용병상 정보입니다.",
            "nearby_hospitals": build_nearby(snapshot, gu) if snapshot else [],
        }

    base = snapshot.get("districts", {}).get(gu)
    payload = dict(base) if base else {"district": gu, "hospitals": []}
    payload["data_type"] = "realtime"
    payload["realtime_available"] = True
    payload["nearby_hospitals"] = []
    payload["notice"] = None
    if not snapshot:
        payload["error"] = "병상 데이터를 준비 중입니다. 잠시 후 새로고침하세요."
    elif not payload.get("hospitals"):
        payload["notice"] = f"{gu} 병상 정보가 없어 인접 자치구 병원을 안내합니다."
        payload["nearby_hospitals"] = build_nearby(snapshot, gu)
    return payload


# ------------------------------------------------------------
# 9. 웹 경로 (방문자는 저장된 캐시만 읽음)
# ------------------------------------------------------------
@app.get("/")
def index():
    if not os.path.isfile(HTML_FILE):
        return jsonify({"error": "HTML 파일 없음", "expected_path": HTML_FILE}), 404
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/realtime-beds")
def realtime_beds():
    district = request.args.get("district", "강남구").strip()
    if district not in VALID_GU:
        return jsonify({"error": "서울시 자치구 이름이 올바르지 않습니다."}), 400
    snapshot = load_snapshot()
    payload = district_payload(snapshot, district)
    payload["snapshot_updated_at"] = snapshot.get("updated_at")
    return jsonify(payload)


@app.get("/api/realtime-beds/all")
def realtime_beds_all():
    # 25개 구를 한 번에 → 브라우저 요청 25회 → 1회
    snapshot = load_snapshot()
    return jsonify({
        "snapshot_updated_at": snapshot.get("updated_at"),
        "snapshot_age_seconds": snapshot_age_seconds(snapshot),
        "districts": [district_payload(snapshot, gu) for gu in SEOUL_GU_LIST],
    })


@app.post("/api/refresh")
def manual_refresh():
    token = request.headers.get("X-Admin-Token") or request.args.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return jsonify({"error": "관리자만 갱신할 수 있습니다."}), 403
    snapshot, refreshed, reason = refresh_all_districts()
    return jsonify({"refreshed": refreshed, "reason": reason,
                    "updated_at": snapshot.get("updated_at"),
                    "api_usage": api_usage_status()})


@app.get("/api/status")
def status():
    snap = load_snapshot()
    return jsonify({
        "bed_source": "NMC 실시간 병상 API (23개 구) + 강북·마포 정적 응급실 병상",
        "data_go_kr": bool(DATA_GO_KR_KEY),
        "static_er_districts": sorted(STATIC_ER_GU),
        "snapshot_stats": snap.get("stats"),
        "snapshot_updated_at": snap.get("updated_at"),
        "snapshot_age_seconds": snapshot_age_seconds(snap),
        "cached_districts": len(snap.get("districts", {})),
        "api_usage": api_usage_status(),
        "refresh_state": refresh_state(),
        "full_refresh_limit": FULL_REFRESH_LIMIT,
        "auto_refresh_minutes": AUTO_REFRESH_MINUTES,
    })


@app.get("/healthz")
def healthz():
    return "ok"


# ------------------------------------------------------------
# 10. 자동 갱신 스케줄러 (서버 안에서 1개만 동작)
# ------------------------------------------------------------
_scheduler_lock = threading.Lock()
_scheduler_started = False


def _auto_refresh_loop():
    last_reason = None
    time.sleep(3)
    while True:
        try:
            age = snapshot_age_seconds(load_snapshot())
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


def start_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started or AUTO_REFRESH_MINUTES <= 0:
            return
        _scheduler_started = True
    threading.Thread(target=_auto_refresh_loop, daemon=True).start()


# gunicorn 으로 실행해도 스케줄러가 켜지도록 import 시점에 시작
if START_SCHEDULER:
    start_scheduler()


if __name__ == "__main__":
    usage = api_usage_status()
    print("=" * 58)
    print("SEOUL EMERGENCY HUB V1 - WEB SERVER")
    print("=" * 58)
    print(f"[KEY] DATA_GO_KR   : {'OK (메인)' if DATA_GO_KR_KEY else 'MISSING → 갱신 불가'}")
    print(f"[ADMIN] 수동 갱신    : {'ON' if ADMIN_TOKEN else 'OFF (ADMIN_TOKEN 없음)'}")
    print(f"[HTML] {HTML_FILE}")
    for name in DAILY_LIMITS:
        print(f"[LIMIT] {name:10} {usage[name]['used']}/{usage[name]['limit']} 사용")
    print(f"[SNAPSHOT] {load_snapshot().get('updated_at') or '없음 → 자동 수집 시작'}")
    print(f"[START] http://{'127.0.0.1' if HOST == '0.0.0.0' else HOST}:{PORT}/")

    if AUTO_OPEN_BROWSER:
        threading.Timer(1.5, lambda: webbrowser.open_new(f"http://127.0.0.1:{PORT}/")).start()

    try:
        from waitress import serve  # 여러 사람이 동시에 접속해도 안정적인 서버
        print("[SERVER] waitress")
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("[SERVER] flask 개발 서버 (pip install waitress 권장)")
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
