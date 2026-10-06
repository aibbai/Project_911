# chatbot_exaone.py : 오른쪽 아래 챗봇 창(base.html)이 호출하는 서버 코드
# 연결 : app_integrated_v1.py 에서  from chatbot_exaone import init_chatbot ; init_chatbot(app)
#
# 질문 처리 순서
#   주소·장소 이름   → 가장 가까운 응급실 (가용 병상 1개 이상)
#   구·동 이름       → 이송 수요 · 생활인구 예측 (숫자는 코드, 해석은 EXAONE)
#   "근처 응급실"    → 브라우저 현재 위치로 다시 요청
#   그 외            → 안내 문구

import os
import re
import json
import math
import time
import threading
from urllib.parse import quote

import requests
from flask import jsonify, request

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_ID = os.getenv("CHAT_MODEL_ID", "LGAI-EXAONE/EXAONE-4.0-1.2B")
MAX_NEW_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "200"))
KAKAO_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()
DATA_KEY = os.getenv("DATA_GO_KR_KEY") or os.getenv("DATA_GO_KR_SERVICE_KEY")

GU_LIST = ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
           "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
           "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"]
ALL = "서울 전체"

GUIDE = ("안녕하세요! 서울시 응급의료 안내 챗봇입니다.\n"
         "구·동 이름을 넣으면 이송 수요 예측을,\n"
         "주소를 넣거나 📍 버튼을 누르면 가장 가까운 응급실을 알려드립니다.\n"
         "예) 역삼동 이송 예측 / 테헤란로 152 응급실")
BEDS_HINT = "※ 응급실 병상은 주소를 입력하거나 📍 버튼을 누르면 가까운 곳으로 알려드립니다."

SYSTEM_PROMPT = (
    "너는 서울시 응급 의료 및 이송 수요 예측 대시보드의 안내 챗봇이다.\n"
    "[확인된 사실]은 이미 사용자 화면에 그대로 표시된다.\n"
    "너는 그 아래에 붙일 핵심 해석을 2문장 이내로만 써라.\n"
    "숫자 목록을 다시 나열하지 마라. 사실에 없는 숫자, 병원, 기간은 절대 만들지 마라.\n"
    "지역 이름은 첫 줄 [ ] 안의 이름만 써라.\n"
    "'예시', '가정' 같은 표현을 쓰지 말고, 짧고 명확한 한국어로 써라."
)

TOPIC_WORDS = {
    "beds": ["병상", "응급실", "병원", "가용", "입원"],
    "transport": ["예측", "이송", "수요", "출동", "구급", "건수"],
    "population": ["인구", "밀집", "유동"],
}
NEAR_WORDS = re.compile(r"가까운|근처|주변|내\s?위치|현재\s?위치")
# 동 이름처럼 보이는 말 (사전에 없으면 "찾지 못했다"고 알려 주기 위함)
DONG_LIKE = re.compile(r"[가-힣]{1,5}\d*동(?=$|\s|,|의|에|은|는|이|을|를)")
NOT_DONG = ("출동", "이동", "변동", "활동", "행동", "운동", "자동", "공동", "연동", "작동", "노동")

# 주소 : 도로명(테헤란로 152, 언주로30길 10) 또는 지번(역삼동 123-4, 을지로3가 5)
ADDRESS_PATTERN = re.compile(
    r"(?:서울(?:특별시|시)?\s*)?(?:[가-힣]+구\s*)?(?:[가-힣]+\d*동\s*)?"
    r"(?:[가-힣]+\d*(?:동|가)|[가-힣\d]+(?:로|길))\s*\d+(?:-\d+)?(?![\d월년일건명개시%가])"
)
# 장소 이름 : 강남역, 서울대병원, 여의도공원 등
LANDMARK_PATTERN = re.compile(
    r"[가-힣A-Za-z\d]+(?:역|병원|대학교|대학|공원|시장|터미널|타워|빌딩|아파트|학교)"
    r"(?=$|\s|,|에서|근처|주변|앞|쪽)"
)
NOT_LANDMARK = ("지역", "구역", "영역", "권역", "광역", "전역", "무역")
NOT_IN_LANDMARK = ("근처", "주변", "가까운", "응급")

# 동 이름 → 자치구 사전 (119안전센터 관할구역으로 만든 파일)
try:
    with open(os.path.join(HERE, "dong_to_gu.json"), encoding="utf-8") as f:
        DONG_MAP = json.load(f)
except FileNotFoundError:
    DONG_MAP = {}
    print("[CHATBOT] ⚠ dong_to_gu.json 없음 → 동 이름 검색 사용 안 함 (chatbot_exaone.py 옆에 두세요)")
DONG_KEYS = sorted(DONG_MAP, key=len, reverse=True)  # 긴 이름부터 비교

# 응급의료기관 좌표 파일 (공공API는 30일에 한 번만 호출)
ER_LOC_FILE = os.path.join(os.getenv("DATA_DIR") or HERE, "er_locations.json")
ER_LIST_URL = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire"

state = {"tokenizer": None, "model": None, "status": "waiting", "error": ""}
load_lock, gen_lock = threading.Lock(), threading.Lock()


# ------------------------------------------------------------
# 1. EXAONE 모델 로드
# ------------------------------------------------------------
def load_model():
    with load_lock:
        if state["status"] in ("ready", "error"):
            return
        state["status"] = "loading"
        try:
            import sys
            import transformers
            from transformers import AutoTokenizer, AutoModelForCausalLM

            print("[CHATBOT] 파이썬 :", sys.executable, "/ transformers :", transformers.__version__)
            state["tokenizer"] = AutoTokenizer.from_pretrained(MODEL_ID)
            state["model"] = AutoModelForCausalLM.from_pretrained(
                MODEL_ID, torch_dtype="auto", low_cpu_mem_usage=True).eval()
            state["status"] = "ready"
            print("[CHATBOT] EXAONE 로드 완료")
        except Exception as e:
            state["status"], state["error"] = "error", f"{type(e).__name__}: {e}"
            print("[CHATBOT] 모델 로드 실패 → 데이터 요약 답변으로 동작 :", state["error"])


# ------------------------------------------------------------
# 2. 질문 분석 : 구·동 · 주소 · 장소 이름 · 질문 종류
# ------------------------------------------------------------
def find_district(text):
    full = [gu for gu in GU_LIST if gu in text]
    short = [gu for gu in GU_LIST if len(gu) > 2 and gu[:-1] in text]  # "강남" → 강남구
    return max(full, key=len) if full else (short[0] if short else None)


def find_dong(text):
    # "역삼1동", "을지로3가" → 숫자·기호를 지우고 사전과 비교
    plain = re.sub(r"[\dㆍ~\-\s]+", "", text)
    for dong in DONG_KEYS:
        if dong not in plain:
            continue
        # 두 글자 동(목동·창동 등)은 단어 맨 앞에 있을 때만 인정
        if len(dong) == 2 and not re.search(rf"(^|[\s,(]){dong[0]}\d*{dong[1]}", text):
            continue
        shown = re.search(rf"{dong[:-1]}[\dㆍ~\s]*{dong[-1]}", text)  # 사용자가 쓴 그대로 표시
        return (shown.group(0) if shown else dong), DONG_MAP[dong]
    return None, []


def find_place(text):
    # 결과 : (자치구, 동, 후보 자치구 목록)
    gu = find_district(text)
    dong, gus = find_dong(text)
    if gu:
        return gu, (dong if gu in gus else None), [gu]
    return (gus[0] if len(gus) == 1 else None), dong, gus


def find_landmark(text):
    for m in LANDMARK_PATTERN.finditer(text):
        name = m.group(0)
        if name not in NOT_LANDMARK and not any(w in name for w in NOT_IN_LANDMARK):
            return name
    return None


def find_address(text):
    m = ADDRESS_PATTERN.search(text)
    return m.group(0).strip() if m else None


def find_topics(text):
    return [k for k, words in TOPIC_WORDS.items() if any(w in text for w in words)]


# ------------------------------------------------------------
# 3. 예측 답변 (숫자는 코드가 정확히, 해석은 EXAONE이 짧게)
# ------------------------------------------------------------
def api_get(app, path):
    # 같은 서버 안에서 호출 → 주소·포트 설정이 필요 없음
    res = app.test_client().get(path)
    if res.status_code != 200:
        raise RuntimeError(f"{path} 응답 코드 {res.status_code}")
    return res.get_json(force=True)


def forecast_facts(app, district, dong, topics):
    dash = api_get(app, "/api/dashboard-data")
    tr, pop = dash.get("transport") or {}, dash.get("population") or {}
    lines = [f"[{district}" + (f" {dong} (구 단위 데이터)]" if dong else "]")]

    gu = (tr.get("districts") or {}).get(district) or {}
    pairs = [(m, v) for m, v in zip(tr.get("future_months") or [], gu.get("forecast") or []) if v is not None]
    if "transport" in topics and pairs:
        lines.append(f"월별 이송 건수 예측 ({tr.get('best_model')})")
        lines += [f"- {m} : {v:,}건" for m, v in pairs]
        top, low = max(pairs, key=lambda x: x[1]), min(pairs, key=lambda x: x[1])
        change = (pairs[-1][1] - pairs[0][1]) / pairs[0][1] * 100
        lines.append(f"가장 많은 달 {top[0]} / 가장 적은 달 {low[0]} / "
                     f"첫 달({pairs[0][0]}) → 마지막 달({pairs[-1][0]}) 변화 {change:+.1f}%")
        recent = [(m, v) for m, v in zip((tr.get("test_months") or [])[-3:],
                                         (gu.get("actual") or [])[-3:]) if v is not None]
        if recent:
            lines.append("최근 실제 : " + ", ".join(f"{m} {v:,}건" for m, v in recent))

    pred = ((pop.get("daily") or {}).get(district) or {}).get("pred") or []
    if "population" in topics and pred:
        lines.append(f"생활인구 일최대 예측 ({(pop.get('dates') or ['-'])[-1]}) : {pred[-1]:,}명")

    if len(lines) == 1:
        lines.append("이 지역의 예측 데이터를 찾지 못했습니다.")
    return "\n".join(lines)


def ask_exaone(question, facts):
    import torch

    tokenizer, model = state["tokenizer"], state["model"]
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"사용자 질문:\n{question}\n\n[확인된 사실]\n{facts}"}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = {k: v.to(model.device) for k, v in tokenizer(prompt, return_tensors="pt").items()}

    with gen_lock, torch.no_grad():  # 한 번에 한 질문씩 생성
        outputs = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                 eos_token_id=tokenizer.eos_token_id,
                                 pad_token_id=tokenizer.eos_token_id)

    comment = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    comment = comment.split("</think>")[-1].strip()

    # 사실에 없는 큰 숫자(건수·인원)나 다른 지역 이름이 나오면 해석을 버림
    known = set(re.findall(r"\d+", facts.replace(",", "")))
    made_up = [n for n in re.findall(r"\d{3,}", comment.replace(",", "")) if n not in known]
    places = GU_LIST + [d for d in DONG_KEYS if len(d) >= 3]
    made_up += [p for p in places if p in comment and p not in facts]
    return facts if not comment or made_up else f"{facts}\n\n💬 {comment}"


# ------------------------------------------------------------
# 4. 가까운 응급실 (좌표 · 거리 · 주소 검색)
# ------------------------------------------------------------
def load_er_locations():
    saved = None
    if os.path.exists(ER_LOC_FILE):
        with open(ER_LOC_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        if time.time() - os.path.getmtime(ER_LOC_FILE) < 30 * 86400:
            return saved
    try:
        import xml.etree.ElementTree as ET

        params = {"serviceKey": DATA_KEY, "Q0": "서울특별시", "pageNo": 1, "numOfRows": 500}
        root = ET.fromstring(requests.get(ER_LIST_URL, params=params, timeout=20).text)
        locs = {i.findtext("hpid"): {"lat": float(i.findtext("wgs84Lat")),
                                     "lon": float(i.findtext("wgs84Lon")),
                                     "addr": i.findtext("dutyAddr")}
                for i in root.findall(".//item")
                if i.findtext("hpid") and i.findtext("wgs84Lat") and i.findtext("wgs84Lon")}
        if not locs:
            raise RuntimeError("응급의료기관 좌표를 받지 못했습니다. (.env 의 DATA_GO_KR_KEY 확인)")
        with open(ER_LOC_FILE, "w", encoding="utf-8") as f:
            json.dump(locs, f, ensure_ascii=False)
        print(f"[CHATBOT] 응급의료기관 좌표 {len(locs)}곳 저장 :", ER_LOC_FILE)
        return locs
    except Exception:
        if saved:  # 새로 받기 실패 → 예전 파일 사용
            return saved
        raise


def distance_km(lat1, lon1, lat2, lon2):
    # 하버사인 공식 : 위도·경도 → 직선거리(km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def nearest_ers(app, lat, lon, top=3):
    allbeds, locs = api_get(app, "/api/realtime-beds/all"), load_er_locations()
    rows = []
    for d in allbeds.get("districts", []):
        for h in d.get("hospitals", []):
            beds, loc = h.get("Available_Beds"), locs.get(h.get("Hospital_ID"))
            if h.get("data_source") == "static_er_beds" or not loc or beds is None or beds < 1:
                continue  # 실시간 정보 없음 · 좌표 없음 · 가용 병상 0 → 제외
            rows.append(dict(h, **loc, dist=distance_km(lat, lon, loc["lat"], loc["lon"])))
    rows.sort(key=lambda h: h["dist"])
    return rows[:top], allbeds.get("snapshot_updated_at")


def nearest_answer(rows, updated, origin):
    if not rows:
        return "현재 가용 병상이 1개 이상인 응급실 정보를 찾지 못했습니다.\n급한 경우 바로 119에 전화하세요.", []
    lines = [f"📍 {origin} 기준 가까운 응급실", f"(가용 병상 1개 이상 · 기준 {updated or '수집 전'})"]
    links = []
    for i, h in enumerate(rows, 1):
        lines.append(f"{i}. {h['Hospital_Name']} · {h['dist']:.1f}km · 가용 {h['Available_Beds']}개")
        lines.append(f"   ☎ {h.get('Tel') or '-'} · {h.get('addr') or ''}")
        links.append({"label": f"{i}번 길찾기", "url": "https://map.kakao.com/link/to/"
                      f"{quote(h['Hospital_Name'])},{h['lat']},{h['lon']}"})
    lines.append("\n직선거리 기준입니다. 위급하면 119에 먼저 전화하세요.")
    return "\n".join(lines), links


def geocode(query, kinds=("address", "keyword")):
    # 주소(또는 장소 이름) → (위도, 경도, 찾은 이름) / 카카오 로컬 API
    if not KAKAO_KEY:
        raise RuntimeError("주소 검색 키(KAKAO_REST_API_KEY)가 .env 에 없습니다.")
    query = query if "서울" in query else "서울 " + query
    for kind in kinds:  # 주소는 주소 검색 먼저, 장소 이름은 장소 검색 먼저
        res = requests.get(f"https://dapi.kakao.com/v2/local/search/{kind}.json",
                           params={"query": query, "size": 1},
                           headers={"Authorization": f"KakaoAK {KAKAO_KEY}"}, timeout=10)
        if res.status_code in (401, 403):
            print("[CHATBOT] 카카오 응답 :", res.status_code, res.text[:200])
            raise RuntimeError("카카오 키 설정 문제 (401 = 키 오류, 403 = 카카오맵 사용 설정 꺼짐)")
        res.raise_for_status()
        docs = res.json().get("documents", [])
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"]), docs[0].get("address_name") or docs[0].get("place_name")
    return None


# ------------------------------------------------------------
# 5. Flask 연결
# ------------------------------------------------------------
def init_chatbot(app):
    # 서버 시작과 함께 모델 미리 로드 (debug 재시작용 부모 프로세스는 제외)
    if os.getenv("CHAT_PRELOAD", "1") == "1" and (not app.debug or os.getenv("WERKZEUG_RUN_MAIN") == "true"):
        threading.Thread(target=load_model, daemon=True).start()

    def reply(answer, source, **extra):
        return jsonify(answer=answer, source=source, **extra)

    def nearest_reply(lat, lon, origin):
        try:
            rows, updated = nearest_ers(app, lat, lon)
        except Exception as e:
            print("[CHATBOT] 가까운 응급실 조회 실패 :", repr(e))
            return reply(f"응급실 위치 정보를 불러오지 못했습니다. ({e})", "error")
        answer, links = nearest_answer(rows, updated, origin)
        return reply(answer, "location", links=links)

    def address_reply(query, kinds=("address", "keyword")):
        try:
            point = geocode(query, kinds)
        except Exception as e:
            print("[CHATBOT] 주소 검색 실패 :", repr(e))
            return reply(f"주소를 좌표로 바꾸지 못했습니다. ({e})\n📍 버튼으로 현재 위치를 이용해 주세요.", "error")
        if not point:
            return reply(f"'{query}' 주소를 찾지 못했습니다.\n도로명과 건물번호를 함께 입력해 주세요. 예) 테헤란로 152", "guide")
        return nearest_reply(*point)

    def forecast_reply(question, district, dong, topics, note=None):
        try:
            facts = forecast_facts(app, district, dong, topics if set(topics) - {"beds"} else ["transport"])
        except Exception as e:
            print("[CHATBOT] 데이터 조회 실패 :", repr(e))
            return reply(f"데이터를 불러오지 못했습니다. ({e})", "error")

        answer, source = facts, "summary"
        if state["status"] == "ready":
            try:
                answer, source = ask_exaone(question, facts), "exaone"
            except Exception as e:
                print("[CHATBOT] 생성 실패 :", e)
        elif state["status"] == "waiting":
            threading.Thread(target=load_model, daemon=True).start()
        if note:
            answer = note + "\n\n" + answer
        if "beds" in topics:
            answer += "\n\n" + BEDS_HINT
        return reply(answer, source, district=district)

    @app.get("/api/chat/status")
    def chat_status():
        return jsonify(status=state["status"], model=MODEL_ID, error=state["error"])

    @app.post("/api/chat")
    def chat():
        question = str((request.get_json(silent=True) or {}).get("message", "")).strip()[:300]
        if not question:
            return jsonify(error="질문을 입력해 주세요."), 400

        near = bool(NEAR_WORDS.search(question))
        address, landmark = find_address(question), find_landmark(question)
        gu, dong, candidates = find_place(question)
        topics = find_topics(question)

        if address:                                       # 주소 → 가까운 응급실
            return address_reply(address)
        if landmark and (near or "beds" in topics):       # 강남역 근처 응급실
            return address_reply(landmark, ("keyword", "address"))
        if not gu and len(candidates) > 1:                # 신사동 → 구 다시 묻기
            return reply(f"'{dong}'은(는) {', '.join(candidates)}에 있습니다.\n"
                         f"구 이름을 함께 입력해 주세요.\n예) {candidates[0]} {dong} 이송 예측", "guide")
        if gu and near:                                   # 역삼동 근처 응급실 → 동네 중심
            return address_reply(f"{gu} {dong or ''}".strip())
        if gu:                                            # 구·동 → 예측
            return forecast_reply(question, gu, dong, topics)
        if near:                                          # 근처 응급실 → 현재 위치 요청
            return reply("", "need_location")
        if topics == ["beds"]:
            return reply(BEDS_HINT.lstrip("※ "), "guide")
        if topics:                                        # 서울 전체 예측
            unknown = [w for w in DONG_LIKE.findall(question) if w not in NOT_DONG]
            note = f"※ '{unknown[0]}'을(를) 찾지 못해 서울 전체 기준으로 안내합니다." if unknown else None
            return forecast_reply(question, ALL, None, topics, note)
        return reply(GUIDE, "guide")

    @app.post("/api/chat/nearest")
    def chat_nearest():
        body = request.get_json(silent=True) or {}
        try:
            lat, lon = float(body["lat"]), float(body["lon"])
        except (KeyError, TypeError, ValueError):
            return jsonify(error="위치 값(lat, lon)이 올바르지 않습니다."), 400
        if not (33 <= lat <= 39 and 124 <= lon <= 132):
            return reply("국내 위치에서만 응급실을 찾을 수 있습니다.", "guide")
        return nearest_reply(lat, lon, "현재 위치")

    print("[CHATBOT] /api/chat 연결 완료 · 모델 :", MODEL_ID)
    if not KAKAO_KEY:
        print("[CHATBOT] KAKAO_REST_API_KEY 없음 → 주소로 응급실 찾기 사용 안 함")
    return app
