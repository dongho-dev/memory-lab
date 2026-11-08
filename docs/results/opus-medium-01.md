# opus-medium-01

- **답변 모델**: `claude-opus-5-5` · effort **medium**
- **무엇**: Stage 0 기준선 (no_memory · raw_search_k10 · oracle_full)
- **일지**: `EXPERIMENTS.md` 003
- **설정**: 서브셋 `subsets/dev42.json`(42문항 = 6개 유형 × 6 + 답변 보류 6), 판정 `claude-sonnet-5-5` effort low(LongMemEval 판정 프롬프트 원문), 구독 백엔드(`claude -p`, `--setting-sources ""`).
- 입력 토큰에는 Claude Code 고정 오버헤드(호출당 약 940)가 들어 있다. 유형당 6문항이라 1문항 = 17%p.
- 유형: SSU 단일 세션·사용자 / SSA 단일 세션·어시스턴트 / SSP 단일 세션·선호 / MS 여러 세션 / KU 지식 갱신 / TR 시간 추론 / ABS 답변 보류

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 저장 tok/q | 근거 재현율 % | 실험 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle_full (천장) | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 8,255 | 0 | 100 | 003 |
| raw_search_k10 | 88 | 100 | 100 | 67 | 50 | 100 | 100 | 100 | 8,644 | 0 | 92 | 003 |
| no_memory (바닥) | 19 | 0 | 33 | 0 | 0 | 0 | 0 | 100 | 1,040 | 0 | 0 | 003 |

## 메모
- 천장 100%로 Sonnet과 같다. 근거만 주면 다 맞힌다.
- raw_search는 Sonnet보다 1문항 많이 맞혔다(SSP). 검색으로 못 찾는 문항(재현율 0)은 여전히 틀린다.
- 세 모델의 raw_search 차이는 83 / 86 / 88로 1문항씩이다. 6문항 유형에서 1문항은 잡음 범위일 수 있다.
