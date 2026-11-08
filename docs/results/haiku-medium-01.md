# haiku-medium-01

- **답변 모델**: `claude-haiku-5-5` · effort **medium**
- **무엇**: Stage 0 기준선 (no_memory · raw_search_k10 · oracle_full)
- **일지**: `EXPERIMENTS.md` 002
- **설정**: 서브셋 `subsets/dev42.json`(42문항 = 6개 유형 × 6 + 답변 보류 6), 판정 `claude-sonnet-5-5` effort low(LongMemEval 판정 프롬프트 원문), 구독 백엔드(`claude -p`, `--setting-sources ""`).
- 입력 토큰에는 Claude Code 고정 오버헤드(호출당 약 940)가 들어 있다. 유형당 6문항이라 1문항 = 17%p.
- 유형: SSU 단일 세션·사용자 / SSA 단일 세션·어시스턴트 / SSP 단일 세션·선호 / MS 여러 세션 / KU 지식 갱신 / TR 시간 추론 / ABS 답변 보류

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 저장 tok/q | 근거 재현율 % | 실험 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle_full (천장) | 95 | 100 | 100 | 100 | 83 | 100 | 83 | 100 | 8,284 | 0 | 100 | 002 |
| raw_search_k10 | 83 | 100 | 100 | 50 | 33 | 100 | 100 | 100 | 8,671 | 0 | 92 | 002 |
| no_memory (바닥) | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 83 | 1,060 | 0 | 0 | 002 |

## 메모
- 천장이 100%가 아니다. 근거를 다 줘도 합산(MS)·날짜 계산(TR)에서 1문항씩 틀린다. 미리 정리해 주는 층의 이득이 Sonnet보다 클 수 있다.
- no_memory가 답변 보류 1문항에서 답을 지어냈다.
