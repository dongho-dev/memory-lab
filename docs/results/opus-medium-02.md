# opus-medium-02

- **답변 모델**: `claude-opus-5-5` · effort **medium**
- **무엇**: Stage 1 자유 검색 — `agentic_files` `bash=true` (실행 이름 `agentic_files_bash@opus-5-5-medium`)
- **일지**: `EXPERIMENTS.md` 006
- **설정**: 서브셋 `subsets/dev42.json`(42문항), 판정 `claude-sonnet-5-5` effort low(LongMemEval 판정 프롬프트 원문), 구독 백엔드 `claude-code-session`(켜 둔 프로세스 + 질문마다 `/clear`).
- **방식**: 질문마다 세션 약 50개를 파일(`sessions/<날짜>_<id>.md`)로 펼치고, Claude Code에 Read·Grep·Glob·Bash를 켜 준다. 찾는 방법·횟수는 지시하지 않는다. 시스템 프롬프트로 "폴더 밖과 네트워크 접근 금지"만 말하고, 기록된 모든 도구 호출을 검사한다(폴더 밖 접근 0/42).
- 유형당 6문항이라 1문항 = 17%p. 입력 토큰은 모델이 찾으며 읽은 양 전체(여러 번 호출 합)다.

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 근거 재현율 % | 정답 발언 재현율 % | 걸음/q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agentic_files bash (자유 검색) | 98 | 100 | 100 | 100 | 100 | 100 | 83 | 100 | 18,582 | 96 | 82 | 2.8 |

비교 ([opus-medium-01](opus-medium-01.md), 같은 모델·effort): 바닥 19 · 기본 검색 raw_search_k10 88 · 천장 oracle_full 100

## 메모
- 도구 사용: Grep 55, Bash 16, Read 3.
- 틀린 문항: 982b5123(TR).
