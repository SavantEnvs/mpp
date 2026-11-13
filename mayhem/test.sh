#!/usr/bin/env bash
#
# mayhem/test.sh — known-answer oracle for MPP's software bitstream parsers. mayhem/build.sh built
# /mayhem/parse_probe with normal flags (no sanitizers); each case feeds a seed to one parser and
# compares the exact line it reports (tasks/frames/parse errors and the picture size the parser
# recovered from the headers) against the value the bitstream was constructed with.
set -uo pipefail
[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH
: "${SRC:=/mayhem}"
cd "$SRC"

emit_ctrf() {
  local tool="$1" passed="$2" failed="$3" skipped="${4:-0}" pending="${5:-0}" other="${6:-0}"
  local tests=$(( passed + failed + skipped + pending + other ))
  cat > "${CTRF_REPORT:-$SRC/ctrf-report.json}" <<JSON
{
  "results": {
    "tool": { "name": "$tool" },
    "summary": {
      "tests": $tests,
      "passed": $passed,
      "failed": $failed,
      "pending": $pending,
      "skipped": $skipped,
      "other": $other
    }
  }
}
JSON
  printf 'CTRF {"results":{"tool":{"name":"%s"},"summary":{"tests":%d,"passed":%d,"failed":%d,"pending":%d,"skipped":%d,"other":%d}}}\n' \
    "$tool" "$tests" "$passed" "$failed" "$pending" "$skipped" "$other"
  [ "$failed" -eq 0 ]
}

PROBE="/mayhem/parse_probe"
[ -x "$PROBE" ] || { echo "missing $PROBE (mayhem/build.sh should have built it)" >&2; emit_ctrf "mpp-parse-probe" 0 1; exit 1; }

passed=0
failed=0

# <codec> <seed under mayhem/fuzz_<t>/testsuite> <fuzz dir> <expected probe line>
check() {
  local codec="$1" dir="$2" seed="$3" want="$4" got
  got="$("$PROBE" "$codec" "$SRC/mayhem/$dir/testsuite/$seed" 2>/dev/null | grep '^codec=' | head -n1)"
  if [ "$got" = "$want" ]; then
    passed=$((passed + 1))
  else
    failed=$((failed + 1))
    echo "FAIL $codec/$seed" >&2
    echo "  want: $want" >&2
    echo "  got:  $got" >&2
  fi
}

check h264  fuzz_h264  idr_64x48.bin      "codec=h264 tasks=1 frames=1 parse_errors=0 width=64 height=48"
check h264  fuzz_h264  idr3_80x64.bin     "codec=h264 tasks=1 frames=1 parse_errors=0 width=80 height=64"
check h264  fuzz_h264  idr_128x96.bin     "codec=h264 tasks=1 frames=1 parse_errors=0 width=128 height=96"
check h264  fuzz_h264  headers_only.bin   "codec=h264 tasks=0 frames=0 parse_errors=0 width=0 height=0"
check jpeg  fuzz_jpeg  yuv420_40x24.bin   "codec=jpeg tasks=1 frames=1 parse_errors=0 width=40 height=24"
check jpeg  fuzz_jpeg  yuv422_32x16.bin   "codec=jpeg tasks=1 frames=1 parse_errors=0 width=32 height=16"
check jpeg  fuzz_jpeg  yuv444_16x16.bin   "codec=jpeg tasks=1 frames=1 parse_errors=0 width=16 height=16"
check mpeg2 fuzz_mpeg2 seq_pic_64x48.bin  "codec=mpeg2 tasks=1 frames=1 parse_errors=0 width=64 height=48"
check mpeg2 fuzz_mpeg2 seq_pic_176x144.bin "codec=mpeg2 tasks=1 frames=1 parse_errors=0 width=176 height=144"
check vp8   fuzz_vp8   key_64x48.bin      "codec=vp8 tasks=1 frames=1 parse_errors=0 width=64 height=48"
check vp8   fuzz_vp8   key_176x144.bin    "codec=vp8 tasks=1 frames=1 parse_errors=0 width=176 height=144"
check vp9   fuzz_vp9   key_64x64.bin      "codec=vp9 tasks=1 frames=1 parse_errors=0 width=64 height=64"
check vp9   fuzz_vp9   key_128x96.bin     "codec=vp9 tasks=1 frames=1 parse_errors=0 width=128 height=96"
check mpeg4 fuzz_mpeg4 vol_vop_64x48.bin  "codec=mpeg4 tasks=1 frames=1 parse_errors=0 width=64 height=48"
check mpeg4 fuzz_mpeg4 vol_vop_176x144.bin "codec=mpeg4 tasks=1 frames=1 parse_errors=0 width=176 height=144"
check h263  fuzz_h263  psc_qcif.bin       "codec=h263 tasks=1 frames=1 parse_errors=0 width=176 height=144"
check h263  fuzz_h263  psc_cif.bin        "codec=h263 tasks=1 frames=1 parse_errors=0 width=352 height=288"

emit_ctrf "mpp-parse-probe" "$passed" "$failed"
