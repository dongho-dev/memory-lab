# 실험 기록

항목마다: **바꾼 것**(변수 하나) · **가설** · **결과**(`results/REPORT.md`에서 옮김) · **해석** · **다음**.
지난 항목은 고치지 않고, 새 항목을 아래에 추가한다.

---

## 000 · Stage 0 기준선 (실행 전)

- **바꾼 것**: 없음. 기준선을 세운다.
- **설정**: LongMemEval cleaned, 서브셋 `subsets/dev42.json` (6개 유형 × 6 + 답변 보류 6), 답변 모델 `claude-sonnet-5-5` (effort medium), 판정 `claude-sonnet-5-5` (effort low)
- **실행**: `bash scripts/run_baselines.sh`
- **가설**
  - `raw_search` (top_k=10)는 `full_context`보다 토큰을 훨씬 적게 쓰면서 정답률은 일부만 잃는다.
  - 가장 많이 지는 곳은 여러 세션을 엮어야 하는 multi-session과 시간 추론(TR).
  - `oracle_full`(근거 세션만)과 `full_context`의 차이 = 긴 이력 속에서 읽기가 흐려지는 정도.
  - `raw_search`의 근거 재현율이 낮은 유형은 검색 실패, 재현율은 높은데 틀린 유형은 읽기 실패.
- **결과**: _실행 후 기록_
- **해석**:
- **다음**:

---

## 001 · Stage 0 기준선 실행 (구독 백엔드, full_context 제외)

- **바꾼 것**: 000의 계획에서 실행 방식만 바꿨다. 모델 호출을 Anthropic API에서 로컬 Claude Code CLI(`claude -p`, 구독)로 바꾸고, `full_context`(_s 전체 이력)는 빼고 돌렸다. 근거는 `docs/decisions.md` 2026-11-08 항목.
- **설정**: 서브셋 `subsets/dev42.json`(42문항: 6개 유형 × 6 + 답변 보류 6), 답변 `claude-sonnet-5-5` effort medium, 판정 `claude-sonnet-5-5` effort low. 둘 다 `--backend claude-code`, `--setting-sources ""`.
- **실행**: `bash scripts/run_baselines.sh` (2026-11-08)
- **결과** (`results/REPORT.md`에서 옮김)

| run | acc % | SSU | SSA | SSP | MS | KU | TR | ABS | in tok/q | evidence recall % |
|---|---|---|---|---|---|---|---|---|---|---|
| oracle_full | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 8,263 | 100 |
| raw_search_k10 | 86 | 100 | 100 | 50 | 50 | 100 | 100 | 100 | 8,646 | 92 |
| no_memory | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 100 | 1,041 | 0 |

- **해석**
  - 근거 세션만 주면 42문항을 전부 맞힌다(oracle_full 100%). 이 서브셋에서는 읽기 능력이 병목이 아니다. 남는 차이는 "기억에서 무엇을 꺼내 주느냐"에서 나온다.
  - 원문 검색 상위 10개만으로 86%. raw_search가 틀린 6문항 가운데:
    - 검색 실패 2문항 (SSP, 근거 재현율 0). 선호를 묻는 질문은 질문 문장과 근거 대화의 단어가 겹치지 않아 BM25가 못 찾는 것으로 보인다.
    - 근거를 찾고도 틀린 4문항 (SSP 1, MS 3, 재현율 0.5~1.0). 여러 세션을 합산하거나 연결해야 하는 질문에서, 잘린 조각만 보고 "모른다"고 하거나 일부만 센다.
  - no_memory는 답변 보류 6문항과 SSA 1문항만 맞힌다. 기억 없이 맞힐 수 있는 문제는 거의 없다.
  - 입력 토큰에는 Claude Code의 고정 오버헤드(호출당 약 940)가 들어 있다. 시스템 간 비교에는 영향이 같다.
  - 주의: 유형마다 6문항뿐이라 50% = 3/6. 차이 하나가 17%p다. 큰 결론은 문항을 늘려서 확인해야 한다.
- **다음**: 1위 실패 유형은 MS(합산·연결)와 SSP(선호 검색). 한 번에 변수 하나 원칙에 따라 후보는 (a) top_k 늘리기, (b) 조각 대신 세션 단위로 넣기, (c) 선호 질문용 질의 확장. 가장 작은 것은 (a).

---

## 002 · Stage 0 기준선, 답변 모델 Haiku

- **바꾼 것**: 답변 모델만 `claude-sonnet-5-5` → `claude-haiku-5-5`. 나머지(서브셋, 프롬프트, 판정 Sonnet low, 구독 백엔드)는 001과 같다.
- **실행**: `MODEL=claude-haiku-5-5 bash scripts/run_baselines.sh` (2026-11-08)
- **결과** (001 Sonnet과 나란히)

| run | acc % | SSU | SSA | SSP | MS | KU | TR | ABS | in tok/q |
|---|---|---|---|---|---|---|---|---|---|
| oracle_full@haiku | 95 | 100 | 100 | 100 | 83 | 100 | 83 | 100 | 8,284 |
| oracle_full@sonnet | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 8,263 |
| raw_search_k10@haiku | 83 | 100 | 100 | 50 | 33 | 100 | 100 | 100 | 8,671 |
| raw_search_k10@sonnet | 86 | 100 | 100 | 50 | 50 | 100 | 100 | 100 | 8,646 |
| no_memory@haiku | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 83 | 1,060 |
| no_memory@sonnet | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 100 | 1,041 |

- **해석**
  - Haiku는 근거 세션을 다 줘도 2문항을 틀린다(MS 1, TR 1). Sonnet과 달리 읽기(합산·날짜 계산)가 병목이 되는 지점이 생긴다. 미리 정리해 주는 메모리 층이 Haiku에서 더 이득일 수 있다는 가설과 맞는 방향.
  - raw_search에서는 Sonnet과 1문항 차이(MS). 검색으로 못 찾는 SSP 2문항은 모델과 상관없이 똑같이 틀린다.
  - no_memory@haiku가 답변 보류 1문항을 틀렸다. 기억이 없는데 지어낸 답을 했다는 뜻.
  - 주의: 유형당 6문항. 1문항 = 17%p.
- **다음**: 노션 L1~L5 계층 시스템을 MemorySystem으로 옮겨 Haiku·Sonnet에서 raw_search와 비교 (설계 확정 대기).

---

## 003 · Stage 0 기준선, 답변 모델 Opus (opus-medium-01)

- **바꾼 것**: 답변 모델만 `claude-opus-5-5`(effort medium). 나머지는 001과 같다.
- **실행**: `MODEL=claude-opus-5-5 bash scripts/run_baselines.sh` (2026-11-08). Haiku max·Sonnet xhigh 실행과 동시에 돌았다(PC 부하 높음, 결과에는 영향 없음).
- **결과**

| run | acc % | SSU | SSA | SSP | MS | KU | TR | ABS | in tok/q |
|---|---|---|---|---|---|---|---|---|---|
| oracle_full@opus | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 8,255 |
| raw_search_k10@opus | 88 | 100 | 100 | 67 | 50 | 100 | 100 | 100 | 8,644 |
| no_memory@opus | 19 | 0 | 33 | 0 | 0 | 0 | 0 | 100 | 1,040 |

- **해석**: 세 모델(medium) raw_search = Haiku 83 / Sonnet 86 / Opus 88, 천장 = 95 / 100 / 100. 모델이 좋아져도 검색이 못 꺼낸 문항은 그대로 틀린다. Sonnet 이상에서는 개선 여지가 거의 전부 검색 쪽에 있다.
- **다음**: haiku-max-01, sonnet-xhigh-01 결과로 effort 효과 확인.

---

## 004 · Stage 0 기준선, Sonnet effort xhigh (sonnet-xhigh-01)

- **바꾼 것**: 답변 effort만 medium → xhigh (모델 `claude-sonnet-5-5`). 001과 비교.
- **실행**: `MODEL=claude-sonnet-5-5 EFFORT=xhigh bash scripts/run_baselines.next.sh` (2026-11-08, Opus·Haiku max와 동시)
- **결과**

| run | acc % | SSU | SSA | SSP | MS | KU | TR | ABS | in tok/q |
|---|---|---|---|---|---|---|---|---|---|
| oracle_full@sonnet-xhigh | 98 | 100 | 100 | 83 | 100 | 100 | 100 | 100 | 8,261 |
| raw_search_k10@sonnet-xhigh | 86 | 100 | 100 | 50 | 50 | 100 | 100 | 100 | 8,646 |
| no_memory@sonnet-xhigh | 17 | 0 | 17 | 0 | 0 | 0 | 0 | 100 | 1,041 |

- **해석**: 더 오래 생각해도 점수는 그대로(천장은 1문항 감소, 잡음 범위). raw_search 출력 토큰 +60%, 시간 +30%. 이 서브셋에서는 Sonnet effort를 올릴 이유가 없다. 검색이 못 꺼낸 문항은 생각을 더 해도 못 맞힌다.

## 관찰 · 켜 둔 claude에서 /clear (2026-11-08)

- `claude -p --input-format stream-json --output-format stream-json`로 프로세스 하나를 켜 두고 질문 사이에 `/clear`를 보내는 방식을 Haiku로 시험했다.
- clear 전에는 앞 내용을 기억하고(이름·숫자 답함), clear 뒤에는 "UNKNOWN"으로 답했다. 4번 반복해도 같았다.
- clear 뒤 입력 토큰은 약 1,040으로 일정하다(한 번 켜고 끄는 방식은 약 920). 약 120토큰의 고정 찌꺼기가 남지만 쌓이지 않는다. 그래서 같은 실험 안에서 두 방식을 섞으면 토큰 비교가 어긋난다.
- 질문당 약 2~3.5초로, 한 번씩 켜는 방식(6~10초)보다 빠르다.

---

## 005 · Stage 0 기준선, Haiku effort max (haiku-max-01)

- **바꾼 것**: 답변 effort만 medium → max (모델 `claude-haiku-5-5`). 002와 비교.
- **실행**: `MODEL=claude-haiku-5-5 EFFORT=max bash scripts/run_baselines.sh` (2026-11-08, Opus·Sonnet xhigh와 동시)
- **결과**

| run | acc % | SSU | SSA | SSP | MS | KU | TR | ABS | in tok/q |
|---|---|---|---|---|---|---|---|---|---|
| oracle_full@haiku-max | 93 | 83 | 100 | 100 | 67 | 100 | 100 | 100 | 8,282 |
| raw_search_k10@haiku-max | 81 | 83 | 100 | 50 | 33 | 100 | 100 | 100 | 8,671 |
| no_memory@haiku-max | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 1,058 |

- **해석**: 최대로 생각해도 Haiku의 점수는 오르지 않는다(천장 95 → 93, 검색 83 → 81, 잡음 범위). 지어내던 답변 보류 1문항은 고쳐졌다. 출력 토큰 약 7배, 시간 약 2.5배. Sonnet xhigh(004)와 같은 결론이다. 이 서브셋에서 effort는 점수를 바꾸지 않고, 차이는 검색에서 나온다.

## 관찰 · 실행 방식 변경: `claude-code` → `claude-code-session` (2026-11-08)

- **바꾼 것**: 하네스의 기본 백엔드. 질문마다 `claude -p`를 새로 켜던 방식(`claude-code`)에서, 동시 작업 수만큼 프로세스를 켜 두고 매 호출 앞에 `/clear`를 보내는 방식(`claude-code-session`)으로. 예전 방식은 `--backend claude-code`로 남아 있다. 채점 동시 작업 기본값도 8 → 4.
- **확인**: raw_search_k10, Haiku medium, dev42 앞 8문항을 새 방식으로 다시 돌려 haiku-medium-01과 비교.
  - 정답 판정 8/8 동일.
  - 입력 토큰 평균 8,295 → 8,415 (+120, `/clear`가 남기는 고정 표시. 예상과 같다).
  - 문항당 시간 평균 5.8 → 4.9초. 처음 4문항은 프로세스를 켜는 시간이 들어가고, 그 뒤로는 2.7~4.8초.
  - 끝난 뒤 실험용 `claude` 프로세스가 남지 않는다(atexit로 정리).
- **주의**: 입력 토큰이 약 120 늘기 때문에 001~005(예전 방식)와 토큰을 직접 비교하면 안 된다. 정답률은 비교해도 된다. 다음 메모리 실험 때 비교 대상 기준선을 새 방식으로 다시 돌린다.
