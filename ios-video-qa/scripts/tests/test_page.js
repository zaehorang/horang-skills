// 리뷰 페이지의 순수 논리(qa-logic 블록)만 떼어 시험한다. 결과 줄: ok … / FAIL …
const fs = require("fs"), path = require("path"), vm = require("vm");
const tpl = fs.readFileSync(path.join(__dirname, "..", "..", "assets", "pages", "template.html"), "utf8");
const m = tpl.match(/<script id="qa-logic">([\s\S]*?)<\/script>/);
const ctx = { module: {} }; vm.createContext(ctx); vm.runInContext(m[1], ctx);
const QA = ctx.module.exports;
const t = (name, cond) => console.log((cond ? "ok " : "FAIL ") + name);
const data = { run: "r1", condition: "기본", cases: [
  { id: "QA-01", hash: "h1", scriptHash: "s1", steps: [{ n: 1, t: 1.5, visual: ["가", "나"] }, { n: 2, t: null, visual: [] }] },
  { id: "QA-02", hash: "h2", scriptHash: "s2", steps: [{ n: 1, t: 0, visual: ["다"] }] }] };
let st = QA.emptyState();
t("항목 3개, 모두 미검토", QA.counts(data, st)["미검토"] === 3 && QA.counts(data, st).total === 3);
const items = QA.allVisual(data);
QA.setVerdict(st, items[0], "정상", "", "기본");
QA.setVerdict(st, items[1], "이상", "겹침", "기본");
const c = QA.counts(data, st);
t("집계", c["정상"] === 1 && c["이상"] === 1 && c["미검토"] === 1);
let threw = false; try { QA.setVerdict(st, items[2], "좋음"); } catch (e) { threw = true; }
t("모르는 판단은 거부", threw);
t("미검토가 있으면 출시 준비 아님", !QA.releaseReady(data, st).ready);
QA.setVerdict(st, items[1], "정상", "", "기본"); QA.setVerdict(st, items[2], "판단 불가", "흐림", "기본");
t("이상 0·미검토 0이면 출시 준비", QA.releaseReady(data, st).ready);
st.approve["QA-02"] = true; st.answers["G1"] = "마지막"; st.answers["G2"] = ""; st.reviewer = "확인자";
const ex = QA.buildExport(data, st);
t("내려받기 형식", ex.kind === "review" && ex.run === "r1" && ex.judgments.length === 3);
t("승인 요청에 각본·스크립트 해시", ex.approve.cases.length === 1 && ex.approve.cases[0].hash === "h2" && ex.approve.cases[0].script_hash === "s2");
t("빈 답은 빼고 보냄", ex.answers.length === 1 && ex.answers[0].id === "G1");
t("판단에 근거 시각", ex.judgments[0].evidence_t === 1.5);
t("템플릿에 공유 도구 이름이 없음", !/window\.claude/.test(tpl) && tpl.includes("__QA_ADAPTER__"));
