# memory-lab

에이전트 메모리 시스템을 **한 층씩, 측정하면서** 만들어가는 실험실.

출발점은 Anthropic의 글 [The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)(2026-11-06)와, 계층형 개인 메모리를 운영할 때 흔히 부딪히는 문제들(매번 직접 불러와야 하는 시동 비용, 낡는 기록, 사람에게 몰리는 쓰기 부담, 맥락을 넘어 끼어드는 기억)이다. 배경과 결정 과정은 [`docs/decisions.md`](docs/decisions.md)에 있다.

## 원칙

1. **측정이 먼저.** 모든 변경은 같은 평가셋, 같은 답변 프롬프트에서 숫자로 비교한다.
2. **한 번에 변수 하나.** 바꾼 것과 결과는 [`EXPERIMENTS.md`](EXPERIMENTS.md)에 남긴다.
3. **층은 자리를 벌어야 남는다.** 기준선보다 정답률이 오르거나 토큰이 줄지 않으면 뺀다.
4. **이겨야 할 상대는 가장 단순한 메모리**, 원문 검색이다.
5. **실사용도 지표다.** 점수가 좋아도 손이 안 가면 실패다.

## 지금: Stage 0 — 기준선

| 시스템 | 하는 일 | 역할 |
|---|---|---|
| `no_memory` | 질문만 본다 | 하한 |
| `raw_search` | 원문 대화를 라운드(사용자 발화 + 이어지는 답) 단위로 BM25 검색, 상위 k개를 시간순으로 | **이겨야 할 상대** |
| `full_context` | 이력 전체를 그대로 넣는다 | 비용 참고선 |
| `full_context` + oracle 데이터 | 근거 세션만 넣는다 | 읽기 상한 (검색이 완벽할 때의 점수) |

**평가**: [LongMemEval](https://github.com/xiaowu0162/LongMemEval)(2025-09 cleaned) 서브셋 `dev42` = 6개 유형 × 6문항 + 답변 보류(abstention) 6문항. 판정 프롬프트는 LongMemEval 공식 것을 그대로 옮겼고(MIT), 판정 모델만 Claude다.

**지표**
- 정답률: 전체, 유형별, 유형 평균
- 질문당 입력 토큰, 메모리 구축 토큰 (나중 층에서 노트 작성·드리밍에 드는 비용)
- **근거 재현율**: 메모리가 근거 세션을 꺼냈는가. 낮으면 검색 실패, 높은데 틀리면 읽기 실패.

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q                  # 목 모델로 전체 흐름 확인 (API 키 불필요)

bash scripts/download_data.sh        # LongMemEval cleaned: _s(질문당 ~11.5만 토큰 이력), oracle
export ANTHROPIC_API_KEY=...
bash scripts/run_baselines.sh        # 비용 추정 → 확인 → 실행 → 채점 → results/REPORT.md
```

`run_baselines.sh`는 API를 부르기 전에 dry run으로 질문당 토큰과 예상 비용을 보여주고 확인을 받는다. 비용 대부분은 `full_context`에서 나오므로 `SKIP_FULL=1`로 뺄 수 있다. 처음 만들어진 `subsets/dev42.json`은 커밋해서 서브셋을 고정한다.

하나씩 돌릴 때:

```bash
python -m memlab.subset --data data/longmemeval_s_cleaned.json --out subsets/dev42.json
python -m memlab.run --system raw_search --param top_k=10 --subset subsets/dev42.json --dry-run
python -m memlab.run --system raw_search --param top_k=10 --subset subsets/dev42.json
python -m memlab.evaluate results/raw_search_top_k10
python -m memlab.report results
```

같은 명령을 다시 실행하면 이어서 한다. 끝난 질문은 건너뛰고, 실패한 질문만 다시 시도한다.

## 새 메모리 층 추가하기

`memlab/systems/`에 `MemorySystem`을 구현하고 `SYSTEMS`에 등록한다.

```python
class MyMemory(MemorySystem):
    name = "my_memory"

    def reset(self): ...                       # 질문마다 새 사용자
    def ingest(self, session): ...             # 쓰기 경로: 세션이 시간순으로 하나씩 들어온다
    def build_context(self, question, question_date) -> Retrieval: ...   # 읽기 경로
```

`ingest`에서 LLM을 쓰면(노트 작성, 드리밍) 그 토큰을 `Retrieval.ingest_*_tokens`에 담는다. 리포트에서 메모리 구축 비용으로 따로 보인다. 모든 시스템은 같은 답변 프롬프트를 쓰므로 점수 차이는 `<memory>`에 무엇을 넣었는지에서만 나온다.

## 구조

```
memlab/
  data.py          LongMemEval 로딩 (질문, 세션, 근거 표시)
  systems/         메모리 시스템들 (base.py 인터페이스, baselines.py)
  bm25.py          의존성 없는 BM25
  prompts.py       공통 답변 프롬프트 + LongMemEval 판정 프롬프트
  llm.py           Anthropic 호출, dry-run 추정기, 테스트용 목 모델
  run.py           시스템 실행 → results/<name>/hypotheses.jsonl
  evaluate.py      판정 → eval.jsonl, summary.json
  report.py        전체 비교표 → results/REPORT.md
  subset.py        고정 서브셋 생성
scripts/           데이터 다운로드, 기준선 일괄 실행
tests/             목 모델 기반 전체 흐름 테스트
docs/decisions.md  결정과 근거 (누가 정했는지 표시)
EXPERIMENTS.md     실험 기록
```

## 로드맵

- **Stage 0 · 기준선** ← 지금
- **Stage 1 · 노트층**: 세션이 끝나면 LLM이 메모를 쓴다. 항목마다 출처(직접 발언 / 확정 / 검토안 / AI 해석)와 날짜.
- **Stage 2 · 인덱스·주입층**: 작은 목차를 항상 주고, 필요할 때 노트를 꺼낸다.
- **Stage 3 · 드리밍**: 원문과 대조해 고치고, 병합하고, 잊는다. 변경은 diff로 남겨 사람이 승인한다.
- **Stage 4 · 자체 평가셋**: LongMemEval이 보지 않는 것. 출처 혼동, 무관한 질문에 끼어들기, 오래된 사실.
- **Stage 5 · 실전 연결**: MCP 서버로 감싸 에이전트에 붙인다. 첫 테스트베드 후보는 코드 리뷰 에이전트 파이프라인 (리뷰어 FAIL률로 효과 측정).

Stage 1 이후는 아직 제안 단계다. 각 단계는 앞 단계를 숫자로 이겨야 다음으로 간다.

## 출처와 라이선스

- LongMemEval: Wu et al., ICLR 2025. 데이터와 판정 프롬프트, MIT ([`licenses/LongMemEval-LICENSE.txt`](licenses/LongMemEval-LICENSE.txt))
- Anthropic, *The components of agent memory*, 2026-11-06
