# sonnet-xhigh-01

- **답변 모델**: `claude-sonnet-5-5` · effort **xhigh**
- **무엇**: Stage 0 기준선 (no_memory · raw_search_k10 · oracle_full)
- **일지**: `EXPERIMENTS.md` 004
- **설정**: 서브셋 `subsets/dev42.json`(42문항 = 6개 유형 × 6 + 답변 보류 6), 판정 `claude-sonnet-5-5` effort low(LongMemEval 판정 프롬프트 원문), 구독 백엔드(`claude -p`, `--setting-sources ""`).
- 입력 토큰에는 Claude Code 고정 오버헤드(호출당 약 940)가 들어 있다. 유형당 6문항이라 1문항 = 17%p.
- 유형: SSU 단일 세션·사용자 / SSA 단일 세션·어시스턴트 / SSP 단일 세션·선호 / MS 여러 세션 / KU 지식 갱신 / TR 시간 추론 / ABS 답변 보류

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 저장 tok/q | 근거 재현율 % | 실험 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle_full (천장) | 98 | 100 | 100 | 83 | 100 | 100 | 100 | 100 | 8,261 | 0 | 100 | 004 |
| raw_search_k10 | 86 | 100 | 100 | 50 | 50 | 100 | 100 | 100 | 8,646 | 0 | 92 | 004 |
| no_memory (바닥) | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 100 | 1,041 | 0 | 0 | 004 |

## 메모
- medium(sonnet-medium-01)과 비교: 검색·바닥은 같고, 천장은 1문항 덜 맞혔다(SSP). xhigh의 이득은 보이지 않는다.
- 대신 raw_search 기준 출력 토큰 127 → 204(+60%), 문항당 시간 7.0 → 9.1초.
