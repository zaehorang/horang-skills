"""보고서와 같은 톤의 matplotlib 스타일.

사용법: 그림 스크립트 맨 위에서
    import sys; sys.path.insert(0, "<이 폴더>")
    from mpl_style import apply, INK_BAR, CLAY, OLIVE, GREY
    apply()
또는 아래 rcParams 블록과 색 상수를 그림 스크립트에 그대로 복사한다(제출 코드가 스킬 폴더에 의존하지 않게 하려면 복사).
"""
import matplotlib.pyplot as plt

PAPER, INK, MUTED, RULE = "#FAF9F5", "#141413", "#5E5D59", "#C9C7BE"
INK_BAR = "#3D3D3A"   # 기본 막대·선 (먹색)
CLAY = "#D97757"      # 강조 하나: 최종안, 두 번째 계열, 음수 계수
OLIVE = "#788C5D"     # 세 번째 계열이 꼭 필요할 때만
GREY = "#C2C0B6"      # 기준선(0.5 등), gap, 보조 요소


def apply(font=("Apple SD Gothic Neo", "AppleGothic", "Noto Sans CJK KR", "NanumGothic")) -> None:
    """font: 앞에서부터 설치된 첫 글꼴을 쓴다. 한글 글꼴이 없으면 설치된 고딕으로 바꿔 넘긴다."""
    plt.rcParams.update({
        "font.family": list(font),
        "axes.unicode_minus": False,
        "figure.dpi": 100,
        "savefig.dpi": 150,
        "figure.facecolor": PAPER,     # 그림 배경 = 보고서 종이색 → 페이지와 이어져 보인다
        "savefig.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "axes.edgecolor": RULE,
        "axes.labelcolor": MUTED,
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titleweight": "bold",
        "axes.titlesize": 11,
        "axes.labelsize": 9.5,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
