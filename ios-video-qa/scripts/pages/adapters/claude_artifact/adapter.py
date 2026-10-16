"""공유 어댑터: claude.ai Artifact. 이 폴더 밖에서는 이 이름을 쓰지 않는다.

publish_config(data): Artifact 발행 설정(publish.json). 판단은 페이지 db의 reviews/<보는 사람 id>에 저장한다
(보기는 볼 수 있는 사람 누구나, 쓰기는 자기 문서만). 영상·사진은 그 페이지의 자산 저장소에 올린다.
"""

CAPABILITIES = {
    "db": {"rules": [{"path": "reviews", "read": "view", "write": "owner"},
                     {"path": "reviews/{self}", "write": "interact"}]},
    "user": {},
    "downloads": True,
    "assets": {},
}


def publish_config(data):
    return {"title": "각본 리뷰", "description": f"{data['run']} 실행의 각본·근거와 항목별 판단(로그인하면 저장)",
            "capabilities": CAPABILITIES, "icon": "checklist"}
