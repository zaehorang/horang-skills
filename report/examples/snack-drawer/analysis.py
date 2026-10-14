"""예시 보고서용 분석: 사무실 간식 서랍은 오후 3시 전에 비는가.

데이터는 시드를 고정한 가상 데이터다. 실제 사무실 기록이 아니다.
실행: python3 analysis.py   (numpy, matplotlib 필요)
출력: data.csv, results.json, figures/*.png
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

# ---- 그림 스타일: report 스킬의 assets/mpl_style.py 를 복사한 것 ----
PAPER, INK, MUTED, RULE = "#FAF9F5", "#141413", "#5E5D59", "#C9C7BE"
INK_BAR, CLAY, GREY = "#3D3D3A", "#D97757", "#C2C0B6"
plt.rcParams.update({
    "font.family": ["Apple SD Gothic Neo", "AppleGothic", "Noto Sans CJK KR", "NanumGothic"],
    "axes.unicode_minus": False, "figure.dpi": 100, "savefig.dpi": 150,
    "figure.facecolor": PAPER, "savefig.facecolor": PAPER, "axes.facecolor": PAPER,
    "axes.edgecolor": RULE, "axes.labelcolor": MUTED, "axes.titlecolor": INK,
    "axes.titlelocation": "left", "axes.titleweight": "bold", "axes.titlesize": 11,
    "axes.labelsize": 9.5, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
})

# ---- 1. 가상 데이터 120영업일 ----
rng = np.random.default_rng(20261014)
N, TRAIN = 120, 90
DAYS = ["월", "화", "수", "목", "금"]
weekday = np.arange(N) % 5                       # 0=월 … 4=금
restock = np.isin(weekday, [0, 3]).astype(int)   # 월·목 아침에 보충
meetings = rng.poisson(2.2, N)                   # 오후 회의 수
temp = 6 + 18 * np.sin(np.linspace(0.2, 2.6, N)) + rng.normal(0, 2.5, N)  # 기온(°C)
deadline = ((np.arange(N) // 5) % 4 == 3).astype(int)  # 4주에 한 번 마감 주간
true_logit = (-0.4 - 2.0 * restock + 0.55 * meetings + 1.3 * deadline
              - 0.04 * (temp - 12) + 0.35 * (weekday == 4))
empty = (rng.random(N) < 1 / (1 + np.exp(-true_logit))).astype(int)

with open(HERE / "data.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["day", "weekday", "restock", "meetings", "temp_c", "deadline_week", "empty_by_3pm"])
    for i in range(N):
        w.writerow([i + 1, DAYS[weekday[i]], restock[i], meetings[i], round(temp[i], 1), deadline[i], empty[i]])

# ---- 2. 모델: 표준화 + L2 로지스틱 회귀 (경사하강) ----
names = ["보충일", "오후 회의 수", "마감 주간", "기온", "금요일"]
X = np.column_stack([restock, meetings, deadline, temp, (weekday == 4).astype(int)]).astype(float)
tr, te = slice(0, TRAIN), slice(TRAIN, N)
mu, sd = X[tr].mean(0), X[tr].std(0)
Z = (X - mu) / sd


def fit(Z, y, lam=0.5, steps=4000, lr=0.1):
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        w -= lr * (Z.T @ (p - y) / len(y) + lam * w / len(y))
        b -= lr * (p - y).mean()
    return w, b


def auc(y, s):
    pos, neg = s[y == 1], s[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


w, b = fit(Z[tr], empty[tr])
p_te = 1 / (1 + np.exp(-(Z[te] @ w + b)))
y_te = empty[te]

# 비교 기준 두 개
base_weekday = np.array([empty[tr][weekday[tr] == d].mean() for d in range(5)])[weekday[te]]
base_restock = 1 - restock[te] + 0.0

pred = (p_te >= 0.5).astype(int)
res = {
    "n_days": N, "train_days": TRAIN, "test_days": N - TRAIN,
    "empty_rate_all": round(float(empty.mean()), 3),
    "empty_rate_restock": round(float(empty[restock == 1].mean()), 3),
    "empty_rate_no_restock": round(float(empty[restock == 0].mean()), 3),
    "empty_rate_deadline": round(float(empty[deadline == 1].mean()), 3),
    "empty_rate_normal_week": round(float(empty[deadline == 0].mean()), 3),
    "auc": {"요일 평균": round(auc(y_te, base_weekday), 3),
            "보충일 규칙": round(auc(y_te, base_restock), 3),
            "로지스틱 회귀": round(auc(y_te, p_te), 3)},
    "accuracy_at_0.5": round(float((pred == y_te).mean()), 3),
    "confusion": {"tp": int(((pred == 1) & (y_te == 1)).sum()), "fp": int(((pred == 1) & (y_te == 0)).sum()),
                  "fn": int(((pred == 0) & (y_te == 1)).sum()), "tn": int(((pred == 0) & (y_te == 0)).sum())},
    "coef": {n: round(float(c), 3) for n, c in zip(names, w)},
    "by_weekday": {DAYS[d]: round(float(empty[weekday == d].mean()), 3) for d in range(5)},
}
(HERE / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

# ---- 3. 그림 ----
def save(fig, name):
    fig.tight_layout(); fig.savefig(FIG / name); plt.close(fig)

# 그림 1: 요일별 동남 비율
fig, ax = plt.subplots(figsize=(9, 3.2))
vals = [res["by_weekday"][d] for d in DAYS]
ax.bar(DAYS, vals, color=[GREY if d in ("월", "목") else INK_BAR for d in DAYS], width=0.6)
for i, v in enumerate(vals):
    ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=9)
ax.set_ylim(0, 1); ax.set_ylabel("오후 3시 전 빈 날의 비율")
ax.set_title("요일별로 서랍이 빈 비율 (회색 = 아침 보충일)")
save(fig, "f1_weekday.png")

# 그림 2: 회의 수별 동남 비율
fig, ax = plt.subplots(figsize=(9, 3.2))
ks = np.arange(0, 6)
rates = [empty[np.minimum(meetings, 5) == k].mean() if (np.minimum(meetings, 5) == k).any() else np.nan for k in ks]
cnts = [int((np.minimum(meetings, 5) == k).sum()) for k in ks]
ax.plot(ks, rates, "-o", color=CLAY)
for k, r, c in zip(ks, rates, cnts):
    ax.text(k, r + 0.05, f"{r:.2f}\n({c}일)", ha="center", fontsize=8, color=MUTED)
ax.set_xticks(ks, ["0", "1", "2", "3", "4", "5+"]); ax.set_ylim(0, 1.15)
ax.set_xlabel("오후 회의 수"); ax.set_ylabel("빈 날의 비율")
ax.set_title("회의가 5개 이상인 날은 열에 아홉 번 빈다")
save(fig, "f2_meetings.png")

# 그림 3: 계수
fig, ax = plt.subplots(figsize=(9, 3.0))
order = np.argsort(w)
ax.barh([names[i] for i in order], w[order], color=[CLAY if w[i] < 0 else INK_BAR for i in order])
ax.axvline(0, color=MUTED, lw=0.8)
ax.set_xlabel("표준화 계수 (양수 = 빌 확률을 높임)")
ax.set_title("무엇이 서랍을 비우나")
save(fig, "f3_coef.png")

# 그림 4: AUC 비교
fig, ax = plt.subplots(figsize=(9, 2.6))
labels = list(res["auc"].keys()); a = list(res["auc"].values())
ax.barh(labels, a, color=[INK_BAR, INK_BAR, CLAY], height=0.55)
for i, v in enumerate(a):
    ax.text(v + 0.01, i, f"{v:.3f}", va="center", fontsize=9)
ax.axvline(0.5, color=GREY, ls="--", lw=1)
ax.set_xlim(0.4, 1.0); ax.set_xlabel(f"검증 {N - TRAIN}일 AUC")
ax.set_title("마지막 30일 검증에서의 AUC")
save(fig, "f4_auc.png")

print(json.dumps(res, ensure_ascii=False, indent=2))
