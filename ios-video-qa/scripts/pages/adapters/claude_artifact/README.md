# 공유 어댑터: claude.ai Artifact

각본 리뷰 페이지를 claude.ai Artifact로 공유할 때 쓰는 어댑터. 엔진 본문은 "공유 어댑터"라는 능력만 알고, 이 이름은 이 폴더 안에서만 쓴다.

- `adapter.js`: 페이지 안에서 판단을 Artifact db의 `reviews/<보는 사람 id>`에 저장·불러오기, 내려받기는 Artifact downloads.
- `adapter.py`: 발행 설정(`publish.json`)의 capabilities(db 규칙, user, downloads, assets).

## 발행 절차 (사람이 발행을 확인한 뒤, 에이전트가 Artifact 도구로)

1. `qa share [결과 폴더] --adapter claude_artifact --out <폴더>` → `index.html`, `assets.json`, `publish.json`
2. `index.html`을 한 번 발행해 URL을 받는다(capabilities는 `publish.json`).
3. `assets.json`의 파일을 그 URL의 자산 저장소에 올리고, 받은 url을 `{key: url}`로 `map.json`에 적는다.
4. `qa share ... --adapter claude_artifact --asset-map map.json`으로 다시 만들어 같은 URL에 다시 발행한다.

판단은 페이지에서 저장되지만, 출시 판단에 쓰려면 사람이 페이지의 "판단 JSON 내려받기"로 받은 파일을 `qa judgments --from`으로 반영한다.
