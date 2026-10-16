#!/bin/zsh
# 새 각본 파이프라인(S0~S7). qa new / qa stage / qa sim 이 부른다.
#   pipeline.sh new   <qa폴더> <ID> "<제목>" <영문-요약>   각본 뼈대를 만들고 S0
#   pipeline.sh stage <qa폴더> <ID>                       단계 상태 표
#   pipeline.sh stage <qa폴더> <ID> <Sn>                  그 단계를 한다(앞 단계가 done이어야)
#   pipeline.sh stage <qa폴더> <ID> --rerun <Sn>          그 단계를 다시 하고 뒤 단계를 stale로
#   pipeline.sh sim   <qa폴더> <ID> <탐색 스크립트>         S1: 앱을 조작하며 locate_record로 후보 기록(run.sh --explore)
# 사람 결정이 필요한 곳(S2 blocking 질문, S4 각본 승인)에서는 waiting으로 멈춘다. 대신 정하지 않는다.
set -u
cmd=$1 QA_DIR=${2:A}; shift 2
ENGINE=${0:A:h:h:h}; LIB=$ENGINE/scripts/lib; RUN=$ENGINE/scripts/run.sh
export PYTHONDONTWRITEBYTECODE=1
P=(python3 -I -B $LIB/pipeline.py)
CF=(python3 -I -B $LIB/casefile.py)
case_md() { print -l $QA_DIR/cases/$1-*.md(N) | head -1; }

stage_run() {
  local ID=$1 S=$2 work=$QA_DIR/work/$1 md; md=$(case_md $ID)
  mkdir -p $work
  case $S in
    S0)
      [[ -n $md ]] || { print "각본이 없음: $ID"; return 1; }
      if $CF parse $md > $work/case.json 2>$work/s0.err; then
        local errs; errs=$(python3 -I -B -c 'import json,sys; sys.path.insert(0,sys.argv[2]); import casefile; print("\n".join(casefile.validate(json.load(open(sys.argv[1])))))' $work/case.json $LIB)
        if [[ -n $errs ]]; then $P mark $work S0 failed "$errs"; print "$errs"; return 1; fi
        $P mark $work S0 done "항목 $(python3 -I -B -c 'import json,sys; c=json.load(open(sys.argv[1])); print(sum(len(s["items"]) for s in c["steps"]))' $work/case.json)개"
      else $P mark $work S0 failed "$(cat $work/s0.err)"; return 1; fi ;;
    S1)
      local missing; missing=$(python3 -I -B -c '
import json,sys,os
c=json.load(open(sys.argv[1])); p=sys.argv[2]; loc=json.load(open(p)) if os.path.exists(p) else {}
print(" ".join(it["display"] for s in c["steps"] for it in s["items"] if it["id"] not in loc))' $work/case.json $work/locate.json)
      if [[ -n $missing ]]; then $P mark $work S1 waiting "요소를 아직 찾지 않은 항목: $missing (qa sim $ID <탐색 스크립트>)"; print "S1 대기: $missing"; return 1; fi
      $P mark $work S1 done "모든 항목의 후보 기록" ;;
    S2)
      local out; out=$($P gaps $QA_DIR $work $ID) || return 1
      local open_; open_=$(print -r -- "$out" | python3 -I -B -c 'import json,sys; print(" ".join(json.load(sys.stdin)["open_blocking"]))')
      if [[ -n $open_ ]]; then $P mark $work S2 waiting "사람 대기: 답 없는 blocking 질문 $open_ (qa status, qa answer)"; print "S2 사람 대기: $open_"; return 1; fi
      $P mark $work S2 done "답 없는 blocking 질문 없음" ;;
    S3)
      [[ -f $QA_DIR/steps/$ID.sh ]] || { $P mark $work S3 waiting "스크립트 없음(steps/$ID.sh, AI가 locate.json·질문 답으로 작성)"; return 1; }
      $P mark $work S3 done "steps/$ID.sh" ;;
    S4)
      local out; out=$(QA_ALLOW_UNAPPROVED=0 $RUN --project $QA_DIR --check $ID 2>&1); local rc=$?
      print -r -- "$out" | tail -8
      case $rc in
        0) ;;
        5) $P mark $work S4 waiting "사람 대기: 각본·스크립트 승인 또는 규칙 확인(qa status, qa approve $ID, qa answer)"; return 1 ;;
        *) $P mark $work S4 blocked "실행 전 검사 차단"; return 1 ;;
      esac
      $P mark $work S4 done "통과" ;;
    S5)
      # 준비 상태는 매 실행 states.sh가 다시 만든다(앞 실행의 앱 상태 위에서 이어 돌리지 않는다)
      $RUN --project $QA_DIR --no-build $ID; local rc=$?
      local run; run=$(readlink $QA_DIR/results/latest)
      if (( rc )); then $P mark $work S5 failed "${run:t}"; return 1; fi
      $P mark $work S5 done "${run:t}" ;;
    S6)
      python3 -I -B $LIB/verify.py $QA_DIR/results/latest || { $P mark $work S6 failed "재현 검증 차단"; return 1; }
      $P mark $work S6 done "$(readlink $QA_DIR/results/latest | xargs basename)" ;;
    S7)
      python3 -I -B $ENGINE/scripts/pages/review.py $QA_DIR $QA_DIR/results/latest || return 1
      $P mark $work S7 done "review/index.html" ;;
    *) print "모르는 단계: $S"; return 2 ;;
  esac
}

case $cmd in
  new)
    ID=$1 TITLE=$2 SLUG=${${3:-new-case}//[^A-Za-z0-9-]/-}
    md=$(case_md $ID)
    if [[ -z $md ]]; then
      md=$QA_DIR/cases/$ID-$SLUG.md
      # 제목은 sed 식에 넣지 않는다(/·&·\ 같은 글자가 깨지지 않게)
      python3 -I -B -c 'import sys; t = open(sys.argv[1], encoding="utf-8").read(); open(sys.argv[2], "w", encoding="utf-8").write(t.replace("__ID__", sys.argv[3]).replace("__TITLE__", sys.argv[4]))' \
        $ENGINE/assets/templates/case.md $md "$ID" "$TITLE"
      print "각본 뼈대: $md (AI가 초안을 채우고, 사람이 승인한다)"
    fi
    stage_run $ID S0; $P status $QA_DIR/work/$ID ;;
  stage)
    ID=$1
    if (( $# == 1 )); then $P status $QA_DIR/work/$ID; exit 0; fi
    if [[ $2 == --rerun ]]; then $P rerun $QA_DIR/work/$ID $3; stage_run $ID $3; rc=$?; $P status $QA_DIR/work/$ID; exit $rc; fi
    stage_run $ID $2; rc=$?; $P status $QA_DIR/work/$ID; exit $rc ;;
  sim)
    ID=$1 script=${2:A}
    exec $RUN --project $QA_DIR --no-build --explore $script --explore-case $ID ;;
  *) sed -n '2,9p' $0 ;;
esac
