#!/usr/bin/env bash
#
# mayhem/build.sh — build the MPP software-parser fuzz targets, their standalone reproducers and the
# oracle probe. Runs inside the commit image as `mayhem` in /mayhem, offline (no downloads).
set -euo pipefail

[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH

: "${SANITIZER_FLAGS=-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
: "${DEBUG_FLAGS:=-g -gdwarf-3}"
: "${CC:=clang}" ; : "${CXX:=clang++}" ; : "${LIB_FUZZING_ENGINE:=-fsanitize=fuzzer}"
: "${MAYHEM_JOBS:=$(nproc)}"
: "${COVERAGE_FLAGS=}"
export SANITIZER_FLAGS DEBUG_FLAGS CC CXX LIB_FUZZING_ENGINE MAYHEM_JOBS COVERAGE_FLAGS

SRC="${SRC:-/mayhem}"
cd "$SRC"

# UBSan checks relaxed because they fire on idioms used throughout MPP's start-up and bit readers,
# not on bugs in a parsed bitstream (everything else, incl. signed-integer-overflow, stays halting):
#   function     indirect calls through differently-typed function pointers (log/syslog wrappers)
#   null,object-size  the kmpp object table computes offsets with `&((T *)0)->member`
#   alignment    h264d_parse.c reads packed fields through casted pointers
#   shift-base   mpp_bitread.c shifts negative/high-bit values left by design
# Applied only when the sanitizer set contains UBSan, so an empty SANITIZER_FLAGS still links.
UBSAN_RELAX=""
case "$SANITIZER_FLAGS" in
  *undefined*) UBSAN_RELAX="-fno-sanitize=function,null,object-size,alignment,shift-base" ;;
esac

# 1) the library (the software parsers) with sanitizers + DWARF 3, fuzzer coverage instrumentation only
cmake -G Ninja -S "$SRC" -B "$SRC/mayhem/.build-fuzz" \
  -DBUILD_TEST=OFF -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
  -DCMAKE_C_FLAGS="$SANITIZER_FLAGS $UBSAN_RELAX $DEBUG_FLAGS -fsanitize=fuzzer-no-link" \
  -DCMAKE_CXX_FLAGS="$SANITIZER_FLAGS $UBSAN_RELAX $DEBUG_FLAGS -fsanitize=fuzzer-no-link" >/dev/null
cmake --build "$SRC/mayhem/.build-fuzz" --target rockchip_mpp_static -j"$MAYHEM_JOBS"
LIB="$SRC/mayhem/.build-fuzz/mpp/librockchip_mpp.a"

INC=""
for d in inc utils osal/inc mpp/inc mpp/base/inc kmpp/inc kmpp/base/inc mpp/common mpp/codec/inc \
         mpp/hal/inc mpp/hal/common; do
  INC="$INC -I$SRC/$d"
done
INC="$INC -I$SRC/mayhem"
LIBS="-lpthread -lm -ldl"

# 2) one harness per codec, linked twice (fuzzer + standalone), plus the LSan-off hook
$CXX $SANITIZER_FLAGS $DEBUG_FLAGS -c "$SRC/mayhem/lsan_off.cc" -o "$SRC/mayhem/.build-fuzz/lsan_off.o"
$CC $SANITIZER_FLAGS $DEBUG_FLAGS -c "$STANDALONE_FUZZ_MAIN" -o "$SRC/mayhem/.build-fuzz/standalone_main.o"

build_target() {
  local name="$1" coding="$2"
  local obj="$SRC/mayhem/.build-fuzz/$name.o"
  $CC $SANITIZER_FLAGS $UBSAN_RELAX $DEBUG_FLAGS -fsanitize=fuzzer-no-link $INC \
      -DMPP_FUZZ_CODING="$coding" -c "$SRC/mayhem/fuzz_parser.c" -o "$obj"
  $CXX $SANITIZER_FLAGS $DEBUG_FLAGS $LIB_FUZZING_ENGINE "$obj" \
      "$SRC/mayhem/.build-fuzz/lsan_off.o" "$LIB" $LIBS -o "/mayhem/$name"
  $CXX $SANITIZER_FLAGS $DEBUG_FLAGS "$obj" "$SRC/mayhem/.build-fuzz/standalone_main.o" \
      "$SRC/mayhem/.build-fuzz/lsan_off.o" "$LIB" $LIBS -o "/mayhem/$name-standalone"
}

build_target fuzz_h264  MPP_VIDEO_CodingAVC
build_target fuzz_h265  MPP_VIDEO_CodingHEVC
build_target fuzz_vp9   MPP_VIDEO_CodingVP9
build_target fuzz_av1   MPP_VIDEO_CodingAV1
build_target fuzz_mpeg2 MPP_VIDEO_CodingMPEG2
build_target fuzz_mpeg4 MPP_VIDEO_CodingMPEG4
build_target fuzz_h263  MPP_VIDEO_CodingH263
build_target fuzz_vp8   MPP_VIDEO_CodingVP8
build_target fuzz_jpeg  MPP_VIDEO_CodingMJPEG
build_target fuzz_avs   MPP_VIDEO_CodingAVS
build_target fuzz_avs2  MPP_VIDEO_CodingAVS2

# 3) oracle probe: the same parsers built with NORMAL flags (no sanitizers), for mayhem/test.sh
cmake -G Ninja -S "$SRC" -B "$SRC/mayhem/.build-oracle" \
  -DBUILD_TEST=OFF -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
  -DCMAKE_C_FLAGS="$COVERAGE_FLAGS" -DCMAKE_CXX_FLAGS="$COVERAGE_FLAGS" >/dev/null
cmake --build "$SRC/mayhem/.build-oracle" --target rockchip_mpp_static -j"$MAYHEM_JOBS"
$CC -O1 $COVERAGE_FLAGS $INC "$SRC/mayhem/parse_probe.c" \
    "$SRC/mayhem/.build-oracle/mpp/librockchip_mpp.a" $LIBS -o /mayhem/parse_probe
