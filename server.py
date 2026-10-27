"""마루네 동물 오피스 로컬 서버.

ai-office.html 을 띄우고, /api/ask 로 들어온 요청에 Claude 로 답한다.

1순위: Claude Code CLI (claude -p) - API 크레딧 대신 Claude 구독 사용량으로 답함
2순위: anthropic SDK - API 크레딧 사용 (ANTHROPIC_API_KEY 또는 ant auth login)
어느 쪽이든 자격 증명은 서버 쪽에만 있고 브라우저에는 노출되지 않는다.

    python server.py                           # http://127.0.0.1:8790/ai-office.html
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    import anthropic
except ImportError:
    anthropic = None

PORT = int(os.environ.get("PORT", 8790))
MODEL = "claude-opus-5-5"
SPECIES = {"cat": "고양이", "fox": "북극여우", "rabbit": "토끼"}
# PATH 에 없을 때(맥에서 Finder/IDE 로 실행 등)를 대비해 기본 설치 위치도 찾아봄
CLAUDE = shutil.which("claude") or next(
    (p for p in map(os.path.expanduser, ["~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
     if os.access(p, os.X_OK)), None)
CLI_SLOTS = threading.Semaphore(3)  # ponytail: claude 프로세스는 무거워서 동시 3개로 제한, 느리면 늘리기

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 등 환경에서 자격 증명을 찾음
    return _client


def backend_label():
    return "Claude Code 구독" if CLAUDE else MODEL


def ai_ready():
    if CLAUDE:
        return True, ""
    if anthropic is None:
        return False, "anthropic 패키지가 없어요 (pip install anthropic)"
    try:
        get_client()
        return True, ""
    except Exception as e:  # 자격 증명이 없으면 생성 단계에서 실패
        return False, f"자격 증명이 없어요 - ant auth login 또는 API 키 ({type(e).__name__})"


def clip(v, n):
    return str(v or "")[:n]


def build_prompt(body):
    who = body.get("who") or {}
    name, role = clip(who.get("name"), 20), clip(who.get("role"), 20)
    animal = SPECIES.get(who.get("species"), "강아지")
    task, verb, notes = clip(body.get("task"), 300), clip(who.get("verb"), 40), clip(body.get("notes"), 8000)
    system = (
        f"너는 '마루네 동물 오피스'에서 일하는 {animal} 직원 '{name}'이고 담당은 {role}야. "
        f"말버릇은 \"{clip(who.get('quirk'), 60)}\". 귀엽고 다정한 반말 캐릭터 말투를 쓰되, "
        "내용은 실제로 쓸모 있게 구체적으로 써. 마크다운 제목 없이 짧은 문단이나 '- ' 목록만 써."
    )
    kind = body.get("kind")
    if kind == "plan":
        user = (f"팀장으로서 업무 \"{task}\"를 받았어. 팀원 목록: {notes}\n"
                "이 업무에 꼭 필요한 팀원만 골라. 간단한 업무면 1명, 커도 최대 4명. 필요 없는 팀원은 부르지 마.\n"
                "첫 줄은 정확히 '참여: 이름, 이름' 형식으로 쓰고, 다음 줄에 고른 팀원들에게 하는 한마디를 1~2문장으로 써.")
    elif kind == "summary":
        user = f"업무 \"{task}\"에 대한 팀원들의 결과야:\n\n{notes}\n\n팀장으로서 핵심만 4~6줄로 최종 보고해줘."
    else:
        user = f"팀장이 업무 \"{task}\" 중에서 너한테 '{verb}'를 맡겼어. 네 담당 결과물을 3~6줄로 써줘."
    return system, user


def ask_claude(body):
    system, user = build_prompt(body)
    resp = get_client().beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low"},  # 짧은 캐릭터 대사라 low 로 충분
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # 안전 필터로 거절되면 서버가 다른 모델로 대신 처리
    )
    if resp.stop_reason == "refusal":
        return None, "이 업무는 도와줄 수 없대요"
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text, ""


def ask_cli(body):
    """claude -p 로 답을 받는다. 프롬프트는 stdin 으로만 넘겨서 명령줄에 사용자 입력이 섞이지 않게 한다."""
    system, user = build_prompt(body)
    args = [CLAUDE, "-p", "--output-format", "json", "--effort", "low",
            "--tools", "", "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "",
            "--system-prompt", "You voice a character in a cute office game. Reply only with the requested text."]
    for attempt in range(2):
        try:
            with CLI_SLOTS:
                r = subprocess.run(args, input=f"{system}\n\n{user}", capture_output=True, text=True,
                                   encoding="utf-8", cwd=tempfile.gettempdir(), timeout=180)
        except subprocess.TimeoutExpired:
            return None, "Claude Code 응답이 너무 오래 걸려요"
        except OSError as e:
            print(f"claude -p 실행 실패: {e}", flush=True)
            return None, "Claude Code 실행에 실패했어요 (서버 콘솔 참고)"
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            print(f"claude -p rc={r.returncode}: {r.stderr[:300] or r.stdout[:300]}", flush=True)
            return None, "Claude Code 실행에 실패했어요 (서버 콘솔 참고)"
        if not data.get("is_error") and r.returncode == 0:
            return data.get("result", "").strip(), ""
        msg = str(data.get("result") or "")
        print(f"claude -p 오류: {msg[:300]}", flush=True)
        if not re.search(r"authenticat|oauth|login", msg, re.I):
            return None, f"Claude Code: {clip(msg, 80)}"  # 사용 한도 초과 등
        # 토큰 만료 순간 여러 프로세스가 동시에 갱신하면 하나만 성공함 → 잠깐 뒤 한 번 더
        time.sleep(2 + random.random() * 3)
    return None, "Claude Code 로그인이 만료됐어요 - 터미널에서 claude 실행 후 /login 하고 서버 재시작"


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, code, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/status":
            ok, why = ai_ready()
            return self.send_json(200, {"ai": ok, "why": why, "model": backend_label()})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/ask":
            return self.send_json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 20000:
            return self.send_json(413, {"error": "요청이 너무 커요"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json(400, {"error": "JSON 형식이 아니에요"})
        ok, why = ai_ready()
        if not ok:
            return self.send_json(503, {"error": why})
        if CLAUDE:
            text, err = ask_cli(body)
            return self.send_json(200, {"text": text} if text else {"error": err or "빈 답변이 왔어요"})
        try:
            text, err = ask_claude(body)
        except anthropic.AuthenticationError:
            return self.send_json(401, {"error": "API 키가 틀렸어요"})
        except anthropic.RateLimitError:
            return self.send_json(429, {"error": "요청이 너무 많아서 잠깐 쉬어야 해요"})
        except anthropic.APIStatusError as e:
            print(f"Claude API {e.status_code}: {e.message}", flush=True)
            if "credit balance" in str(e.message):
                return self.send_json(402, {"error": "API 크레딧이 부족해요 (Console > Plans & Billing에서 충전)"})
            return self.send_json(502, {"error": f"Claude API 오류 {e.status_code} (서버 콘솔 참고)"})
        except anthropic.APIConnectionError:
            return self.send_json(502, {"error": "인터넷 연결을 확인해 주세요"})
        if text is None:
            return self.send_json(200, {"error": err})
        return self.send_json(200, {"text": text})


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    ok, why = ai_ready()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949)에서 한글 출력 깨짐 방지
    print(f"http://127.0.0.1:{PORT}/ai-office.html  ({'진짜 AI 모드: ' + backend_label() if ok else '연출 모드 - ' + why})")
    ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=here)).serve_forever()
