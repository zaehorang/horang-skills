"""앱 레포에 qa/ 폴더를 만든다(qa init). 이미 있으면 아무것도 바꾸지 않는다.

    init.py <엔진 폴더> <앱 레포 또는 그 안의 qa 폴더>

만드는 것: qa.config, states.sh, flows.sh, .gitignore, cases/QA-01-first-launch.md, steps/QA-01.sh
qa.config의 프로젝트·스킴·기기는 찾을 수 있으면 채우고(하나뿐일 때만), 못 찾으면 비워 둔다(`qa doctor`가 알려 준다).
첫 각본은 실행 전 검사(S4)를 통과하는 형태다. 실행하려면 사람이 승인해야 한다(qa approve QA-01).
"""

import json
import os
import shutil
import subprocess
import sys

SKIP_DIRS = {"Pods", ".build", "DerivedData", ".swiftpm", "Carthage", "node_modules", ".git", "qa"}


def find_xcode(repo):
    found = {"xcworkspace": [], "xcodeproj": []}
    for root, dirs, _ in os.walk(repo):
        depth = os.path.relpath(root, repo).count(os.sep)
        for d in list(dirs):
            ext = d.rsplit(".", 1)[-1] if "." in d else ""
            if ext in found:
                found[ext].append(os.path.relpath(os.path.join(root, d), repo))
                dirs.remove(d)   # 번들 안(project.xcworkspace 등)은 보지 않는다
            elif d in SKIP_DIRS or d.startswith(".") or depth >= 3:
                dirs.remove(d)
    return found


def shared_schemes(repo, path):
    d = os.path.join(repo, path, "xcshareddata", "xcschemes")
    return sorted(f[:-len(".xcscheme")] for f in os.listdir(d) if f.endswith(".xcscheme")) if os.path.isdir(d) else []


def first_iphone():
    try:
        r = subprocess.run(["xcrun", "simctl", "list", "devices", "available", "-j"], capture_output=True, text=True, timeout=30)
        devs = json.loads(r.stdout)["devices"]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return ""
    ios = sorted((rt for rt in devs if "iOS" in rt), key=lambda rt: [int(x) for x in rt.rsplit("iOS-", 1)[-1].split("-") if x.isdigit()])
    for rt in reversed(ios):
        names = [d["name"] for d in devs[rt] if d["name"].startswith("iPhone")]
        if names:
            return names[0]
    return ""


def main(engine, target):
    target = os.path.abspath(target)
    repo = os.path.dirname(target) if os.path.basename(target) == "qa" else target
    qa = os.path.join(repo, "qa")
    if os.path.exists(os.path.join(qa, "qa.config")):
        print(f"이미 있습니다: {qa}/qa.config (아무것도 바꾸지 않음)")
        return 1
    tpl = os.path.join(engine, "assets", "templates")
    x = find_xcode(repo)
    ws = x["xcworkspace"][0] if len(x["xcworkspace"]) == 1 else ""
    proj = x["xcodeproj"][0] if len(x["xcodeproj"]) == 1 and not ws else ""
    container = ws or proj
    schemes = shared_schemes(repo, proj or (x["xcodeproj"][0] if len(x["xcodeproj"]) == 1 else "")) if container else []
    scheme = schemes[0] if len(schemes) == 1 else (os.path.splitext(os.path.basename(container))[0] if container else "")
    device = first_iphone()
    cfg = open(os.path.join(tpl, "qa.config"), encoding="utf-8").read()
    for k, v in (("__PROJECT__", proj), ("__WORKSPACE__", ws), ("__SCHEME__", scheme), ("__DEVICE__", device)):
        cfg = cfg.replace(k, v)
    os.makedirs(os.path.join(qa, "cases"), exist_ok=True)
    os.makedirs(os.path.join(qa, "steps"), exist_ok=True)
    with open(os.path.join(qa, "qa.config"), "w", encoding="utf-8") as f:
        f.write(cfg)
    for src, dst in (("states.sh", "states.sh"), ("flows.sh", "flows.sh"), ("gitignore", ".gitignore"),
                     ("QA-01-first-launch.md", "cases/QA-01-first-launch.md"), ("QA-01.sh", "steps/QA-01.sh")):
        shutil.copyfile(os.path.join(tpl, src), os.path.join(qa, dst))
    print(f"만듦: {qa}")
    print(f"  프로젝트: {container or '(못 찾음: qa.config에 적기)'} · 스킴: {scheme or '(못 찾음)'} · 기본 기기: {device or '(못 찾음)'}")
    print("다음:")
    print("  1. qa.config를 확인하고 `qa doctor`")
    print("  2. cases/QA-01-first-launch.md와 states.sh·steps/QA-01.sh의 '첫 화면의 문구'를 앱의 실제 문구로")
    print("  3. `qa check` → 사람 승인 대기(exit 5)면 사람이 터미널에서 `qa approve QA-01`")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
