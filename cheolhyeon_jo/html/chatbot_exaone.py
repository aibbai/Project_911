# chatbot_exaone.py
# 오른쪽 아래 챗봇 창(base.html)이 호출하는 /api/chat 서버 코드
# 04_119_LLM_호환확인 노트북의 EXAONE 로드 · 답변 함수를 그대로 옮김
#
# 연결 방법 (app_integrated_v1.py, app = Flask(...) 아래에 두 줄 추가)
#   from chatbot_exaone import init_chatbot
#   init_chatbot(app)

import os
import re
import json
import threading

from flask import jsonify, request

MODEL_ID = os.getenv("CHAT_MODEL_ID", "LGAI-EXAONE/EXAONE-4.0-1.2B")
MAX_NEW_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "200"))

GU_LIST = ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
           "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
           "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"]
ALL = "서울 전체"

# 데이터와 관련 없는 질문에 보여줄 안내 문구 (base.html 첫 인사와 같음)
GUIDE = ("안녕하세요! 서울시 응급의료 안내 챗봇입니다.\n"
         "질문에 구 이름을 넣어 물어보세요.\n"
         "예) 강남구 응급실 병상 알려줘")

# 숫자 목록은 코드가 정확히 만들고, EXAONE은 짧은 해석만 덧붙임
SYSTEM_PROMPT = (
    "너는 서울시 응급 의료 및 이송 수요 예측 대시보드의 안내 챗봇이다.\n"
    "[확인된 사실]은 이미 사용자 화면에 그대로 표시된다.\n"
    "너는 그 아래에 붙일 핵심 해석을 2문장 이내로만 써라.\n"
    "숫자 목록을 다시 나열하지 마라. 사실에 없는 숫자, 병원, 기간은 절대 만들지 마라.\n"
    "'예시', '가정' 같은 표현을 쓰지 말고, 짧고 명확한 한국어로 써라."
)

# 모델 상태 : 서버 전체에서 하나만 사용
state = {"tokenizer": None, "model": None, "status": "waiting", "error": ""}
load_lock = threading.Lock()
gen_lock = threading.Lock()


# ------------------------------------------------------------
# 1. EXAONE 모델 로드 (노트북 2~3단계)
# ------------------------------------------------------------
def load_model():
    with load_lock:
        if state["model"] is not None or state["status"] == "error":
            return
        state["status"] = "loading"
        try:
            import sys
            import transformers
            from transformers import AutoTokenizer, AutoModelForCausalLM

            print("[CHATBOT] 파이썬 :", sys.executable)
            print("[CHATBOT] transformers :", transformers.__version__)
            state["tokenizer"] = AutoTokenizer.from_pretrained(MODEL_ID)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_ID, torch_dtype="auto", low_cpu_mem_usage=True
            )
            model.eval()
            state["model"] = model
            state["status"] = "ready"
            print("[CHATBOT] EXAONE 로드 완료")
        except Exception as e:
            state["status"] = "error"
            state["error"] = f"{type(e).__name__}: {e}"
            print("[CHATBOT] 모델 로드 실패 → 데이터 요약 답변으로 동작 :", state["error"])


# ------------------------------------------------------------
# 2. 질문 분석 : 자치구 · 질문 종류
# ------------------------------------------------------------
def find_district(text, default=ALL):
    for gu in sorted(GU_LIST, key=len, reverse=True):
        if gu in text:
            return gu
    for gu in GU_LIST:
        short = gu[:-1]
        if len(short) >= 2 and short in text:  # "강남" → 강남구 ("중"은 제외)
            return gu
    return default


def find_topics(text):
    words = {
        "beds": ["병상", "응급실", "병원", "가용", "입원"],
        "transport": ["예측", "이송", "수요", "출동", "구급", "건수"],
        "population": ["인구", "밀집", "유동"],
    }
    return [k for k, ws in words.items() if any(w in text for w in ws)]


# ------------------------------------------------------------
# 3. Flask API에서 필요한 부분만 꺼내기 (노트북 5~7단계)
# ------------------------------------------------------------
def api_get(app, path, params=None):
    # 같은 서버 안에서 호출 → 주소·포트 설정이 필요 없음
    res = app.test_client().get(path, query_string=params or {})
    if res.status_code != 200:
        raise RuntimeError(f"{path} 응답 코드 {res.status_code}")
    return res.get_json(force=True)


def slim(rows, limit=8):
    # 짧은 값만 남겨 모델 입력을 줄임
    out = []
    for row in (rows or [])[:limit]:
        out.append({k: v for k, v in row.items()
                    if v is None or isinstance(v, (int, float, bool)) or len(str(v)) <= 40})
    return out


def build_context(app, district, topics):
    context = {"자치구": district}

    if "beds" in topics:
        if district == ALL:
            context["실시간_병상"] = "자치구를 지정해야 조회할 수 있음"
        else:
            beds = api_get(app, "/api/realtime-beds", {"district": district})
            context["실시간_병상"] = {
                "기준시각": beds.get("snapshot_updated_at"),
                "hospitals": slim(beds.get("hospitals")),
                "인접구_병원": slim(beds.get("nearby_hospitals"), 5),
            }

    if topics != ["beds"]:
        dash = api_get(app, "/api/dashboard-data")
        tr = dash.get("transport") or {}
        gu = (tr.get("districts") or {}).get(district) or {}

        if "transport" in topics:
            context["이송건수_예측"] = {
                "사용모델": tr.get("best_model"),
                "예측월": tr.get("future_months"),
                "예측값": gu.get("forecast"),
                "최근_실제월": (tr.get("test_months") or [])[-3:],
                "최근_실제값": (gu.get("actual") or [])[-3:],
            }

        pop = dash.get("population") or {}
        if "population" in topics and pop:
            daily = (pop.get("daily") or {}).get(district) or {}
            context["생활인구_일최대"] = {
                "날짜": (pop.get("dates") or [])[-7:],
                "예측값": (daily.get("pred") or [])[-7:],
            }

    return context


# ------------------------------------------------------------
# 4. 답변 만들기 (노트북 8단계 ask_exaone_with_context)
# ------------------------------------------------------------
def ask_exaone(question, context):
    import torch

    tokenizer, model = state["tokenizer"], state["model"]
    facts = simple_answer(context)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"사용자 질문:\n{question}\n\n[확인된 사실]\n{facts}"},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(next(model.parameters()).device) for k, v in inputs.items()}

    with gen_lock, torch.no_grad():  # 한 번에 한 질문씩 생성
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )

    comment = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    comment = comment.split("</think>")[-1].strip()

    # 사실에 없는 큰 숫자(건수·인원)가 나오면 해석을 버림
    known = set(re.findall(r"\d+", facts.replace(",", "")))
    made_up = [n for n in re.findall(r"\d{3,}", comment.replace(",", "")) if n not in known]
    if not comment or made_up:
        return facts
    return f"{facts}\n\n💬 {comment}"


def simple_answer(context):
    # 모델이 없거나 준비 중일 때 : API 값을 그대로 요약
    lines = [f"[{context['자치구']}]"]

    beds = context.get("실시간_병상")
    if isinstance(beds, str):
        lines.append(f"실시간 병상 : {beds}")
    elif beds:
        lines.append(f"실시간 응급실 병상 (기준 {beds['기준시각'] or '수집 전'})")
        hospitals = beds["hospitals"]
        if not hospitals and beds["인접구_병원"]:
            lines.append("관내 응급실이 없어 인접 구 병원을 안내합니다.")
            hospitals = beds["인접구_병원"]
        if not hospitals:
            lines.append("- 아직 수집된 병원 정보가 없습니다.")
        for h in hospitals:
            n = h.get("Available_Beds")
            lines.append(f"- {h.get('Hospital_Name')} : {'확인 불가' if n is None else str(n) + '개'}")

    tr = context.get("이송건수_예측")
    if tr and tr["예측값"]:
        pairs = [(m, v) for m, v in zip(tr["예측월"], tr["예측값"]) if v is not None]
        lines.append(f"월별 이송 건수 예측 ({tr['사용모델']})")
        lines += [f"- {m} : {v:,}건" for m, v in pairs]

        top, low = max(pairs, key=lambda x: x[1]), min(pairs, key=lambda x: x[1])
        change = (pairs[-1][1] - pairs[0][1]) / pairs[0][1] * 100
        lines.append(f"가장 많은 달 {top[0]} / 가장 적은 달 {low[0]} / "
                     f"{pairs[0][0]} 대비 {pairs[-1][0]} {change:+.1f}%")

        recent = [(m, v) for m, v in zip(tr["최근_실제월"], tr["최근_실제값"]) if v is not None]
        if recent:
            lines.append("최근 실제 : " + ", ".join(f"{m} {v:,}건" for m, v in recent))

    pop = context.get("생활인구_일최대")
    if pop and pop["예측값"]:
        lines.append(f"생활인구 일최대 예측 ({pop['날짜'][-1]}) : {pop['예측값'][-1]:,}명")

    return "\n".join(lines)


# ------------------------------------------------------------
# 5. Flask 연결
# ------------------------------------------------------------
def init_chatbot(app):
    # 서버 시작과 동시에 모델을 미리 불러옴 (debug 재시작용 부모 프로세스는 제외)
    if os.getenv("CHAT_PRELOAD", "1") == "1" and (
        not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        threading.Thread(target=load_model, daemon=True).start()

    @app.get("/api/chat/status")
    def chat_status():
        return jsonify(status=state["status"], model=MODEL_ID, error=state["error"])

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        question = str(body.get("message", "")).strip()[:300]
        if not question:
            return jsonify(error="질문을 입력해 주세요."), 400

        found = find_district(question, None)
        topics = find_topics(question)

        # 구 이름도, 데이터 관련 단어도 없으면 안내 문구
        if not found and not topics:
            return jsonify(answer=GUIDE, source="guide", district=None)

        district = found or body.get("district") or ALL
        topics = topics or ["beds", "transport"]  # 구 이름만 있으면 병상 + 이송 예측

        try:
            context = build_context(app, district, topics)
        except Exception as e:
            print("[CHATBOT] 데이터 조회 실패 :", repr(e))
            return jsonify(answer=f"데이터를 불러오지 못했습니다. ({e})", source="error",
                           district=district)

        if state["status"] == "ready":
            try:
                return jsonify(answer=ask_exaone(question, context), source="exaone",
                               district=district)
            except Exception as e:
                print("[CHATBOT] 생성 실패 :", e)

        if state["status"] == "waiting":
            threading.Thread(target=load_model, daemon=True).start()
        try:
            answer = simple_answer(context)
        except Exception as e:
            print("[CHATBOT] 요약 실패 :", repr(e))
            answer = json.dumps(context, ensure_ascii=False, indent=1)
        return jsonify(answer=answer, source="summary", district=district)

    print("[CHATBOT] /api/chat 연결 완료 · 모델 :", MODEL_ID)
    return app
