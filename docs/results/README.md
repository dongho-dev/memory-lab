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

## Stage 1 · 자유 검색 (정답률 %)

모델이 파일로 펼친 기억을 Read·Grep·Glob·Bash로 직접 뒤진다(`agentic_files bash=true`). 같은 dev42.

| 문서 | 자유 검색 | 기본 검색 | 천장 | 입력 tok/q | 걸음/q |
|---|---|---|---|---|---|
| [haiku-medium-02](haiku-medium-02.md) | 95 | 83 | 95 | 45,214 | 4.5 |
| [haiku-max-02](haiku-max-02.md) | 95 | 81 | 93 | 104,365 | 7.8 |
| [sonnet-medium-02](sonnet-medium-02.md) | 98 | 86 | 100 | 21,773 | 3.0 |
| [sonnet-xhigh-02](sonnet-xhigh-02.md) | 100 | 86 | 98 | 36,958 | 5.0 |
| [opus-medium-02](opus-medium-02.md) | 98 | 88 | 100 | 18,582 | 2.8 |
| [opus-high-01](opus-high-01.md) | 98 | – | – | 22,598 | 3.2 |

## 더 큰 서브셋 (정답률 %, Haiku medium)

500문항 비율대로 새로 뽑은 확인용. dev42보다 어렵다(천장 95 → 85~92).

| 문서 | 서브셋 | 바닥 | 기본 검색 | 자유 검색 | 천장 |
|---|---|---|---|---|---|
| [haiku-medium-03](haiku-medium-03.md) | dev100 | 2 | 72 | 84 | 85 |
| [haiku-medium-03](haiku-medium-03.md) | dev250 | 6 | 78 | 89 | 92 |

## 기억 10배 (LongMemEval _m, dev42, Haiku medium)

| 문서 | 기본 검색 _s → _m | 자유 검색 _s → _m | 자유 검색 tok/q _s → _m |
|---|---|---|---|
| [haiku-medium-04](haiku-medium-04.md) | 83 → 71 | 95 → 88 | 45k → 71k |

