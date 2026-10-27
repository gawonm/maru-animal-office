# 🌸 마루네 동물 오피스

강아지·고양이·북극여우·토끼 직원들이 일하는 픽셀아트 AI 오피스.
업무를 던져주면 팀장 마루가 나눠주고, 각자 Claude로 진짜 결과물을 만들어 보고해요.

- 1F 라운지(휴식) · 2F 사무실(업무) · 3F 옥상정원(산책)을 엘리베이터로 이동
- 동숲풍 대화창 + 말소리, 출근부, 결과 보고서, 업무 일지

## 실행

필요한 것: Python 3.9+, 그리고 로그인된 [Claude Code](https://claude.com/claude-code) (`claude` 명령)

```bash
# macOS
python3 server.py

# Windows
python server.py
```

브라우저에서 http://127.0.0.1:8790/ai-office.html 열기.

## AI 연결 방식

`server.py`가 자동으로 고릅니다. 자격 증명은 서버 쪽에만 있고 브라우저로는 안 넘어가요.

| 순서 | 방식 | 비용 |
|---|---|---|
| 1 | Claude Code CLI (`claude -p`) | Claude 구독 사용량 |
| 2 | `anthropic` SDK (`pip install anthropic` + `ant auth login` 또는 `ANTHROPIC_API_KEY`) | API 크레딧 |
| - | 둘 다 없으면 | 연출 모드 (AI 답변 없이 움직임만) |

팀장 마루가 업무를 보고 꼭 필요한 팀원만(1~4명) 불러요. 나머지는 라운지에서 쉬어요.
Claude 호출 수 = 팀장 분배 1 + 참여 팀원 수 + 최종 보고 1 (참여자가 1명이면 최종 보고 생략) → 업무당 2~6번.

## 직원 바꾸기

`ai-office.html` 위쪽 `STAFF` 배열에서 이름·역할·털색·말버릇·동물 종류(`species`: 없으면 강아지 / `cat` / `fox` / `rabbit`)를 바꾸면 돼요.
