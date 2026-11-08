# memory-lab

AI 에이전트를 위한 장기 메모리를 **한 층씩, 측정하면서** 만드는 실험 저장소입니다.

에이전트는 대화가 끝나면 잊습니다. 지난 대화를 모두 컨텍스트에 넣기에는 너무 길고, 정해진 검색으로 몇 조각만 꺼내 주면 필요한 것을 놓칩니다. 이 저장소는 **기억은 저장해 두고, 찾는 일은 모델에게 맡기는** 메모리를 만들고, 공개 벤치마크에서 숫자로 비교합니다.

## 어떻게 동작하나

```
지난 대화 (질문당 세션 수십~수백 개)
        │  쓰기: 메모리 시스템이 저장한다 (원문 그대로, 파일, 메모 등)
        ▼
   메모리 저장소
        │  읽기: 질문이 오면 메모리 시스템이 꺼내거나, 모델이 직접 뒤진다
        ▼
   답변 모델 ──▶ 답 ──▶ 판정 모델이 정답과 비교
```

- 모든 메모리 시스템은 같은 질문, 같은 판정으로 비교합니다. 점수 차이는 "무엇을 어떻게 남기고 꺼냈는가"에서만 나옵니다.
- 모델이 직접 찾는 시스템은 걸음마다 **왜 그렇게 했는지, 어떤 도구를 썼는지, 무엇을 받았는지**를 기록합니다. 점수만이 아니라 찾는 방식과 판단 과정을 봅니다.

## 원칙

1. **측정이 먼저.** 모든 변경은 같은 평가셋에서 숫자로 비교합니다.
2. **한 번에 변수 하나.** 바꾼 것과 결과는 [`EXPERIMENTS.md`](EXPERIMENTS.md)에 남깁니다.
3. **층은 자리를 벌어야 남습니다.** 앞 단계를 이기지 못하면 뺍니다.

## 메모리 시스템

| 시스템 | 하는 일 | 역할 |
|---|---|---|
| `no_memory` | 질문만 봅니다 | 하한 |
| `raw_search` | 지난 대화를 라운드 단위로 BM25 검색해 상위 k개를 넣습니다 | 기준선 |
| `full_context` | 이력 전체를 넣습니다. oracle 데이터와 쓰면 정답 근거 세션만 넣습니다 | 비용 참고선 / 상한 |
| `agentic_search` | 모델이 검색어를 정해 BM25에 여러 번 묻습니다 | 비교용 |
| `agentic_files` | 세션마다 파일 하나로 펼쳐 두고, 모델이 Read·Grep·Glob(`bash=true`면 Bash까지)으로 알아서 찾습니다 | 자유 검색 |
| `progress_md` | 모델이 지난 대화를 약 10만 토큰씩 순서대로 읽으며 자기 메모 `progress.md`를 자유롭게 쓰고, 답할 때 메모와 세션 파일을 함께 봅니다 | 외부 메모리 파일 (실험 중) |

모델이 직접 찾는 시스템(`agentic_*`, `progress_md`)은 Claude Code를 질문마다 빈 폴더에서 실행합니다. 시스템 프롬프트로 폴더 밖과 네트워크 접근을 금지하고, 기록된 모든 도구 호출을 검사해 폴더 밖 접근을 표시합니다.

## 평가

- **데이터**: [LongMemEval](https://github.com/xiaowu0162/LongMemEval) (2025-09 cleaned)
  - `_s`: 질문당 세션 약 50개, 약 16만 토큰
  - `_m`: 질문당 세션 약 500개, 약 160만 토큰. 어떤 모델의 컨텍스트에도 다 들어가지 않습니다
- **서브셋** (서로 겹치지 않음, 시드 고정)
  - `subsets/dev42.json`: 6개 유형 × 6문항 + 답변 보류 6문항. 방식을 빨리 바꿔 보는 개발용
  - `subsets/dev100.json`, `subsets/dev250.json`: 500문항의 유형 비율대로 뽑은 확인용
- **판정**: LongMemEval 공식 판정 프롬프트를 그대로 쓰고, 판정 모델만 Claude입니다.
- **지표**: 정답률(전체, 유형별), 질문당 입력 토큰, 메모리 구축 토큰, 근거 재현율, 정답 발언 재현율, 걸음 수

결과는 [`docs/results/`](docs/results/README.md)에, 시간순 일지는 [`EXPERIMENTS.md`](EXPERIMENTS.md)에 있습니다.

## 빠른 시작

설치하고, 모델 호출 없이 전체 흐름을 확인합니다.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

데이터를 받고 기준선을 돌립니다. 실행 전에 비용 추정을 보여 주고 확인을 받습니다.

```bash
bash scripts/download_data.sh
bash scripts/run_baselines.sh
```

답변 모델과 effort는 환경 변수로 바꿉니다: `MODEL=claude-haiku-5-5 EFFORT=max bash scripts/run_baselines.sh`

## 시스템 하나 돌리기

```bash
python -m memlab.run --system agentic_files --param bash=true --subset subsets/dev42.json \
  --model claude-haiku-5-5 --effort medium --name agentic_files_bash@haiku-5-5-medium --dry-run
python -m memlab.run --system agentic_files --param bash=true --subset subsets/dev42.json \
  --model claude-haiku-5-5 --effort medium --name agentic_files_bash@haiku-5-5-medium
python -m memlab.evaluate results/agentic_files_bash@haiku-5-5-medium
python -m memlab.report results
```

- `--dry-run`은 모델을 부르지 않고 토큰과 비용만 추정합니다.
- 같은 명령을 다시 실행하면 이어서 합니다. 끝난 질문은 건너뛰고 실패한 질문만 다시 시도합니다.
- 결과 폴더 이름에 모델과 effort를 붙입니다(`<시스템>@<모델>-<effort>`).

모델이 찾은 과정 보기:

```bash
python -m memlab.trace results/agentic_files_bash@haiku-5-5-medium
python -m memlab.trace results/agentic_files_bash@haiku-5-5-medium --show wrong
```

첫 줄은 요약(걸음 수, 쓴 도구, 정답 발언을 본 문항 수, 폴더 밖 접근)이고, `--show wrong`은 틀린 문항을 한 걸음씩 보여 줍니다.

### 큰 데이터(`_m`)

`_m` 파일은 2.7GB라 통째로 읽지 않고, 서브셋 문항만 뽑아 작은 파일로 씁니다.

```bash
bash scripts/download_data.sh m
pip install -e ".[m]"
python -m memlab.extract --data data/longmemeval_m_cleaned.json --subset subsets/dev42.json \
  --out data/longmemeval_m_dev42.json
python -m memlab.run --system agentic_files --param bash=true --data data/longmemeval_m_dev42.json \
  --subset subsets/dev42.json --model claude-haiku-5-5 --effort medium --out-dir results/m_dev42 \
  --name agentic_files_bash@haiku-5-5-medium
```

### 새 서브셋

```bash
python -m memlab.subset --total 100 --exclude subsets/dev42.json --out subsets/dev100.json
```

## 모델 호출 방식 (`--backend`)

| 백엔드 | 방식 | 비용 |
|---|---|---|
| `claude-code-session` (기본) | 로컬 [Claude Code](https://claude.com/claude-code) 프로세스 몇 개를 켜 두고, 호출마다 `/clear`로 대화를 비웁니다 | Claude 구독 사용량 |
| `claude-code` | 호출마다 `claude -p`를 새로 실행합니다 (느리고 PC 부하가 큼) | Claude 구독 사용량 |
| `api` | Anthropic API를 직접 부릅니다 (`ANTHROPIC_API_KEY` 필요) | 토큰당 과금 |

Claude Code 백엔드는 MCP 서버와 사용자 설정(`--setting-sources ""`)을 끄고, 시스템마다 정해진 도구만 켭니다. 개인 설정이 답변에 섞이지 않습니다. 호출당 약 1,000토큰의 고정 오버헤드가 있으므로 토큰은 같은 백엔드끼리만 비교합니다.

## 새 메모리 시스템 추가하기

`memlab/systems/`에 `MemorySystem`을 구현하고 `memlab/systems/__init__.py`의 `SYSTEMS`에 등록합니다.

```python
class MyMemory(MemorySystem):
    name = "my_memory"

    def reset(self): ...
    def ingest(self, session): ...
    def build_context(self, question, question_date) -> Retrieval: ...
```

- `reset`: 질문마다 새 사용자로 시작합니다.
- `ingest`: 쓰기 경로. 지난 세션이 시간순으로 하나씩 들어옵니다. 여기서 LLM을 쓰면 그 토큰을 `Retrieval.ingest_*_tokens`에 담아 메모리 구축 비용으로 따로 셉니다.
- `build_context`: 읽기 경로. 답변 모델에게 넘길 기억을 돌려줍니다.

모델이 직접 찾게 하려면 `agentic = True`로 두고 `run_agent`를 구현합니다(`agentic_files.py` 참고).

## 구조

```
memlab/
  data.py          LongMemEval 로딩 (질문, 세션, 근거 표시)
  systems/         메모리 시스템
    base.py          인터페이스
    baselines.py     no_memory, raw_search, full_context
    agentic.py       agentic_search
    agentic_files.py 자유 검색
    progress_md.py   외부 메모리 파일
  bm25.py          의존성 없는 BM25
  prompts.py       답변·메모·판정 프롬프트
  llm.py           모델 호출 백엔드, dry-run 추정기, 테스트용 목 모델
  run.py           시스템 실행 → results/<name>/hypotheses.jsonl, traces.jsonl
  evaluate.py      판정 → eval.jsonl, summary.json
  report.py        비교표 → results/REPORT.md
  trace.py         모델이 찾은 과정 보기
  subset.py        고정 서브셋 생성
  extract.py       큰 데이터에서 서브셋 문항만 추출
scripts/           데이터 다운로드, 기준선 일괄 실행
subsets/           고정 평가 서브셋
tests/             목 모델 기반 전체 흐름 테스트
docs/results/      실험별 결과 문서 (<모델>-<effort>-<번호>.md)
docs/decisions.md  설계 결정과 근거
EXPERIMENTS.md     시간순 실험 일지
```

## 로드맵

사람이 설계하는 것은 **무엇을 어떤 형태로 남길지, 모델에게 줄 도구, 언제 꺼내 쓸지**입니다. 찾는 일은 모델에게 맡깁니다.

- **Stage 0 · 기준선** (완료): 기억 없음 / 원문 검색 / 상한
- **Stage 1 · 모델이 직접 검색** (완료): 원문을 파일로 펼쳐 두고 모델이 원하는 만큼 찾습니다.
- **Stage 2 · 찾기 쉬운 저장** (지금): 모델이 기억을 정리해 남깁니다. 첫 실험은 자기 메모 파일 `progress.md`입니다.
- **Stage 3 · 인덱스·주입층**: 작은 목차를 항상 주고, 모델이 필요할 때 펼쳐 봅니다.
- **Stage 4 · 정리(드리밍)**: 원문과 대조해 고치고, 합치고, 잊습니다. 변경은 diff로 남겨 사람이 승인합니다.
- **Stage 5 · 자체 평가셋**: LongMemEval이 보지 않는 것. 출처 혼동, 무관한 질문에 끼어들기, 오래된 사실.
- **Stage 6 · 실전 연결**: MCP 서버로 감싸 실제 에이전트에 붙입니다.

## 출처와 라이선스

- 코드: MIT ([`LICENSE`](LICENSE))
- LongMemEval: Wu et al., ICLR 2025. 데이터와 판정 프롬프트, MIT ([`licenses/LongMemEval-LICENSE.txt`](licenses/LongMemEval-LICENSE.txt))
- 참고: Anthropic, [*The components of agent memory*](https://www.anthropic.com/research/components-of-agent-memory), 2026-11-06
