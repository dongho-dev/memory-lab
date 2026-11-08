# sonnet-medium-01

- **답변 모델**: `claude-sonnet-5-5` · effort **medium**
- **무엇**: Stage 0 기준선 (no_memory · raw_search_k10 · oracle_full)
- **일지**: `EXPERIMENTS.md` 001
- **설정**: 서브셋 `subsets/dev42.json`(42문항 = 6개 유형 × 6 + 답변 보류 6), 판정 `claude-sonnet-5-5` effort low(LongMemEval 판정 프롬프트 원문), 구독 백엔드(`claude -p`, `--setting-sources ""`).
- 입력 토큰에는 Claude Code 고정 오버헤드(호출당 약 940)가 들어 있다. 유형당 6문항이라 1문항 = 17%p.
- 유형: SSU 단일 세션·사용자 / SSA 단일 세션·어시스턴트 / SSP 단일 세션·선호 / MS 여러 세션 / KU 지식 갱신 / TR 시간 추론 / ABS 답변 보류

| 시스템 | 정답률 % | SSU | SSA | SSP | MS | KU | TR | ABS | 입력 tok/q | 저장 tok/q | 근거 재현율 % | 실험 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle_full (천장) | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 8,263 | 0 | 100 | 001 |
| raw_search_k10 | 86 | 100 | 100 | 50 | 50 | 100 | 100 | 100 | 8,646 | 0 | 92 | 001 |
| no_memory (바닥) | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 100 | 1,041 | 0 | 0 | 001 |

## 메모
- 근거만 주면 전부 맞힌다. 이 서브셋에서 Sonnet은 읽기가 병목이 아니다.
- raw_search 오답 6: 검색 실패 2(SSP, 재현율 0), 찾고도 틀림 4(SSP 1, MS 3).
