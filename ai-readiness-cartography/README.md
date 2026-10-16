# ai-readiness-cartography

repo가 코딩 에이전트에게 얼마나 친화적인지 **100점 rubric**으로 채점하고, 대시보드 HTML과 ROI 순 action list를 만든다.

## 왜 만들었나

"이 repo를 에이전트가 잘 다룰 수 있을까"를 감으로만 알았다. CLAUDE.md가 있다고 좋은 게 아니고, 문서 속 경로가 실제로 존재하는지는 아무도 확인하지 않는다. 점수로 보이면 어디부터 고칠지 정할 수 있다.

## 무엇을 해주나

세 가지를 한 번에 만든다.

1. **JSON 점수표** — 7범주(Navigation · Context Quality · Tribal Knowledge · Dependency Mapping · Verification Gates · Freshness · Agent Outcomes), 증거, 발견, ROI 액션
2. **단일 HTML 대시보드** — 사람이 보고 결정하는 용도. Inter + JetBrains Mono, 밝은 바탕의 기술 계기판
3. **ROI 순 action list** — 효과 대비 비용으로 정렬한 다음 할 일

번들된 `scripts/score.py`가 자동으로 잡는 것 중 가장 중요한 건 **hallucinated path 검증**이다. 문서가 가리키는 모든 경로 후보가 실제 존재하는지 전부 확인한다. 그 외 문서 drift(mtime 비교), god file, AGENTS.md 옆에 import 없는 CLAUDE.md 같은 함정도 잡는다.

## 어떻게 쓰나

`dev` bundle에 있다 → [설치](../docs/install.md)

> 이 레포 AI-readiness 점수 매겨줘
> 우리 repo가 얼마나 agent-friendly한지 보여줘

절차는 [SKILL.md](SKILL.md), rubric은 [references/scoring-rubric.md](references/scoring-rubric.md)에 있다.

## 설계에서 정한 것

- **점수는 스크립트가 낸다.** 모델은 JSON을 HTML에 채우고 수동 항목만 보탠다. 같은 repo면 같은 점수가 나와야 비교가 된다.
- **자동이 못 잡는 것은 Manual로 표시한다.** 빠른 명령의 깊이, tribal knowledge의 질, critic 리뷰 품질은 사람이 본다. 자동 점수인 척하지 않는다.
- **장식 없는 계기판.** 이름은 cartography지만 양피지 · 나침반 같은 지도 장식은 쓰지 않는다. 의사결정용 화면이다.

## 한계

- 산출물 예시가 아직 없다.
- rubric v2 기준이라 기준이 바뀌면 다시 채점해야 한다.
