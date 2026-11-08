# 실험 결과 문서

문서 하나 = 실험 하나. 이름은 `<답변 모델>-<effort>-<번호>`이고, 번호는 모델·effort 조합마다 따로 센다.
예: `haiku-medium-01` = Haiku, effort medium으로 한 첫 실험. 시간순 전체 일지는 `EXPERIMENTS.md`.

## 한눈에 보기 (정답률 %)

| 문서 | 무엇 | 바닥 no_memory | 검색 raw_search_k10 | 천장 oracle_full |
|---|---|---|---|---|
| [haiku-medium-01](haiku-medium-01.md) | Stage 0 기준선 | 12 | 83 | 95 |
| [sonnet-medium-01](sonnet-medium-01.md) | Stage 0 기준선 | 17 | 86 | 100 |
| [opus-medium-01](opus-medium-01.md) | Stage 0 기준선 | 19 | 88 | 100 |
| [haiku-max-01](haiku-max-01.md) | Stage 0 기준선 | 14 | 81 | 93 |
| [sonnet-xhigh-01](sonnet-xhigh-01.md) | Stage 0 기준선 | 17 | 86 | 98 |
