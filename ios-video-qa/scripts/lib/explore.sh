# 탐색 어휘(S1 요소 찾기). run.sh --explore 가 core.sh 다음에 source한다. 앱 문구는 없다.
#   locate_record <항목 표시번호 n.k> <질의…>   지금 화면에서 질의에 맞는 후보 전부를 locate.json에 기록
#   explore_dump [이름]                         지금 화면의 요소 목록을 work/<ID>/explore/<이름>.txt 로
# 탐색은 판정이 아니다. 고르지 않고 후보를 전부 남긴다(고르는 규칙은 S2 질문으로 사람이 정한다).

locate_record() {
  _guard
  local disp=$1; shift
  _tree_get
  local tf; tf=$(print -r -- "$_TREE" | python3 -I -B $JUDGE treesave $TREES)
  local shot=$OUT/locate-$disp.png
  drv_screenshot $shot
  python3 -I -B $LIB/pipeline.py locate-add $QA_WORK $disp $TREES/$tf $shot "$@" || fail_script "요소 찾기 기록 실패" --dev "$disp $*"
}
explore_dump() {
  _guard
  mkdir -p $OUT
  drv_q dump > $OUT/${1:-screen}.txt
  ui_info "화면 목록: ${1:-screen}.txt ($(wc -l < $OUT/${1:-screen}.txt | tr -d ' ')줄)"
}
