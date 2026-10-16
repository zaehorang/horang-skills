"""공유용 각본 리뷰 페이지 묶음을 만든다. 발행은 하지 않는다(발행은 사람 확인 뒤, 어댑터 문서의 절차로).

    share.py <qa폴더> <결과 폴더> --adapter <이름> [--out <폴더>] [--asset-map <map.json>]

공유 어댑터는 adapters/<이름>/ 에 있다: adapter.js(페이지 안에서 판단 저장·불러오기·내려받기),
adapter.py(publish_config(data) → 발행 설정), README.md(발행 절차). 페이지 템플릿은 로컬 리뷰(review.py)와 같다.

만드는 것(<폴더>, 기본 <qa폴더>/share)
  index.html        같은 템플릿, mode=share, 어댑터 스크립트 포함
  assets.json       올릴 자산 목록: [{"key": 페이지 안 경로, "file": 로컬 파일, "type": 종류, "bytes": 크기}] (영상·사진)
  publish.json      어댑터가 만든 발행 설정
--asset-map: 자산을 올린 뒤 받은 {key: url}. 주면 페이지가 그 url로 영상·사진을 연다.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review  # noqa: E402


def load_adapter(name):
    d = os.path.join(HERE, "adapters", name or "")
    if not name or not os.path.isdir(d):
        have = sorted(x for x in os.listdir(os.path.join(HERE, "adapters")) if not x.startswith(("_", ".")))
        sys.exit(f"공유 어댑터를 고르세요: --adapter <{'|'.join(have)}>")
    spec = importlib.util.spec_from_file_location(f"qa_share_adapter_{name}", os.path.join(d, "adapter.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, open(os.path.join(d, "adapter.js"), encoding="utf-8").read()


def main(argv):
    qa_dir, run_dir = os.path.abspath(argv[0]), argv[1]
    opt = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None
    mod, js = load_adapter(opt("--adapter"))
    out = os.path.abspath(opt("--out") or os.path.join(qa_dir, "share"))
    amap = json.load(open(opt("--asset-map"))) if opt("--asset-map") else {}
    os.makedirs(out, exist_ok=True)
    assets = {}

    def rel(p):
        p = os.path.realpath(p)
        key = os.path.relpath(p, os.path.realpath(run_dir))
        assets[key] = p
        return key

    data = review.build(qa_dir, run_dir, rel)
    data["mode"] = "share"
    data["assetMap"] = amap
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(review.render(data, js))
    lst = [{"key": k, "file": f, "type": "video" if f.endswith(".mp4") else "image", "bytes": os.path.getsize(f)}
           for k, f in sorted(assets.items())]
    json.dump(lst, open(os.path.join(out, "assets.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(mod.publish_config(data), open(os.path.join(out, "publish.json"), "w"), ensure_ascii=False, indent=1)
    missing = [a["key"] for a in lst if a["key"] not in amap]
    print(f"공유용 묶음: {out} (자산 {len(lst)}개, {sum(a['bytes'] for a in lst) / 1e6:.1f}MB"
          + (f", 아직 url 없는 자산 {len(missing)}개" if missing else "") + "). 발행하지 않았음")


if __name__ == "__main__":
    main(sys.argv[1:])
