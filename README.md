# horang-skills

에이전트에게 넘기는 **Agent Skills** 모음. 공통점은 하나다 — **이해하기 어려운 것을, 사람이 검수할 수 있는 산출물로 바꾼다.**

## 설치

```
/plugin marketplace add zaehorang/horang-skills
/plugin install study@horang-skills
/plugin install dev@horang-skills
/plugin install deliver@horang-skills
```

플러그인 없이 폴더만 복사해도 된다 → [docs/install.md](docs/install.md)

## study — 이해하기

```
/plugin install study@horang-skills
```

| 스킬 | 하는 일 |
|---|---|
| [`mechanism-explainer`](./mechanism-explainer) | 시스템 하나의 내부 동작을 단계별 상태 다이어그램 + 실제 before/after로 따라가는 단일 HTML |
| [`explorable-world`](./explorable-world) | 아키텍처를 비유 세계관 지도로 바꾸고, 사건 버튼으로 요청의 흐름을 탐험하는 웹 페이지 |

## dev — 진단 · 개발하기

```
/plugin install dev@horang-skills
```

| 스킬 | 하는 일 |
|---|---|
| [`ai-readiness-cartography`](./ai-readiness-cartography) | repo가 코딩 에이전트에게 얼마나 친화적인지 100점 rubric으로 채점한 대시보드 |
| [`herdr-dispatch`](./herdr-dispatch) | 옆 pane에 일을 넘길 때 모델 · 추론 강도 · 권한을 role table로 고른다 |

## deliver — 전달하기

```
/plugin install deliver@horang-skills
```

| 스킬 | 하는 일 |
|---|---|
| [`report`](./report) | "한 쪽 = 한 메시지"인 A4 page-fixed 보고서와 PDF. 넘침 · 줄바꿈을 자동 검사 |
| [`presentation`](./presentation) | 장 배열과 대본을 먼저 승인받고, 화면에는 말의 근거만 옮긴 16:9 HTML 덱 |

## bundle에 없는 스킬

폴더 복사로 설치한다.

| 스킬 | 하는 일 |
|---|---|
| [`blog-review`](./blog-review) | 테크 블로그를 대화형으로 리뷰한다. 요약 대신 사용자의 이해를 끌어내 교정하고 학습 노트로 남긴다 |
| [`behavior-spec-extraction`](./behavior-spec-extraction) | 기존 코드에서 구현 용어를 걷어낸 "관측 가능한 동작" 명세를 reverse-engineer한다 |
| [`harness-backlog`](./harness-backlog) | 세션이 끝나면 다른 모델이 harness의 빈틈을 backlog에 제안한다. 반영은 사람이 한다 |

## 더 읽기

- [docs/install.md](docs/install.md) — 플러그인 · 폴더 복사 · 갱신
- [docs/structure.md](docs/structure.md) — 스킬 폴더 구조와 bundle
- [docs/principles.md](docs/principles.md) — 이 repo의 원칙

## 라이선스

MIT
