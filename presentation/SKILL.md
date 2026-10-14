---
name: presentation
description: Plan, narrate, build, review, verify, export, or polish an HTML presentation deck with a reusable 16:9 template and deterministic quality checks. Use for presentation flow design, speaker script writing, slide creation, deck review, and PDF export; do not use for editing an unrelated existing PPTX template.
---

# Presentation

Create presentation artifacts in the user's chosen project directory while keeping the reusable template, checks, and guidance inside this skill.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. Never assume the current repository contains `.agents/deck-kit` or `scripts/deck_*.py`.

## 순서

**슬라이드보다 대본이 먼저다.** 화면을 먼저 만들면 무엇을 말하고 싶은지가 레이아웃에
끌려간다. 말이 서면 화면은 그 말의 근거만 담는다.

```
plan      FLOW.md            장 배열 — 질문 · 핵심 주장 · 초 · 상태        ← 승인
narrate¹  SCRIPT.md          장 안의 전개, 요지 박자                      ← 승인 (FLOW 복귀 가능)
narrate²  SCRIPT.md          완성 발화체 + 화면에 둘 것 / 말로만 할 것      ← 승인
build     presentation.html  "화면에 둘 것"만 옮김
verify    기계 검사 + 관점별 서브에이전트 리뷰
export    PDF
polish    SCRIPT.md          진행 메모 + 화면에 맞춘 문구 조정
```

FLOW 와 SCRIPT 는 축이 다르다. **FLOW 는 장의 배열(가로), SCRIPT 는 장 안의 전개(세로)** 다.
FLOW 가 *무엇을 주장하는가* 라면 SCRIPT 는 *어떻게 믿게 만드는가* 다.

## Route the request

Load only the reference needed for the current operation:

- New presentation, storyline, slide order: read [references/plan.md](references/plan.md).
- Speaker script, 논리 전개, 문체: read [references/narrate.md](references/narrate.md).
- Build slides from an approved `SCRIPT.md`, or edit an existing harness deck: read [references/build.md](references/build.md).
- Images, illustrations, product screen captures: read [references/assets.md](references/assets.md).
- Review or validate a deck, or judge feedback received from elsewhere: read [references/verify.md](references/verify.md).
- Export an HTML deck to PDF: read [references/export.md](references/export.md).
- Final script pass — 진행 메모, 화면에 맞춘 조정: read [references/polish.md](references/polish.md).

If a request spans several operations, follow the stage gates below and load each reference only when its stage begins.

## Stage gates

1. Plan produces only `FLOW.md`, then stops for user approval.
2. Narrate pass 1 produces 요지 only, then stops. 구조 문제가 나오면 FLOW 로 되돌아간다.
3. Narrate pass 2 produces 완성 발화체 + 화면/말 구분, then stops.
4. Build requires an approved `SCRIPT.md` and produces `presentation.html` plus project-local assets.
5. Verify reports review findings before applying judgment-based revisions. Deterministic errors may be fixed within an authorized build request.
6. Export runs only when the user requests a PDF, and never overwrites the previous PDF.
7. Polish runs after the deck is settled.

Do not treat approval of one stage as permission for later stages.

장 순서나 주장이 바뀌면 덱만 고치지 않는다. FLOW · SCRIPT · 덱 셋을 같이 맞춘다.

## Bundled resources

- Copy [assets/starter/presentation.html](assets/starter/presentation.html) into the project when starting a harness deck. Copy the bundled files from `assets/starter/assets/` that the chosen slides actually use into the project's `assets/` directory.
- Use [references/layout-budget.md](references/layout-budget.md) when choosing slide patterns or reducing crowded content.
- Consult [references/failure-catalog.md](references/failure-catalog.md) when a verification failure needs its original rationale.
- Run `python3 <skill-dir>/scripts/deck_verify.py <deck.html>` for deck validation.
- Run `python3 <skill-dir>/scripts/deck_export.py <deck.html> [-o out.pdf]` for PDF export.
- Run `python3 <skill-dir>/scripts/deck_selftest.py [--fast]` only when changing the template or verifier itself.

Preserve user-authored content and distinguish confirmed behavior, proposals, and future work. Reviews alone are read-only; modify files only when the user asks for creation or changes.
