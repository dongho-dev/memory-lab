# memory-lab

LLM 에이전트의 장기 메모리를 **한 층씩, 측정하면서** 만들어 가는 실험 저장소입니다.

가장 단순한 메모리(원문 검색)를 기준선으로 두고, 새 층(노트, 인덱스, 정리 등)을 하나씩 붙여 같은 평가셋에서 비교합니다. 기준선보다 정답률이 오르거나 토큰이 줄어든 층만 남깁니다.

## 원칙

1. **측정이 먼저.** 모든 변경은 같은 평가셋, 같은 답변 프롬프트에서 숫자로 비교합니다.
2. **한 번에 변수 하나.** 바꾼 것과 결과는 [`EXPERIMENTS.md`](EXPERIMENTS.md)에 남깁니다.
3. **층은 자리를 벌어야 남습니다.** 기준선을 이기지 못하면 뺍니다.
4. **이겨야 할 상대는 가장 단순한 메모리**, 원문 검색입니다.

## 지금까지의 결과

[LongMemEval](https://github.com/xiaowu0162/LongMemEval) 서브셋 42문항(dev42), 정답률(%). 자세한 내용은 [`docs/results/`](docs/results/README.md).

| 답변 모델 · effort | 기억 없음 (하한) | 원문 검색 top 10 | **자유 검색** | 근거 세션만 (상한) | 자유 검색 입력 토큰/문항 |
|---|---|---|---|---|---|
| Haiku · medium | 12 | 83 | **95** | 95 | 45k |
| Haiku · max | 14 | 81 | **95** | 93 | 104k |
| Sonnet · medium | 17 | 86 | **98** | 100 | 22k |
| Sonnet · xhigh | 17 | 86 | **100** | 98 | 37k |
| Opus · medium | 19 | 88 | **98** | 100 | 19k |
| Opus · high | – | – | **98** | – | 23k |

- **자유 검색**: 지난 대화를 세션별 파일로 펼쳐 두고, 모델이 Read·Grep·Glob·Bash로 알아서 찾게 합니다. 찾는 방법과 횟수는 정해 주지 않습니다.
- 자유 검색은 모든 조합에서 원문 검색보다 10~14%p 높고, 상한과 같거나 1문항 차이입니다. 대신 입력 토큰이 2~12배 듭니다. 강한 모델일수록 적게 찾습니다(Opus 2.8걸음, Haiku medium 4.5걸음).
- dev42는 유형당 6문항이라 1문항이 17%p입니다. 이제 상한에 붙어서, 더 큰 서브셋(dev100, dev250)과 더 긴 이력(LongMemEval `_m`)으로 넘어갑니다.

## 메모리 시스템

| 시스템 | 하는 일 | 역할 |
|---|---|---|
| `no_memory` | 질문만 봅니다 | 하한 |
| `raw_search` | 지난 대화를 라운드(사용자 발화 + 이어지는 답) 단위로 BM25 검색해 상위 k개를 시간순으로 넣습니다 | **이겨야 할 기준선** |
| `full_context` | 이력 전체를 넣습니다 | 비용 참고선 |
| `full_context` + oracle 데이터 | 정답 근거가 든 세션만 넣습니다 | 상한 (검색이 완벽할 때) |
| `agentic_search` | 모델이 검색어를 정해 BM25에 여러 번 묻고, 필요하면 세션 전체를 읽습니다 | 비교용 (도구가 정해진 검색) |
| `agentic_files` | 세션마다 파일 하나로 펼쳐 두고, Claude Code가 Read·Grep·Glob(`bash=true`면 Bash까지)으로 알아서 찾습니다 | **Stage 1 자유 검색** |

`agentic_files`는 걸음마다 모델이 적은 이유, 쓴 도구와 입력, 받은 결과, 그 결과에 정답 발언이 있었는지를 `traces.jsonl`에 남깁니다. 시스템 프롬프트로 "폴더 밖과 네트워크에 접근하지 말라"고만 하고 막지는 않습니다. 대신 기록된 모든 도구 호출을 검사해 폴더 밖 접근을 표시합니다(지금까지 0건).

## 평가

- **데이터**: LongMemEval (2025-09 cleaned). `_s`는 질문당 약 50세션(약 11.5만 토큰)의 대화 이력입니다.
- **서브셋** (서로 겹치지 않음, 시드 고정)
  - [`subsets/dev42.json`](subsets/dev42.json): 6개 유형 × 6문항 + 답변 보류 6문항. 방식을 빨리 바꿔 보는 개발용
  - [`subsets/dev100.json`](subsets/dev100.json), [`subsets/dev250.json`](subsets/dev250.json): 500문항의 유형 비율대로 뽑은 확인용
- **판정**: LongMemEval 공식 판정 프롬프트를 그대로 쓰고, 판정 모델만 Claude(`claude-sonnet-5-5`, effort low)입니다.
- **지표**
  - 정답률: 전체, 유형별
  - 질문당 입력 토큰, 메모리 구축 토큰(쓰기 경로에서 LLM을 쓰는 층의 비용)
  - 근거 재현율: 메모리가 근거 세션을 꺼냈는가. 낮으면 검색 실패, 높은데 틀리면 읽기 실패
  - 정답 발언 재현율: 정답이 든 발언 자체가 모델에게 보였는가 (세션 단위보다 엄격)
  - 걸음 수: 모델이 직접 찾는 시스템에서 도구를 몇 번 썼는가

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q                 # 목 모델로 전체 흐름 확인 (모델 호출 없음)

bash scripts/download_data.sh       # LongMemEval _s, oracle 내려받기 (약 280MB)
bash scripts/run_baselines.sh       # 비용 추정 → 확인 → 실행 → 채점 → results/REPORT.md
```

옵션:

```bash
MODEL=claude-haiku-5-5 EFFORT=max bash scripts/run_baselines.sh   # 답변 모델·effort 바꾸기
FULL=1 bash scripts/run_baselines.sh                              # full_context(질문당 약 16.5만 토큰)도 실행
BACKEND=api bash scripts/run_baselines.sh                         # Anthropic API로 실행
```

하나씩 돌릴 때:

```bash
python -m memlab.run --system raw_search --param top_k=10 --subset subsets/dev42.json --dry-run
python -m memlab.run --system raw_search --param top_k=10 --subset subsets/dev42.json --name raw_search_k10
python -m memlab.evaluate results/raw_search_k10
python -m memlab.report results
```

같은 명령을 다시 실행하면 이어서 합니다. 끝난 질문은 건너뛰고 실패한 질문만 다시 시도합니다.

자유 검색과 그 과정 보기:

```bash
python -m memlab.run --system agentic_files --param bash=true --subset subsets/dev42.json \
  --model claude-haiku-5-5 --effort medium --name agentic_files_bash@haiku-5-5-medium
python -m memlab.evaluate results/agentic_files_bash@haiku-5-5-medium
python -m memlab.trace results/agentic_files_bash@haiku-5-5-medium               # 요약
python -m memlab.trace results/agentic_files_bash@haiku-5-5-medium --show wrong  # 틀린 문항을 한 걸음씩
```

새 서브셋 만들기: `python -m memlab.subset --total 100 --exclude subsets/dev42.json --out subsets/dev100.json`

### 모델 호출 방식 (`--backend`)

| 백엔드 | 방식 | 비용 |
|---|---|---|
| `claude-code-session` (기본) | 로컬 [Claude Code](https://claude.com/claude-code) 프로세스 몇 개를 켜 두고, 호출마다 `/clear`로 대화를 비웁니다 | Claude 구독 사용량 |
| `claude-code` | 호출마다 `claude -p`를 새로 실행합니다 (느리고 PC 부하가 큼) | Claude 구독 사용량 |
| `api` | Anthropic API를 직접 부릅니다 (`ANTHROPIC_API_KEY` 필요) | 토큰당 과금 |

Claude Code 백엔드는 도구, MCP 서버, 사용자 설정(`--setting-sources ""`)을 모두 끄고 공통 답변 프롬프트만 씁니다. 그래서 개인 설정이 답변에 섞이지 않습니다. 호출당 약 1,000토큰의 고정 오버헤드가 입력 토큰에 포함되므로, 토큰은 같은 백엔드끼리만 비교합니다.

## 새 메모리 층 추가하기

`memlab/systems/`에 `MemorySystem`을 구현하고 `SYSTEMS`에 등록합니다.

```python
class MyMemory(MemorySystem):
    name = "my_memory"

    def reset(self): ...                       # 질문마다 새 사용자
    def ingest(self, session): ...             # 쓰기 경로: 세션이 시간순으로 하나씩 들어옵니다
    def build_context(self, question, question_date) -> Retrieval: ...   # 읽기 경로
```

`ingest`에서 LLM을 쓰면 그 토큰을 `Retrieval.ingest_*_tokens`에 담습니다. 리포트에 메모리 구축 비용으로 따로 표시됩니다. 모든 시스템이 같은 답변 프롬프트를 쓰므로, 점수 차이는 `<memory>`에 무엇을 넣었는지에서만 나옵니다.

## 구조

```
memlab/
  data.py          LongMemEval 로딩 (질문, 세션, 근거 표시)
  systems/         메모리 시스템 (base.py 인터페이스, baselines.py 기준선,
                   agentic.py BM25 도구 검색, agentic_files.py 자유 검색)
  bm25.py          의존성 없는 BM25
  prompts.py       공통 답변 프롬프트, LongMemEval 판정 프롬프트
  llm.py           모델 호출 백엔드, dry-run 추정기, 테스트용 목 모델
  run.py           시스템 실행 → results/<name>/hypotheses.jsonl
  evaluate.py      판정 → eval.jsonl, summary.json
  report.py        전체 비교표 → results/REPORT.md
  subset.py        고정 서브셋 생성 (유형별 같은 수, 또는 전체 비율대로)
  trace.py         모델이 직접 찾은 과정 보기 (traces.jsonl)
scripts/           데이터 다운로드, 기준선 일괄 실행
subsets/           고정 평가 서브셋
tests/             목 모델 기반 전체 흐름 테스트
docs/results/      실험별 결과 문서 (<모델>-<effort>-<번호>.md)
docs/decisions.md  설계 결정과 근거
EXPERIMENTS.md     시간순 실험 일지
```

## 로드맵

방향: 검색 알고리즘을 다듬는 것보다, **모델이 스스로 뒤져 가며 효율적으로 찾을 수 있는 메모리**를 만드는 데 집중합니다. 사람이 설계하는 건 무엇을 어떤 형태로 남길지, 모델에게 줄 도구, 언제 꺼내 쓸지입니다.

- **Stage 0 · 기준선** (완료). 기억 없음 / 원문 검색 / 상한
- **Stage 1 · 모델이 직접 검색** ← 지금. 원문을 파일로 펼쳐 두고 모델이 원하는 만큼 찾게 합니다. dev42에서 상한에 도달했고, 더 큰 서브셋과 더 긴 이력(`_m`, 질문당 약 150만 토큰)에서 버티는지 확인 중입니다.
- **Stage 2 · 찾기 쉬운 저장**: 세션이 끝나면 노트를 남깁니다. 항목마다 날짜와 출처(직접 발언 / 확정 / 검토안 / AI 해석)를 붙입니다. 모델이 더 적은 왕복으로 찾게 되는지 봅니다.
- **Stage 3 · 인덱스·주입층**: 작은 목차를 항상 주고, 모델이 필요할 때 펼쳐 봅니다.
- **Stage 4 · 정리(드리밍)**: 원문과 대조해 고치고, 합치고, 잊습니다. 변경은 diff로 남겨 사람이 승인합니다.
- **Stage 5 · 자체 평가셋**: LongMemEval이 보지 않는 것. 출처 혼동, 무관한 질문에 끼어들기, 오래된 사실.
- **Stage 6 · 실전 연결**: MCP 서버로 감싸 실제 에이전트에 붙입니다.

Stage 2 이후는 계획입니다. 각 단계는 앞 단계를 숫자로 이겨야 다음으로 갑니다.

## 출처와 라이선스

- 코드: MIT ([`LICENSE`](LICENSE))
- LongMemEval: Wu et al., ICLR 2025. 데이터와 판정 프롬프트, MIT ([`licenses/LongMemEval-LICENSE.txt`](licenses/LongMemEval-LICENSE.txt))
- 참고: Anthropic, [*The components of agent memory*](https://www.anthropic.com/research/components-of-agent-memory), 2026-11-06
