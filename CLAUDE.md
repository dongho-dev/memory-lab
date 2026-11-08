# memory-lab 작업 규칙

에이전트 메모리 시스템을 한 층씩, 측정하면서 만드는 저장소다.

## 먼저 읽을 것
1. `docs/decisions.md` — 왜 이렇게 만들었나, 누가 정했나 (정리본)
2. `docs/results/README.md` — 실험 결과 한눈에 보기 (문서 하나 = 실험 하나, `<모델>-<effort>-<번호>`)
3. `EXPERIMENTS.md` — 지금까지의 실험 일지 (시간순)
4. 원문이 필요할 때만 `docs/sessions/` — 대화 원문 (원본층, **로컬 전용**: gitignore, 공개 저장소에 올리지 않음)

## 규칙
- 모든 변경은 측정으로 판단한다. 새 메모리 층은 `memlab/systems/`에 `MemorySystem`으로 추가하고, 같은 서브셋·같은 답변 프롬프트로 기준선과 비교한다.
- 한 번에 변수 하나. 실험할 때마다 `EXPERIMENTS.md`에 항목을 **추가**한다 (지난 기록은 고치지 않는다).
- 답변 프롬프트(`memlab/prompts.py`의 `ANSWER_*`)는 시스템 간 공정 비교의 기준이다. 바꾸면 모든 기준선을 다시 돌린다.
- 판정 프롬프트는 LongMemEval 원문 그대로 둔다 (공개 결과와 비교 가능하도록).
- 실제 API 호출 전에 `--dry-run`으로 토큰과 비용을 먼저 본다.
- `data/`와 `results/`의 실행 산출물은 커밋하지 않는다. 결과는 `results/REPORT.md`의 표를 `EXPERIMENTS.md`(일지, 추가만)로 옮기고, `docs/results/<모델>-<effort>-<번호>.md` 문서를 만들고 `docs/results/README.md` 표에 한 줄 추가한다.
- 답변 모델은 Haiku / Sonnet / Opus로 나눠 각각 잰다. effort도 변수로 본다. 실행 이름에 모델과 effort가 붙는다(예: `raw_search_k10@sonnet-5-5-medium`).
- `docs/decisions.md`를 고칠 때는 출처를 구분한다: [소유자] / [합의] / [제안] / [관찰]. Claude의 제안을 소유자의 결정처럼 쓰지 않는다.
- `docs/sessions/`의 원문은 수정하지 않고, 커밋하지 않는다(개인 대화라 로컬에만 둔다).
- 테스트: `python -m pytest -q` (목 모델, API 키 불필요)
