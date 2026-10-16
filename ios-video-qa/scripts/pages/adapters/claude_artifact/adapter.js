// 공유 어댑터: claude.ai Artifact 런타임(window.claude.use). 인터페이스는 assets/pages/template.html의 주석.
window.QA_SHARE_ADAPTER = (function () {
  var rt = window.claude && window.claude.use ? window.claude : null, db = null, me = null;
  function doc() { return db.doc("reviews/" + me); }
  return {
    ready: function () {
      if (!rt) return Promise.resolve({ canSave: false, note: "보기 전용(Artifact 밖에서 열림 — 판단은 내려받기로 남기세요)" });
      return Promise.all([rt.use("db"), rt.use("user")]).then(function (r) {
        if (!r[0] || !r[1]) return { canSave: false, note: "보기 전용(판단을 저장하려면 로그인)" };
        db = r[0];
        return r[1].id().then(function (id) {
          me = id;
          return me ? { canSave: true, note: "" } : { canSave: false, note: "보기 전용(로그인 필요)" };
        });
      });
    },
    load: function () {
      return doc().get().then(function (snap) {
        var d = snap && snap.data && snap.data();
        try { return d && d.state ? JSON.parse(d.state) : null; } catch (e) { return null; }
      });
    },
    save: function (run, state) {
      return doc().set({ state: JSON.stringify(state), run: run, updatedAt: new Date().toISOString() });
    },
    download: function (name, text) {
      if (!rt) return Promise.resolve(false);
      return rt.use("downloads").then(function (dl) {
        if (!dl) return false;
        return dl.save({ filename: name, data: text }).then(function () { return true; });
      });
    }
  };
})();
