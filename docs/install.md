# 설치

두 가지 방법이 있다. 둘 다 같은 파일을 쓴다.

## Claude Code 플러그인으로

marketplace를 한 번 등록하면 bundle 단위로 설치한다.

```
/plugin marketplace add zaehorang/horang-skills
/plugin install study@horang-skills
/plugin install dev@horang-skills
/plugin install deliver@horang-skills
```

| bundle | 스킬 |
|---|---|
| `study` | `mechanism-explainer` · `explorable-world` |
| `dev` | `ai-readiness-cartography` · `herdr-dispatch` · `ios-video-qa` |
| `deliver` | `report` · `presentation` |

- 설치한 스킬은 `/study:mechanism-explainer`처럼 bundle 이름이 앞에 붙는다. auto-trigger는 그대로 동작한다.
- third-party marketplace는 자동 업데이트가 꺼져 있다. 갱신은 `claude plugin update study@horang-skills`로 한다.
- bundle에 없는 스킬(`blog-review` · `behavior-spec-extraction` · `harness-backlog`)은 아래 폴더 복사로 설치한다.

## 폴더 복사로 (모든 에이전트)

스킬 폴더를 통째로 스킬 디렉터리에 복사(또는 symlink)하면 끝이다.

| 에이전트 | 개인 스킬 | 프로젝트 스킬 |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex CLI | `~/.agents/skills/` | `.agents/skills/` |
| Cursor · Gemini CLI 등 | 각 도구 문서 참고 | |

```bash
git clone https://github.com/zaehorang/horang-skills.git
cp -R horang-skills/mechanism-explainer ~/.claude/skills/
```

에이전트에게 시켜도 된다.

> `https://github.com/zaehorang/horang-skills` 의 `mechanism-explainer` 폴더를 내 스킬 디렉터리에 복사해줘

설치 후 에이전트를 재시작해야 목록에 뜬다.

`harness-backlog`는 프로젝트에 hook과 설정 파일을 놓는 설치형이라 복사 대신 번들된 `scripts/setup.py`를 쓴다. 자세한 건 그 스킬의 [README](../harness-backlog/README.md).
