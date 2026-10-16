# presentation

장 배열(FLOW)과 대본(SCRIPT)을 먼저 승인받고, 화면에는 **말의 근거만** 옮긴 16:9 HTML 덱을 만든다.

**예시**
- [완성 발표 — 간식 서랍](https://zaehorang.github.io/horang-skills/presentation/examples/snack-drawer/presentation.html) — report 예시에서 출발해 FLOW · SCRIPT를 거친 7장 덱. ← → 로 넘긴다.
- [장 갤러리](https://zaehorang.github.io/horang-skills/presentation/examples/gallery/) — 발표에 자주 나오는 장 22가지와 색 테마 5개, 라이트/다크. 장 종류를 고르는 견본이고 [안내서](examples/gallery/README.md)가 따로 있다.

## 왜 만들었나

슬라이드를 먼저 만들면 무엇을 말하고 싶은지가 레이아웃에 끌려간다. 그리고 덱 검토는 눈으로만 하니 넘침, 대비 부족, 어색한 줄바꿈을 매번 놓친다. 말이 먼저 서야 화면은 그 말의 근거만 담고, 검사는 기계가 먼저 해야 한다.

## 무엇을 해주나

```
plan      FLOW.md            장 배열 — 질문 · 핵심 주장 · 초 · 상태        ← 승인
narrate   SCRIPT.md          장 안의 전개 → 완성 발화체 + 화면에 둘 것 / 말로만 할 것  ← 승인
build     presentation.html  "화면에 둘 것"만 옮김
verify    기계 검사 + 관점별 리뷰
export    PDF
polish    SCRIPT.md          진행 메모 + 화면에 맞춘 문구 조정
```

- 스타터 템플릿 하나에 장 패턴 22가지(표지 · 목차 · 구조도 · 코드 설명 · 전후 비교 · 핵심 숫자 · 로드맵 · 결정 요청 …)와 색 테마 5개가 들어 있다.
- `scripts/deck_verify.py`가 넘침 · 대비 · 줄바꿈 · 레이아웃 예산을 검사한다. `deck_numbers.py`는 화면의 숫자를 근거 JSON · CSV와 대조한다.
- 보고서가 먼저 있으면 그 수치와 그림에서 출발하고, FLOW에 보고서 쪽 번호를 연결한다.

산출물은 `FLOW.md` + `SCRIPT.md` + `presentation.html` (+ PDF).

## 어떻게 쓰나

`deliver` 묶음에 있다 → [설치](../docs/install.md)

> 이 보고서로 발표 덱 만들어줘
> 발표 흐름부터 잡아줘

절차는 [SKILL.md](SKILL.md)에 있다. 단계별 참고는 `references/`의 plan · narrate · build · verify · export · polish.

## 설계에서 정한 것

- **승인 단계를 셋으로 나눈다.** FLOW는 장의 배열(가로, 무엇을 주장하는가), SCRIPT는 장 안의 전개(세로, 어떻게 믿게 만드는가)라 축이 다르다. 한 단계 승인이 다음 단계 허락이 아니다. 장 순서가 바뀌면 덱만 고치지 않고 FLOW · SCRIPT · 덱 셋을 같이 맞춘다.
- **화면에는 말의 근거만.** SCRIPT에서 "화면에 둘 것"과 "말로만 할 것"을 갈라 두고, build는 앞쪽만 옮긴다.
- **구조도는 그림을 만들지 않는다.** 레인 · 전후 · 번호 다이어그램은 HTML 패턴과 선 그리기 엔진으로 그린다. 그래야 테마를 따르고 글자가 읽힌다.
- **검사는 스크립트가 먼저.** 넘침과 대비는 눈으로 보면 놓친다. 템플릿을 고치면 `deck_selftest.py`가 갤러리와 스타터가 같은지까지 확인한다.
- **테마는 발표 종류로 고른다.** clay(제안 · 보고, report와 같은 톤) · ocean(기술) · duo(강의 · 비교) · forest(운영) · signal(피치).

## 한계

- 기존 PPTX 템플릿은 편집하지 않는다.
- PDF 내보내기에 헤드리스 Chromium 계열 브라우저가 필요하다.
