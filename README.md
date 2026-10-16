# horang-skills

**Agent Skills** 모음. 주제별로 묶여 있다. 📖 이해하기(`study`), 🔍 진단·🛠 개발의 일부(`dev`), 📄 전달하기(`deliver`)는 Claude Code 플러그인으로 설치할 수 있고, 모든 스킬은 폴더만 복사해 써도 된다.

[Agent Skills](https://agentskills.io)는 에이전트에게 절차적 지식을 넘기는 오픈 포맷이다.
폴더 하나 = 스킬 하나이고, 안의 `SKILL.md`가 전부다. Claude Code · Codex · Cursor · Gemini CLI 등이 같은 포맷을 읽는다.

공통점은 하나다 — **이해하기 어려운 것을, 사람이 검수할 수 있는 산출물로 바꾼다.**

---

## 📖 이해하기

> 남이 만든 것을 내가 아는 것으로.

```
/plugin install study@horang-skills
```

| 스킬 | 하는 일 | 산출물 |
|---|---|---|
| [`mechanism-explainer`](./mechanism-explainer) | 시스템 내부 동작을 단계별 상태 다이어그램 + 실제 before/after로 따라간다 | 단일 `.html` |
| [`explorable-world`](./explorable-world) | 아키텍처를 세계관 지도로 바꾸고, 사건 버튼으로 요청의 흐름을 애니메이션으로 탐험한다 | 정적 웹 페이지 폴더 |
| [`blog-review`](./blog-review) | 테크 블로그를 대화형으로 리뷰한다. 요약 대신 사용자의 이해를 끌어내 ✅/🔧/💡로 교정한다 | 학습 노트 `.md` + 개념 파일 + raw `.jsonl` |

`blog-review`는 `study` 묶음에 없다. 폴더 복사로 설치한다.

---

## 🔍 진단하기

> 지금 상태가 어떤지 숫자로.

```
/plugin install dev@horang-skills
```

| 스킬 | 하는 일 | 산출물 |
|---|---|---|
| [`ai-readiness-cartography`](./ai-readiness-cartography) | repo가 코딩 에이전트에게 얼마나 친화적인지 100점 rubric으로 채점한다. 문서 속 경로가 실재하는지 전부 검증 | dashboard `.html` + 점수 `.json` + ROI 순 action list |

---

## 📄 전달하기

> 결과를 읽히는 문서로, 들리는 말로.

```
/plugin install deliver@horang-skills
```

| 스킬 | 하는 일 | 산출물 |
|---|---|---|
| [`report`](./report) | 분석 결과를 "한 쪽 = 한 메시지"인 A4 쪽 고정형 보고서로 만든다. 쪽 넘침 · 짧은 꼬리 줄 · 줄바꿈 지점을 자동 검사하고, 보고서 쪽에 맞춘 발표 대본을 따로 뽑는다 | `report.html` + PDF (+ 쪽별 대본 `.md`) |
| [`presentation`](./presentation) | 장 배열(FLOW)과 전개(SCRIPT)를 먼저 승인받고, 화면에는 말의 근거만 옮긴 16:9 HTML deck을 만든다 | `FLOW.md` + `SCRIPT.md` + `presentation.html` (+ PDF) |

읽히는 문서가 필요하면 `report`, 따로 슬라이드를 띄워 말해야 하면 `presentation`을 쓴다.

`presentation`에는 발표에 자주 나오는 장 22가지와 색 테마 5개를 한 주제로 채운 견본 갤러리가 있다 — [`presentation/examples/gallery/index.html`](./presentation/examples/gallery/index.html)을 브라우저로 열면 장 종류별로 미리 보고 테마를 바꿔 볼 수 있다.

---

## 🛠 개발하기

> 코드 밖에 남겨야 할 것을 남기고, 일은 알맞은 곳에 넘긴다.

`herdr-dispatch`는 `dev` 묶음에 있다. 나머지는 [폴더 복사](#폴더-복사로-모든-에이전트)로 설치한다.

| 스킬 | 하는 일 | 산출물 |
|---|---|---|
| [`behavior-spec-extraction`](./behavior-spec-extraction) | 기존 코드에서 구현 용어를 걷어낸 "관측 가능한 동작" 명세를 역추출한다. linter가 구현 누출을 막는다 | 명세 `.md` (코드 블록 없음) |
| [`herdr-dispatch`](./herdr-dispatch) | 옆 pane에 일을 넘길 때 모델 · 추론 강도 · 권한을 역할표로 고른다. 표가 낡으면 `doctor`가 잡고, 벤더별 pane이 자기 쪽을 재검증한다 | 알맞게 설정된 pane + 선택 근거 |
| [`harness-backlog`](./harness-backlog) | 세션이 끝나면 다른 모델이 harness 빈틈을 backlog에 제안한다. 반영은 사람이 한다 | `.local/harness-backlog/*.md` + 설치 스크립트 |

`herdr-dispatch`의 모델명·플래그 표는 낡는다. `scripts/doctor.py`가 설치된 CLI·모델 캐시·전역 설정과 표를 몇 초 안에 대조하고, "모델 업데이트 확인해"라고 하면 `references/verify.md` 절차대로 claude pane과 codex pane이 각자 자기 벤더 문서를 공식 출처와 교차 확인한다.

---

## 설치

### Claude Code 플러그인으로

marketplace를 한 번 등록하면 묶음을 설치할 수 있다.

```
/plugin marketplace add zaehorang/horang-skills
/plugin install study@horang-skills
/plugin install dev@horang-skills
/plugin install deliver@horang-skills
```

| 묶음 | 주제 | 스킬 |
|---|---|---|
| `study` | 📖 이해하기 | `mechanism-explainer` · `explorable-world` |
| `dev` | 🔍 진단 · 🛠 개발 | `ai-readiness-cartography` · `herdr-dispatch` |
| `deliver` | 📄 전달하기 | `report` · `presentation` |

설치한 스킬은 `/study:mechanism-explainer`처럼 묶음 이름이 앞에 붙는다. auto-trigger는 그대로 동작한다.
third-party marketplace는 자동 업데이트가 꺼져 있으니 갱신은 `claude plugin update study@horang-skills`로 한다.

### 폴더 복사로 (모든 에이전트)

폴더를 통째로 스킬 디렉터리에 복사(또는 symlink)하면 끝이다.

| 에이전트 | 개인 스킬 | 프로젝트 스킬 |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex CLI | `~/.agents/skills/` | `.agents/skills/` |
| Cursor · Gemini CLI 등 | 각 도구 문서 참고 | |

```bash
git clone https://github.com/zaehorang/horang-skills.git
cp -R horang-skills/mechanism-explainer ~/.claude/skills/
```

에이전트에게 시켜도 된다:

> `https://github.com/zaehorang/horang-skills` 의 `mechanism-explainer` 폴더를 내 스킬 디렉터리에 복사해줘

설치 후 에이전트를 재시작해야 목록에 뜬다.

---

## 스킬 하나의 구조

```
<skill-name>/
├── SKILL.md          필수 — frontmatter(name·description) + 절차
├── references/       선택 — 길어서 본문에 못 넣은 참고 자료
├── assets/           선택 — template·scaffold 파일
└── scripts/          선택 — 실행 script
```

repo root의 `.claude-plugin/marketplace.json`이 묶음을 정의한다. 묶음은 스킬 폴더를 옮기지 않고 폴더 목록만 가리키므로,
플러그인으로 깔든 폴더를 복사하든 같은 파일이 쓰인다.

`SKILL.md`는 처음에 `description`만 읽히고, 요청이 그 설명과 맞을 때 본문이 통째로 로드된다.
그래서 **`description`에 trigger 문구를 넉넉히** 적고, 긴 설명은 `references/`로 뺀다.

## 이 repo의 규칙

- **vendor 이름을 본문에 쓰지 않는다.** 특정 도구 이름 대신 능력으로 쓴다 — "웹 페이지를 가져온다", "파일로 저장한다". 그래야 어느 에이전트에서든 돈다.
  단, **특정 도구를 제어하는 것 자체가 목적인 스킬은 예외다.** 도구 이름이 곧 내용이라 추상화하면 스킬이 할 일이 없어진다 (`herdr-dispatch`, `harness-backlog`).
- **스킬 폴더에 README.md를 두지 않는다.** `SKILL.md`가 그 역할이고, 둘을 두면 어긋난다.
- **개인 취향을 스킬에 넣지 않는다.** 판별 기준:

  > *"다른 사람이 이 스킬을 깔았을 때, 이 줄이 그 사람에게도 참인가?"*

  | 답 | 어디로 |
  |---|---|
  | 참이다 | **스킬** — 방법 |
  | "내가 그렇게 정했다" | **프로젝트** — 결정 |
  | 참이지만 **값이 사람마다 다르다** | 스킬엔 *"정해야 한다"* 만, **값은 프로젝트** |

  세 번째가 제일 놓치기 쉽다. 예를 들어 `blog-review`의 태그 어휘는 스킬에 두면 안 된다 —
  **개인 어휘를 늘리려고 공유 스킬을 고치게 되면 분리가 잘못된 것이다.**

## 라이선스

MIT
