# 구조

## 스킬 하나

[Agent Skills](https://agentskills.io)는 에이전트에게 절차적 지식을 넘기는 오픈 포맷이다. 폴더 하나 = 스킬 하나이고, 안의 `SKILL.md`가 전부다. Claude Code · Codex · Cursor · Gemini CLI 등이 같은 포맷을 읽는다.

```
<skill-name>/
├── SKILL.md          필수 — frontmatter(name·description) + 절차. 에이전트가 읽는다
├── README.md         사람이 읽는다 — 왜 만들었나 · 무엇을 해주나 · 설계에서 정한 것
├── references/       선택 — 길어서 본문에 못 넣은 참고 자료
├── assets/           선택 — template · scaffold 파일
├── scripts/          선택 — 실행 script
└── examples/         선택 — 완성 산출물 예시
```

`SKILL.md`는 처음에 `description`만 읽히고, 요청이 그 설명과 맞을 때 본문이 통째로 로드된다. 그래서 **`description`에 trigger 문구를 넉넉히** 적고, 긴 설명은 `references/`로 뺀다.

## 묶음

repo root의 `.claude-plugin/marketplace.json`이 플러그인 묶음을 정의한다. 묶음은 스킬 폴더를 옮기지 않고 폴더 목록만 가리키므로, 플러그인으로 깔든 폴더를 복사하든 같은 파일이 쓰인다.

묶음에 넣지 않는 스킬도 있다. 사람마다 값이 달라 프로젝트 설정이 먼저인 것(`blog-review`), 프로젝트에 훅과 파일을 놓는 설치형(`harness-backlog`)이 그렇다.

## 예시

산출물 예시는 각 스킬의 `examples/`에 두고, GitHub Pages로 바로 열 수 있다. 저장소 루트의 `.nojekyll`은 Pages가 파일을 그대로 서빙하게 한다.
