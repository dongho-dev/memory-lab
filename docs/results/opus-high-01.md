# opus-high-01

- **답변 모델**: `claude-opus-5-5` · effort **high**
- **무엇**: Stage 1 자유 검색 — `agentic_files` `bash=true` (실행 이름 `agentic_files_bash@opus-5-5-high`). 이 조합은 기준선을 돌리지 않았다.
- **일지**: `EXPERIMENTS.md` 007
- **설정**: opus-medium-02와 같다(dev42, 판정 Sonnet low, `claude-code-session`, Read·Grep·Glob·Bash, 횟수 제한 없음, 프롬프트로만 폴더 밖·네트워크 금지 + 기록 검사).

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 근거 재현율 % | 정답 발언 재현율 % | 걸음/q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agentic_files bash (자유 검색) | 98 | 100 | 100 | 100 | 100 | 100 | 83 | 100 | 22,598 | 99 | 90 | 3.2 |

## 메모
- 도구 사용: Grep 63, Bash 16, Read 14, Glob 1. 폴더 밖 접근 0/42.
- 틀린 문항: 982b5123(TR, 에어비앤비 예약 몇 달 전). medium과 같다. `Airbnb` Grep → 세션 하나 전체 읽기 → "3개월 전에 미리 예약"을 3개월 전으로 답함. "두 달 전 여행"이 적힌 다른 세션(‘Airbnb’ 단어 없음)을 찾지 않았다. Sonnet xhigh만 이 세션까지 찾아 맞혔다.
