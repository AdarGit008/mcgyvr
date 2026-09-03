#!/usr/bin/env bash
#
# tools/runs/campaigns/srv1-kernel-arms/1-build-ladder.sh
#   -> records/evidence/2026-09-02-srv1-kernel-arms/srv1-build-ladder.tsv
#
# Campaign steps 0 and 1 (`PLAN.md:113-118`):
#
#   0  static   cuobjdump L0..L3      free, can end the campaign early
#   1  build    L0 L1 L2 L3 L4 A3     srv2 builds, direct-push to srv1
#
# Step 0 is not a separate pass over somebody else's binaries: `cuobjdump` runs
# inside each build, on the `libggml-cuda.so` that build just produced, and its
# counts are baked into the image as `/app/kernels.txt`. An image that already
# carries this run's labels is REUSED rather than rebuilt, so re-running the
# script after the images exist is the "free" step-0 pass the doc asks for.
# Before a single BENCH row is written the ladder is GATED (guideline 6): L0/L1
# must contain tensor-core instructions and L2/L3 must not. If they do not, the
# script says so loudly and exits non-zero — no rig time is spent on a mechanism
# that did not take.
#
# THE GATE IS PER ARCH IMAGE, AND IT JUDGES ONLY WHAT THE CARD CAN LOAD. A fat
# binary holds one image per `-gencode` target and the device loads exactly one
# of them, so counting `mma.sync` over the whole `cuobjdump` output answers a
# question about images that never execute. Measured on this ladder's own
# builds: L2 and L3 each report 137748 `mma.sync` lines and ALL 137748 are in
# their sm_80 PTX image; their sm_61 image has none, and neither arm has any
# SASS at all (the arch list is virtual-only). srv1 is compute capability 7.5,
# so its driver can JIT sm_61 and cannot touch sm_80 — on the path srv1 actually
# loads, mma.sync is ABSENT. The mechanism took. A whole-binary `grep -c` said
# it had not and would have hard-stopped the campaign on a false positive.
#
# So: the counts are taken per arch image, SERVE_HOST's compute capability is
# read off the card, the verdict comes from the single image that capability
# selects (highest target <= cc; a PTX-only image is JITted, a SASS image is
# loaded as it is), and the whole per-arch breakdown is written into the KERNELS
# stamp so a reader recomputes the verdict rather than trusting one number.
# There is no override flag. A gate that can be waved through is not a gate.
#
# What lands in the artifact (ARTIFACT-CONTRACT.md §5.5):
#   ### WORKLOAD digest=none comparable_with=microbenchmark-only   (§2.1, §6.4)
#   ### START / ### RIG / ### END                                  (guideline 7)
#   ### BUILD arm=.. commit=.. image_sha256=.. cuda_architectures=.. force_mmq=..
#             ggml_native=.. cpu_all_variants=.. patched=..         (§2.4)
#   ### KERNELS arm=.. tensor_core_instructions=present|absent
#             device_cc=.. selected_arch=.. selected_kind=sass|ptx-jit
#             selected_tensor_core_lines=.. mma_sync_ptx_by_arch=..
#             hmma_sass_by_arch=..                                 (§2.5)
#   one BENCH row per rung                                          (§6.4)
#
# TWO PASSES, IN THIS ORDER, ENFORCED. The BENCH rows are NOT measured here.
# Resolved conflict §6.4: they are the step-3 `llama-bench` numbers, copied out
# of `srv1-llama-bench.tsv` and re-filed beside the stamps. So this script runs
# either side of step 3 and it must be told which:
#
#   pass 1   1-build-ladder.sh --stage build     campaign step 1
#            Builds, gates the mechanism, writes the stamps. No BENCH rows: the
#            instrument has not run yet. Exits 0 saying what is still owed.
#   step 3   3-llama-bench.sh                    the instrument
#   pass 2   1-build-ladder.sh                   (--stage all, the default)
#            Through the door as `run.sh srv1-kernel-arms build-ladder --host
#            srv1 --suffix pass2`: a same-day re-run needs its own run id.
#            Reuses the images, re-writes the file WITH the BENCH rows.
#
# The default stage REFUSES TO START when `srv1-llama-bench.tsv` is absent —
# checked before a single build, so an out-of-order run costs nothing and leaves
# nothing — and it exits non-zero if any built rung ends up with no row. `--stage
# build` is the only way to get the stamps without the rows, and it says so. The
# artifact is truncated and rewritten by each pass, so pass 2 leaves one whole
# file rather than two half ones. It never invents a number.
#
# A3 AND THE ALREADY-BUILT IMAGE. A3's Vulkan build failed configure 3/3 with
# `Could not find a package configuration file provided by "SPIRV-Headers"`:
# `libvulkan-dev glslc glslang-tools` do not pull that package in. `spirv-headers`
# is now on the apt line, and that exact fix was verified to build — the image
# `llamacpp:b10644-A3-spirvfix` (6f84d77b65c1) is on srv1 and srv2 from that
# build. This recipe now produces the `llamacpp:b10644-A3` tag the ladder
# expects, so that verified image must either be re-tagged or rebuilt.
# RECOMMENDED: RE-TAG. It already carries the full `org.mcgyvr.build.*` label set
# (arm=A3, backend=vulkan, cuda_architectures=none, force_mmq=OFF,
# ggml_native=OFF, cpu_all_variants=ON, patched=no, commit=d7a2074112d2), the
# `/app/kernels.txt` A3 needs (`cuda_library=absent`, `backend=vulkan`) and the
# same id on both hosts, so `image_matches` accepts it and the ladder reuses it
# without a build:
#     ssh srv2 docker tag llamacpp:b10644-A3-spirvfix llamacpp:b10644-A3
# Rebuilding costs ~20 minutes of srv2 and produces a bit-different image for no
# gain; do that only if you want the build re-verified from source.
#
# Hosts are parameters. Nothing here assumes it is running on srv1 or on srv2.
#
#   RUN_BUILD_HOST   where docker builds run.       default srv2   ("local" = here)
#   RUN_SERVE_HOST   where the image is loaded.     default srv1   ("local" = here)
#   RUN_TAG_PREFIX   image tag prefix (§3.1).       default llamacpp:b10644-
#   RUN_ARMS         arms to build.                 default "L0 L1 L2 L3 L4 A3"
#   RUN_LLAMACPP_REPO / RUN_LLAMACPP_COMMIT         the source under test
#   RUN_CUDA_DEVEL / RUN_CUDA_RUNTIME               the toolkit (a BUILD variable)
#   RUN_MMVQ_PATCH   L3's patch, repo-relative or absolute. Required for L3.
#   RUN_BENCH_TSV    the instrument record to project from.
#   RUN_PROJECT_PP / RUN_PROJECT_FA                 which instrument row projects
#   RUN_JOBS         build parallelism.             default 20
#   RUN_HOST / RUN_REPO / RUN_RETRY_SLEEP           read by tools/runs/_common.sh
#
# Flags:
#   --stage S     `build` = pass 1, before step 3: build, gate, stamp, no BENCH
#                 rows. `all` (default) = pass 2, after step 3: everything,
#                 and it fails loudly if the instrument record is not there.
#   --dry-run     print the exact command line for every cell, execute nothing,
#                 read nothing off the rig, write no file.
#
# Through the door only (tools/runs/run.sh): RUN_ID names the run in ### START,
# ### ROUND records the product round gate 1 checked, and the artifact lands
# in $RUN_OUT_DIR. Two passes over one file is why it is declared under
# RUN_REWRITES and not RUN_ARTIFACTS: gate 5 admits the pass-1 file only if its
# run_id names this step, moves it to srv1-build-ladder.superseded-<run_id>.tsv
# before pass 2 starts (the stamps are re-read off the images and the BENCH
# rows are projections of step 3, so nothing measured is lost, and the pass-1
# file stays beside the result), and refuses another step's file outright.
# RUN_REWRITES: srv1-build-ladder.tsv

[ -n "${RUN_ID:-}" ] || { echo "1-build-ladder.sh: RUN_ID is unset — start me through tools/runs/run.sh" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh
# shellcheck disable=SC1091  # sourced at runtime from the script's own directory
. "$HERE/../../_common.sh"
door_required

ARTIFACT=srv1-build-ladder.tsv
RUN_REL=records/evidence/2026-09-02-srv1-kernel-arms

BUILD_HOST=${RUN_BUILD_HOST:-srv2}
SERVE_HOST=${RUN_SERVE_HOST:-srv1}
TAG_PREFIX=${RUN_TAG_PREFIX:-llamacpp:b10644-}
LCPP_REPO=${RUN_LLAMACPP_REPO:-https://github.com/ggml-org/llama.cpp.git}
LCPP_COMMIT=${RUN_LLAMACPP_COMMIT:-d7a207411}
CUDA_DEVEL=${RUN_CUDA_DEVEL:-nvidia/cuda:12.8.0-devel-ubuntu24.04}
CUDA_RUNTIME=${RUN_CUDA_RUNTIME:-nvidia/cuda:12.8.0-runtime-ubuntu24.04}
JOBS=${RUN_JOBS:-20}
PROJECT_PP=${RUN_PROJECT_PP:-512}
PROJECT_FA=${RUN_PROJECT_FA:-1}

DRY_RUN=0
STAGE=all

usage() {
    sed -n '2,117p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,2\} \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --stage)
            [ "$#" -ge 2 ] || { _fail "--stage needs build or all"; exit 2; }
            STAGE=$2
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            _fail "unknown argument '$1'. See --help"
            exit 2
            ;;
    esac
    shift
done

case $STAGE in
    build | all) : ;;
    *) _fail "--stage must be 'build' (pass 1, before step 3) or 'all' (pass 2, the default); got '$STAGE'"; exit 2 ;;
esac

ROOT=$(_repo_root)
# The envelope: the door's $RUN_OUT_DIR (door_required refused without it).
# The instrument record (step 3) lives in the same envelope; the mmvq patch is
# an input filed with the 2026-09-02 record and stays there.
OUT_DIR=$RUN_OUT_DIR
OUT="$OUT_DIR/$ARTIFACT"
BENCH_TSV=${RUN_BENCH_TSV:-$OUT_DIR/srv1-llama-bench.tsv}
MMVQ_PATCH=${RUN_MMVQ_PATCH:-$ROOT/$RUN_REL/mmvq.patch}
THIS_HOST=$(hostname)

read -r -a ARM_LIST <<<"${RUN_ARMS:-L0 L1 L2 L3 L4 A3}"

declare -A KERNEL_VERDICT=()
declare -A KERNEL_SELECTED=()
declare -A BUILT_TAG=()
DEVICE_CC=

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

say() { printf '# %s\n' "$*" >&2; }

# The plan line. Printed in both modes, so a real run's log shows exactly what
# it ran and a --dry-run shows exactly what it would have.
plan() {
    local q
    q=$(printf '%q ' "$@")
    printf '+ %s\n' "${q% }"
}

dry() { [ "$DRY_RUN" -eq 1 ]; }

# Every artifact line goes through here. In --dry-run nothing is written and no
# rig is read: the values simply do not exist yet, and a placeholder for one is
# the single unacceptable output.
emit() {
    if dry; then return 0; fi
    "$@" >>"$OUT"
}

# on_host HOST CMD... — run locally when HOST is "local" or this box, else over
# ssh with every argument requoted (an arch list carries a `;`).
on_host() {
    local host=$1
    shift
    if [ "$host" = local ] || [ "$host" = "$THIS_HOST" ]; then
        "$@"
    else
        # SC2029: expanding client-side is the point — printf %q quotes every
        # argument for the remote shell, and an arch list carries a `;`.
        # shellcheck disable=SC2029
        "${RUN_SSH:-ssh}" "$host" "$(printf '%q ' "$@")"
    fi
}

plan_on_host() {
    local host=$1
    shift
    if [ "$host" = local ] || [ "$host" = "$THIS_HOST" ]; then
        plan "$@"
    else
        plan ssh "$host" -- "$@"
    fi
}

# quiet_on_host HOST CMD... — same, but the command's stdout is the value we
# want, so nothing is announced twice and nothing is executed under --dry-run.
quiet_on_host() {
    if dry; then return 1; fi
    on_host "$@"
}

# --------------------------------------------------------------------------
# the arms table (PLAN.md:39-47)
# --------------------------------------------------------------------------
#
#   L0  75-real;75-virtual      FORCE_MMQ off              local-build baseline
#   L1  75-real;75-virtual      FORCE_MMQ on               FORCE_MMQ alone
#   L2  61-virtual;80-virtual   FORCE_MMQ on               the arch spoof (= v2)
#   L3  L2 + the mmvq patch                                the ship candidate
#   L4  L0 + GGML_NATIVE=ON, no CPU_ALL_VARIANTS           the CPU build flags
#   A3  GGML_VULKAN=ON                                     a bound, not a rung
#
# L0->L1 moves force_mmq only, L1->L2 cuda_architectures only, L2->L3 patched
# only (test_a_six_variable_diff_...:73-79). GGML_BACKEND_DL follows
# CPU_ALL_VARIANTS because llama.cpp requires them together; it is not one of
# the five compared keys.

arm_spec() {
    case $1 in
        L0) printf 'backend=cuda\ncuda_architectures=75-real;75-virtual\nforce_mmq=OFF\nggml_native=OFF\ncpu_all_variants=ON\npatched=no\n' ;;
        L1) printf 'backend=cuda\ncuda_architectures=75-real;75-virtual\nforce_mmq=ON\nggml_native=OFF\ncpu_all_variants=ON\npatched=no\n' ;;
        L2) printf 'backend=cuda\ncuda_architectures=61-virtual;80-virtual\nforce_mmq=ON\nggml_native=OFF\ncpu_all_variants=ON\npatched=no\n' ;;
        L3) printf 'backend=cuda\ncuda_architectures=61-virtual;80-virtual\nforce_mmq=ON\nggml_native=OFF\ncpu_all_variants=ON\npatched=yes\n' ;;
        L4) printf 'backend=cuda\ncuda_architectures=75-real;75-virtual\nforce_mmq=OFF\nggml_native=ON\ncpu_all_variants=OFF\npatched=no\n' ;;
        A3) printf 'backend=vulkan\ncuda_architectures=none\nforce_mmq=OFF\nggml_native=OFF\ncpu_all_variants=ON\npatched=no\nicd_deps=x11-egl\n' ;;
        *)
            _fail "arm_spec: '$1' is not on this campaign's arms table (PLAN.md:39-47)"
            return 1
            ;;
    esac
}

spec_get() { printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n 1; }

tag_of() { printf '%s%s' "$TAG_PREFIX" "$1"; }

# --------------------------------------------------------------------------
# the build context
# --------------------------------------------------------------------------

CTX=
cleanup() {
    if [ -n "$CTX" ] && [ -d "$CTX" ]; then rm -rf "$CTX"; fi
    return 0
}
trap cleanup EXIT

# L3's one variable is a patch file. It is not in this repo; point
# RUN_MMVQ_PATCH at it. Checked before anything is built, because "the ship
# candidate, minus its patch" is L2 wearing L3's label.
preflight_patch() {
    local arm
    for arm in "${ARM_LIST[@]}"; do
        [ "$(spec_get "$(arm_spec "$arm")" patched)" = yes ] || continue
        [ -f "$MMVQ_PATCH" ] && continue
        if dry; then
            say "BLOCKER: $arm needs the mmvq patch and '$MMVQ_PATCH' is absent."
            say "A real run stops here. Set RUN_MMVQ_PATCH before step 1."
        else
            _fail "$arm is the patched rung and '$MMVQ_PATCH' does not exist. Set RUN_MMVQ_PATCH to the mmvq patch, or drop L3 from RUN_ARMS. A rung built without its one variable is L2 wearing L3's label"
            return 1
        fi
    done
    return 0
}

# The step-3 ordering, enforced. §6.4: the ladder's BENCH rows ARE the
# llama-bench numbers, so the default stage cannot run before the instrument
# has. Checked here, before a single image is built, so an out-of-order run
# spends nothing and writes nothing. `--stage build` is the explicit pass-1
# escape and is the only one.
preflight_instrument() {
    [ "$STAGE" = all ] || return 0
    [ -f "$BENCH_TSV" ] && return 0
    if dry; then
        say "BLOCKER: --stage all needs the step-3 instrument record and"
        say "'$BENCH_TSV' is absent. A real run stops here."
        say "Order: 1-build-ladder.sh --stage build, then 3-llama-bench.sh,"
        say "then 1-build-ladder.sh. See RUN-ORDER.md."
        return 0
    fi
    _fail "the ladder's BENCH rows ARE the step-3 llama-bench numbers (ARTIFACT-CONTRACT.md §6.4) and '$BENCH_TSV' does not exist, so there is nothing to copy. Run 'tools/runs/campaigns/srv1-kernel-arms/1-build-ladder.sh --stage build' for campaign step 1, then 'tools/runs/campaigns/srv1-kernel-arms/3-llama-bench.sh' for step 3, then this script again. Refusing now rather than writing a ladder with no rungs priced"
    return 1
}

# write_context ARM SPEC — a self-contained docker context on stdin-able tar.
# The `cuobjdump` of step 0 runs in the build stage, where the CUDA toolkit
# lives, and its counts are copied into the image. Nothing is inferred from the
# flags: the numbers come out of the binary.
write_context() {
    local arm=$1 spec=$2 backend
    backend=$(spec_get "$spec" backend)
    CTX=$(mktemp -d)
    mkdir -p "$CTX/patch"
    : >"$CTX/patch/.keep"
    kernels_counter >"$CTX/kernels-count.sh"
    if [ "$(spec_get "$spec" patched)" = yes ]; then
        if [ ! -f "$MMVQ_PATCH" ]; then
            _fail "$arm is the patched rung and '$MMVQ_PATCH' does not exist (preflight said so). A rung built without its one variable is L2 wearing L3's label"
            return 1
        fi
        cp "$MMVQ_PATCH" "$CTX/patch/mmvq.patch"
    fi
    if [ "$backend" = vulkan ]; then
        write_dockerfile_vulkan >"$CTX/Dockerfile"
    else
        write_dockerfile_cuda >"$CTX/Dockerfile"
    fi
}

# kernels_counter — step 0's whole measurement, as one POSIX shell program on
# stdout. It goes into the build context and runs inside the build stage, where
# the CUDA toolkit lives; recount_kernels runs the SAME text against an image
# that was built before this gate existed. One counter, two callers, one answer.
#
# WHY PER ARCH IMAGE. A fat binary holds one image per `-gencode` target and a
# device loads exactly one of them, so a `grep -c` over the whole `cuobjdump`
# output conflates images the device can load with images it cannot. Measured on
# this ladder's own builds: L2 and L3 each report mma_sync_ptx=137748 and all
# 137748 are in their sm_80 PTX image. srv1 is compute capability 7.5 and cannot
# load sm_80 at all; on the sm_61 image it does JIT the count is 0. The old gate
# read the 137748, called the mechanism un-taken and would have hard-stopped the
# campaign on a mechanism that had in fact taken.
#
# `cuobjdump --dump-sass` prints the PTX images' HEADERS too, arch line and all,
# so the section kind is tracked and only `Fatbin elf code:` sections are counted
# as SASS. An arch that appears in the PTX dump and in no elf section is
# virtual-only and is JITted; an arch with an elf section is loaded as it is.
kernels_counter() {
    cat <<'COUNTER'
#!/bin/sh
# kernels-count.sh LIB — one CUDA library in, one k=v block out. Every number
# comes from cuobjdump; a dump that named no arch image is an error, not a zero.
set -eu

lib=${1:?usage: kernels-count.sh LIB}
test -f "$lib"

# scan WANTKIND REGEX — reads a cuobjdump dump on stdin and reports
# "bytes=N images=N by_arch=sm_61:0,sm_80:137748 total=N", archs low to high.
scan() {
    awk -v want="$1" -v re="$2" '
        { bytes += length($0) + 1 }
        /^Fatbin ptx code:/ { kind = "ptx"; a = ""; next }
        /^Fatbin elf code:/ { kind = "elf"; a = ""; next }
        /^arch = / {
            a = (kind == want) ? $3 : ""
            if (a != "" && !(a in seen)) { seen[a] = 1; order[++n] = a; c[a] = 0 }
            next
        }
        a != "" && $0 ~ re { c[a] += 1; total += 1 }
        END {
            for (i = 1; i <= n; i++)
                for (j = i + 1; j <= n; j++) {
                    x = order[i]; y = order[j]
                    sub(/^[^0-9]*/, "", x)
                    sub(/^[^0-9]*/, "", y)
                    if (x + 0 > y + 0) { t = order[i]; order[i] = order[j]; order[j] = t }
                }
            s = ""
            for (i = 1; i <= n; i++) s = s (i > 1 ? "," : "") order[i] ":" c[order[i]]
            printf "bytes=%d images=%d by_arch=%s total=%d\n", \
                bytes + 0, n + 0, (n ? s : "none"), total + 0
        }
    '
}

get() { printf '%s\n' "$1" | tr ' ' '\n' | sed -n "s/^$2=//p"; }

ptx=$(cuobjdump --dump-ptx "$lib" | scan ptx 'mma\\.sync')
sass=$(cuobjdump --dump-sass "$lib" | scan elf 'HMMA|IMMA')

images=$(get "$ptx" images)
[ "${images:-0}" -gt 0 ] || {
    echo "kernels-count: cuobjdump --dump-ptx named no arch image in $lib" >&2
    exit 1
}

printf 'cuda_library=present\n'
printf 'mma_sync_ptx=%s\n' "$(get "$ptx" total)"
printf 'hmma_sass=%s\n' "$(get "$sass" total)"
printf 'ptx_bytes=%s\n' "$(get "$ptx" bytes)"
printf 'sass_bytes=%s\n' "$(get "$sass" bytes)"
printf 'ptx_images=%s\n' "$images"
printf 'sass_images=%s\n' "$(get "$sass" images)"
printf 'mma_sync_ptx_by_arch=%s\n' "$(get "$ptx" by_arch)"
printf 'hmma_sass_by_arch=%s\n' "$(get "$sass" by_arch)"
COUNTER
}

write_dockerfile_cuda() {
    cat <<'DOCKERFILE'
ARG BASE_DEVEL
ARG BASE_RUNTIME
FROM ${BASE_DEVEL} AS build
ARG LCPP_REPO
ARG LCPP_COMMIT
ARG ARCHS
ARG FORCE_MMQ
ARG NATIVE
ARG ALLVAR
ARG BACKEND_DL
ARG PATCHED
ARG JOBS
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake build-essential libcurl4-openssl-dev ca-certificates ninja-build \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone "$LCPP_REPO" . \
 && git checkout "$LCPP_COMMIT" \
 && git rev-parse HEAD > /commit.txt
COPY patch/ /patch/
RUN if [ "$PATCHED" = yes ]; then git apply --verbose /patch/mmvq.patch; fi
RUN cmake -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CUDA=ON \
      -DGGML_CUDA_FORCE_MMQ="$FORCE_MMQ" \
      -DCMAKE_CUDA_ARCHITECTURES="$ARCHS" \
      -DGGML_NATIVE="$NATIVE" \
      -DGGML_CPU_ALL_VARIANTS="$ALLVAR" \
      -DGGML_BACKEND_DL="$BACKEND_DL" \
      -DLLAMA_CURL=ON \
      -DBUILD_SHARED_LIBS=ON \
      -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined \
 && cmake --build build --config Release -j "$JOBS" --target llama-server llama-bench
# Step 0, inside the build that produced the library, PER ARCH IMAGE. The whole
# of the counting lives in kernels-count.sh so that the same code answers for a
# fresh build and for an image built before this gate existed (recount_kernels).
COPY kernels-count.sh /kernels-count.sh
RUN sh /kernels-count.sh /src/build/bin/libggml-cuda.so > /kernels.txt

FROM ${BASE_RUNTIME}
ARG ARM
ARG ARCHS
ARG FORCE_MMQ
ARG NATIVE
ARG ALLVAR
ARG PATCHED
ARG BASE_DEVEL
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 libcurl4 curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/bin/ /app/
COPY --from=build /kernels.txt /app/kernels.txt
COPY --from=build /commit.txt /app/commit.txt
ENV LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH
LABEL org.mcgyvr.build.arm="${ARM}" \
      org.mcgyvr.build.backend="cuda" \
      org.mcgyvr.build.cuda_architectures="${ARCHS}" \
      org.mcgyvr.build.force_mmq="${FORCE_MMQ}" \
      org.mcgyvr.build.ggml_native="${NATIVE}" \
      org.mcgyvr.build.cpu_all_variants="${ALLVAR}" \
      org.mcgyvr.build.patched="${PATCHED}" \
      org.mcgyvr.build.toolkit="${BASE_DEVEL}"
EXPOSE 8080
ENTRYPOINT ["/app/llama-server"]
DOCKERFILE
}

write_dockerfile_vulkan() {
    cat <<'DOCKERFILE'
ARG BASE_DEVEL
ARG BASE_RUNTIME
FROM ${BASE_DEVEL} AS build
ARG LCPP_REPO
ARG LCPP_COMMIT
ARG NATIVE
ARG ALLVAR
ARG BACKEND_DL
ARG JOBS
# `spirv-headers` is not optional and is not pulled in by the other three:
# without it b10644's Vulkan backend fails `configure` outright with
#   Could not find a package configuration file provided by "SPIRV-Headers"
# which is how A3 failed to build 3/3 times. With it the build completes.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake build-essential libcurl4-openssl-dev ca-certificates ninja-build \
      libvulkan-dev glslc glslang-tools spirv-headers \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone "$LCPP_REPO" . \
 && git checkout "$LCPP_COMMIT" \
 && git rev-parse HEAD > /commit.txt
RUN cmake -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CUDA=OFF \
      -DGGML_VULKAN=ON \
      -DGGML_NATIVE="$NATIVE" \
      -DGGML_CPU_ALL_VARIANTS="$ALLVAR" \
      -DGGML_BACKEND_DL="$BACKEND_DL" \
      -DLLAMA_CURL=ON \
      -DBUILD_SHARED_LIBS=ON \
      -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined \
 && cmake --build build --config Release -j "$JOBS" --target llama-server llama-bench
# A3 is a Vulkan build: there is no libggml-cuda.so to dump, and the backend
# detects tensor cores by querying VK_KHR_cooperative_matrix rather than reading
# the compute-capability integer. The step-0 question does not apply to it, and
# this file says that rather than reporting an absence it did not measure.
RUN set -eu; \
    test ! -f /src/build/bin/libggml-cuda.so; \
    { echo "cuda_library=absent"; echo "backend=vulkan"; } > /kernels.txt

FROM ${BASE_RUNTIME}
ARG ARM
ARG NATIVE
ARG ALLVAR
ARG BASE_DEVEL
ARG ICD_DEPS
# libglvnd0 libegl1 libx11-6 libxext6 ARE THE VULKAN DEVICE. The NVIDIA ICD
# the container toolkit injects (/etc/vulkan/icd.d/nvidia_icd.json ->
# libGLX_nvidia.so.0) links libGLdispatch.so.0, libX11.so.6 and libXext.so.6,
# and at init it dlopens libEGL.so.1 and returns no vkCreateInstance without
# it; --no-install-recommends pulls none of the four in behind libvulkan1.
# Without them the loader says "Failed loading library associated with ICD
# JSON libGLX_nvidia.so.0" (the linked three) or "Could not get
# 'vkCreateInstance' via 'vk_icdGetInstanceProcAddr'" (libEGL, found by
# strace on 2026-09-03), ggml_backend_vk_reg() returns NULL, and ggml
# registers the CPU backend alone, silently: that is how A3 benched the
# i5-9600K under a vulkan tag on 2026-09-02, and again — refused this time —
# on 2026-09-03. The ldconfig check below makes the build fail where the rig
# would have measured the wrong device.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 libcurl4 curl ca-certificates libvulkan1 vulkan-tools \
      libglvnd0 libegl1 libx11-6 libxext6 \
 && rm -rf /var/lib/apt/lists/*
RUN set -eu; for so in libX11.so.6 libXext.so.6 libGLdispatch.so.0 libEGL.so.1 libvulkan.so.1; do \
      ldconfig -p | grep -q "$so " || { echo "$so did not resolve: the NVIDIA Vulkan ICD cannot load in this image" >&2; exit 1; }; \
    done
WORKDIR /app
COPY --from=build /src/build/bin/ /app/
COPY --from=build /kernels.txt /app/kernels.txt
COPY --from=build /commit.txt /app/commit.txt
ENV LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH
ENV NVIDIA_DRIVER_CAPABILITIES=all
LABEL org.mcgyvr.build.arm="${ARM}" \
      org.mcgyvr.build.backend="vulkan" \
      org.mcgyvr.build.cuda_architectures="none" \
      org.mcgyvr.build.force_mmq="OFF" \
      org.mcgyvr.build.ggml_native="${NATIVE}" \
      org.mcgyvr.build.cpu_all_variants="${ALLVAR}" \
      org.mcgyvr.build.patched="no" \
      org.mcgyvr.build.icd_deps="${ICD_DEPS}" \
      org.mcgyvr.build.toolkit="${BASE_DEVEL}"
EXPOSE 8080
ENTRYPOINT ["/app/llama-server"]
DOCKERFILE
}

# --------------------------------------------------------------------------
# build / reuse / push
# --------------------------------------------------------------------------

# THE CROSS-SCRIPT LABEL CONTRACT. tools/runs/campaigns/srv1-kernel-arms/4-kernel-arms.sh reads
# `org.mcgyvr.build.<key>` off every `llamacpp:b10644-*` image and REFUSES to
# write a `### BUILD` stamp for a tag that does not carry one (ARTIFACT-CONTRACT
# section 2.4, behaviour 3). This script is the producer of those images and
# therefore of those labels. The keys it reads are:
#
#   commit  image_sha256  cuda_architectures  force_mmq  ggml_native
#   cpu_all_variants  patched
#
# Five of them are build variables, known before the build, and are set by
# `LABEL` in the Dockerfiles below. `commit` is NOT known before the build -- it
# is what `git checkout` resolved to, and only the built image knows it -- so it
# is applied afterwards by `label_build_facts`, read out of the image's own
# /app/commit.txt. `image_sha256` cannot be a label at all: an image's id is a
# hash of its own metadata, so a label naming it cannot exist. The consumer has
# a documented, non-guessing fallback for exactly that key -- it asks docker for
# `{{.Id}}` -- and that is the whole of the exception. Every other key is set
# here.
label_of() {
    quiet_on_host "$BUILD_HOST" docker image inspect \
        --format "{{index .Config.Labels \"org.mcgyvr.build.$2\"}}" "$1" 2>/dev/null
}

# label_build_facts TAG COMMIT — a metadata-only second build FROM the image
# just made, adding the one label that could not be known before it existed.
# Idempotent: a reused image is relabelled with the same value it already has.
label_build_facts() {
    local tag=$1 commit=$2
    printf '+ printf FROM %s / LABEL org.mcgyvr.build.commit=%s | %s\n' \
        "$tag" "$commit" \
        "$(plan_on_host "$BUILD_HOST" docker build -t "$tag" - | sed 's/^+ //')"
    if dry; then return 0; fi
    printf 'FROM %s\nLABEL org.mcgyvr.build.commit=%s\n' "$tag" "$commit" |
        on_host "$BUILD_HOST" docker build -t "$tag" -
}

# image_matches TAG SPEC — true when a tag already on the build host was built
# by this script for this arm with exactly these five variables. Only then may
# it be reused; otherwise the ladder would compare an image to its own name.
image_matches() {
    local tag=$1 spec=$2 key want got
    quiet_on_host "$BUILD_HOST" docker image inspect "$tag" >/dev/null 2>&1 || return 1
    for key in cuda_architectures force_mmq ggml_native cpu_all_variants patched; do
        want=$(spec_get "$spec" "$key")
        got=$(label_of "$tag" "$key") || return 1
        [ "$got" = "$want" ] || return 1
    done
    # A vulkan image is also held to icd_deps: the 2026-09-02 A3 image had
    # libvulkan1 and no libX11/libXext/libGLdispatch, the 2026-09-03 rebuild
    # (icd_deps=x11) had those and no libEGL, and under both the NVIDIA ICD
    # never came up and the tag benched the CPU. An image whose label is not
    # the current value is one of those, and it is rebuilt rather than reused
    # under the same tag.
    if [ "$(spec_get "$spec" backend)" = vulkan ]; then
        want=$(spec_get "$spec" icd_deps)
        got=$(label_of "$tag" icd_deps) || return 1
        [ "$got" = "$want" ] || return 1
    fi
    return 0
}

build_arm() {
    local arm=$1 spec=$2 tag=$3 backend
    backend=$(spec_get "$spec" backend)
    local args=(
        docker build
        --build-arg "BASE_DEVEL=$CUDA_DEVEL"
        --build-arg "BASE_RUNTIME=$CUDA_RUNTIME"
        --build-arg "LCPP_REPO=$LCPP_REPO"
        --build-arg "LCPP_COMMIT=$LCPP_COMMIT"
        --build-arg "ARM=$arm"
        --build-arg "NATIVE=$(spec_get "$spec" ggml_native)"
        --build-arg "ALLVAR=$(spec_get "$spec" cpu_all_variants)"
        --build-arg "BACKEND_DL=$(spec_get "$spec" cpu_all_variants)"
        --build-arg "JOBS=$JOBS"
    )
    if [ "$backend" = cuda ]; then
        args+=(
            --build-arg "ARCHS=$(spec_get "$spec" cuda_architectures)"
            --build-arg "FORCE_MMQ=$(spec_get "$spec" force_mmq)"
            --build-arg "PATCHED=$(spec_get "$spec" patched)"
        )
    else
        args+=(--build-arg "ICD_DEPS=$(spec_get "$spec" icd_deps)")
    fi
    args+=(-t "$tag" -)

    say "$arm: $backend build on $BUILD_HOST -> $tag"
    printf '+ tar -C <context> -c . | %s\n' \
        "$(plan_on_host "$BUILD_HOST" "${args[@]}" | sed 's/^+ //')"
    if dry; then return 0; fi

    write_context "$arm" "$spec" || return 1
    # Guideline 8: three attempts before a failure is believed.
    if retry3 tar_build "$CTX" "${args[@]}"; then
        rm -rf "$CTX"
        CTX=
        return 0
    fi
    rm -rf "$CTX"
    CTX=
    return 1
}

# The context reaches docker on stdin, so the same call works locally and over
# ssh without copying a directory to the build host first.
tar_build() {
    local ctx=$1
    shift
    tar -C "$ctx" -c . | on_host "$BUILD_HOST" "$@"
}

push_arm() {
    local tag=$1
    if [ "$BUILD_HOST" = "$SERVE_HOST" ]; then
        say "build host and serve host are both '$SERVE_HOST'; no push needed"
        return 0
    fi
    printf '+ %s | %s\n' \
        "$(plan_on_host "$BUILD_HOST" docker save "$tag" | sed 's/^+ //')" \
        "$(plan_on_host "$SERVE_HOST" docker load | sed 's/^+ //')"
    if dry; then return 0; fi
    on_host "$BUILD_HOST" docker save "$tag" | on_host "$SERVE_HOST" docker load
}

# --------------------------------------------------------------------------
# step 0: what the binary contains
# --------------------------------------------------------------------------

# read_kernels TAG — the counts cuobjdump wrote into the image at build time.
read_kernels() {
    quiet_on_host "$BUILD_HOST" docker run --rm --entrypoint cat "$1" /app/kernels.txt
}

# The recount, as one POSIX program. An image built before the per-arch gate
# existed carries a `/app/kernels.txt` with only the conflated totals, and a
# total cannot be split back into images after the fact. Rather than trust it or
# rebuild the arm, step 0 is simply RE-RUN, now, against that image's own
# library: the library is streamed out of the image (following its symlink), and
# the same kernels_counter text is run over it inside the CUDA devel image, which
# is where cuobjdump lives. Read-only, no GPU, nothing built, nothing served.
# SC2016: the $-expansions belong to the remote shell that runs this text, not
# to this one. Single quotes are exactly right.
# shellcheck disable=SC2016
RECOUNT_SH='
set -eu
tag=$1
devel=$2
counter=$3
d=$(mktemp -d)
trap "rm -rf \"$d\"" EXIT INT TERM
printf "%s\n" "$counter" > "$d/kernels-count.sh"
docker run --rm --entrypoint sh "$tag" -c "exec cat \"\$(readlink -f /app/libggml-cuda.so)\"" > "$d/lib.so"
test -s "$d/lib.so"
docker run --rm -v "$d:/dump:ro" --entrypoint sh "$devel" /dump/kernels-count.sh /dump/lib.so
'

# recount_kernels TAG — the same k=v block read_kernels would have returned, had
# the image been built by this version of the recipe.
recount_kernels() {
    quiet_on_host "$BUILD_HOST" sh -c "$RECOUNT_SH" recount \
        "$1" "$CUDA_DEVEL" "$(kernels_counter)"
}

# device_cc — the compute capability of the card the images are LOADED on, read
# off that card. The gate is a question about the SELECTED path and this number
# is what selects it, so it is measured on SERVE_HOST rather than assumed from
# the host's name or from the arch list the build was given.
device_cc() {
    local cc
    cc=$(quiet_on_host "$SERVE_HOST" nvidia-smi --query-gpu=compute_cap --format=csv,noheader) || cc=
    cc=$(printf '%s' "${cc%%$'\n'*}" | tr -d '[:space:]')
    case ${cc:-x} in
        [0-9]*.[0-9]*) ;;
        *)
            _fail "device_cc: '$SERVE_HOST' reported compute_cap='$cc'. Which arch image the driver loads is decided by that number, so without it the gate cannot say what runs and will not guess"
            return 1
            ;;
    esac
    printf '%s' "$cc"
}

# reachable_image CC PTX_BY_ARCH SASS_BY_ARCH -> "ARCH KIND COUNT"
#
# Of the images in the fat binary, a device loads the highest whose target is
# <= its own compute capability: an `sm_NN` SASS image runs as it is, a PTX-only
# `compute_NN` image is JITted by the driver. Everything above the device's
# capability is unreachable and says nothing about what executes. Returns 2 when
# the library holds no image this device could load at all.
reachable_image() {
    local cc=$1 ptx=$2 sass=$3
    local ccnum best=-1 best_arch=none best_kind=none best_count=0
    local kind list pair arch cnt num
    local -a pairs=()
    ccnum=${cc//./}
    case ${ccnum:-x} in
        *[!0-9]*)
            _fail "reachable_image: compute capability '$cc' is not a number like 7.5"
            return 1
            ;;
    esac
    # SASS first, so that at one arch a real image outranks the same arch's PTX:
    # the driver runs the cubin and never reaches the JIT.
    for kind in sass ptx-jit; do
        if [ "$kind" = sass ]; then list=$sass; else list=$ptx; fi
        [ -n "$list" ] && [ "$list" != none ] || continue
        IFS=, read -r -a pairs <<<"$list"
        for pair in "${pairs[@]}"; do
            arch=${pair%%:*}
            cnt=${pair#*:}
            num=${arch#sm_}
            case ${num:-x}${cnt:-x} in
                *[!0-9]*)
                    _fail "reachable_image: '$pair' is not sm_NN:COUNT, so the per-arch breakdown cannot be read and no image can be selected"
                    return 1
                    ;;
            esac
            [ "$num" -le "$ccnum" ] || continue
            if [ "$num" -gt "$best" ]; then
                best=$num
                best_arch=$arch
                best_kind=$kind
                best_count=$cnt
            fi
        done
    done
    [ "$best" -ge 0 ] || return 2
    printf '%s %s %s' "$best_arch" "$best_kind" "$best_count"
}

# kernels_verdict KERNELSTXT CC -> "VERDICT ARCH KIND COUNT"
#
# Guideline 6 asks what runs on the SELECTED path. The old form of this function
# asked a different question — `grep -c` over the whole cuobjdump output — and
# got a different answer: L2 and L3 each report mma_sync_ptx=137748, every one of
# those lines is in their sm_80 PTX image, srv1 is cc 7.5 and cannot load sm_80,
# and on the sm_61 image srv1 does JIT the count is 0. The mechanism had taken;
# the gate would have stopped the campaign saying it had not. So the verdict is
# read off the ONE image this device selects, and the whole per-arch breakdown is
# stamped beside it so a reader recomputes rather than trusts.
#
# An unparseable record is a refusal, never an "absent".
kernels_verdict() {
    local txt=$1 cc=$2 lib ptx sass sel rc arch kind count
    lib=$(spec_get "$txt" cuda_library)
    if [ "$lib" = absent ]; then
        printf 'not-applicable none none 0'
        return 0
    fi
    ptx=$(spec_get "$txt" mma_sync_ptx_by_arch)
    sass=$(spec_get "$txt" hmma_sass_by_arch)
    if [ -z "$ptx" ]; then
        _fail "kernels_verdict: this cuobjdump record carries no mma_sync_ptx_by_arch, so it cannot say WHICH arch image holds its counts. A total over every image in a fat binary is not a statement about the one the device loads, and no verdict is read from it"
        return 1
    fi
    rc=0
    sel=$(reachable_image "$cc" "$ptx" "$sass") || rc=$?
    if [ "$rc" -eq 2 ]; then
        _fail "kernels_verdict: the library holds ptx=[$ptx] sass=[$sass] and a compute-capability-$cc device can load none of them. That image cannot run on the serve host at all — a build error, not an 'absent'"
        return 1
    fi
    [ "$rc" -eq 0 ] || return 1
    read -r arch kind count <<<"$sel"
    if [ "$count" -gt 0 ]; then
        printf 'present %s %s %s' "$arch" "$kind" "$count"
    else
        printf 'absent %s %s %s' "$arch" "$kind" "$count"
    fi
}

# The gate, guideline 6. Free, and it ends the campaign before rig time is spent.
# Every verdict here is about the image SERVE_HOST's card actually selects; an
# image the card cannot load is not evidence about anything it runs.
gate_the_mechanism() {
    local rung want bad=
    for rung in L0 L1 L2 L3; do
        case $rung in
            L0 | L1) want=present ;;
            *) want=absent ;;
        esac
        [ "${KERNEL_VERDICT[$rung]:-unread}" = "$want" ] && continue
        bad="${bad:+$bad; }$rung=${KERNEL_VERDICT[$rung]:-unread}"
        bad="$bad on ${KERNEL_SELECTED[$rung]:-no selected image} (wanted $want)"
    done
    if [ -n "$bad" ]; then
        printf '\n' >&2
        say "=============================================================="
        say "STOP. The mechanism is not what the ladder claims: $bad"
        say "L0/L1 must carry tensor-core instructions on the image a cc"
        say "$DEVICE_CC card loads, and L2/L3 must not. Each verdict above names"
        say "that image; the KERNELS stamps carry the per-arch counts it came"
        say "from, so it can be recomputed rather than believed."
        say "If L2/L3 still contain mma.sync on the SELECTED path the arch spoof"
        say "did not take, and no throughput number can be attributed to removing"
        say "it (PLAN.md guideline 6). Not one second of rig time"
        say "is worth spending on the arms below until this reads clean."
        say "=============================================================="
        return 1
    fi
    say "gate passed on the cc $DEVICE_CC path: L0/L1 present, L2/L3 absent."
    for rung in L0 L1 L2 L3; do
        say "  $rung: ${KERNEL_SELECTED[$rung]:-?} -> ${KERNEL_VERDICT[$rung]:-?}"
    done
}

# --------------------------------------------------------------------------
# §6.4: the BENCH rows are copied from the instrument record, never measured
# --------------------------------------------------------------------------

# project_row ARM TAG — one BENCH row per rung, lifted out of
# srv1-llama-bench.tsv. Prints `host<TAB>pp<TAB>tg<TAB>srcline` or nothing.
instrument_row() {
    local arm=$1
    awk -v arm="$arm" -v want_fa="$PROJECT_FA" -v want_pp="$PROJECT_PP" '
        BEGIN { FS = "\t" }
        /^###/ { next }
        NF < 3 { next }
        $3 != "BENCH" { next }
        {
            split($2, w, " ")
            if (w[1] != arm "-p" want_pp) next
            pp = ""; tg = ""; fa = ""; a = ""
            for (i = 4; i <= NF; i++) {
                if ($i ~ /^pp=/) pp = substr($i, 4)
                else if ($i ~ /^tg=/) tg = substr($i, 4)
                else if ($i ~ /^fa=/) fa = substr($i, 4)
                else if ($i ~ /^arm=/) a = substr($i, 5)
            }
            if (fa != want_fa || a != arm) next
            if (pp == "" || tg == "") next
            print $1 "\t" pp "\t" tg "\t" NR
            exit
        }
    ' "$BENCH_TSV"
}

project_bench() {
    local arm tag line src_host pp tg srcline saved missing=
    if [ "$STAGE" = build ]; then
        say "--stage build: pass 1, before step 3. No BENCH row is written,"
        say "because the instrument has not run. This file is INCOMPLETE by"
        say "design: it carries the stamps and no rung is priced."
        say "Next: tools/runs/campaigns/srv1-kernel-arms/3-llama-bench.sh, then re-run this script with"
        say "no --stage. The images are reused, so pass 2 is cheap."
        return 0
    fi
    if [ ! -f "$BENCH_TSV" ]; then
        # preflight_instrument refuses this before anything is built; reaching
        # here means the record was deleted mid-run.
        _fail "$BENCH_TSV vanished between the preflight and the projection. Nothing is copied and nothing is invented"
        return 1
    fi
    for arm in "${ARM_LIST[@]}"; do
        tag=${BUILT_TAG[$arm]:-}
        [ -n "$tag" ] || continue
        line=$(instrument_row "$arm") || line=
        if [ -z "$line" ]; then
            missing="${missing:+$missing }$arm"
            continue
        fi
        IFS=$'\t' read -r src_host pp tg srcline <<<"$line"
        # The row is the instrument's measurement; it keeps the instrument's
        # host, because this script may well be running on the build box.
        saved=${RUN_HOST:-}
        RUN_HOST=$src_host
        emit row "$(arm_label "$arm" "p$PROJECT_PP")" BENCH \
            "arm=$arm" "img=$tag" "pp=$pp" "tg=$tg" \
            "projected_from=srv1-llama-bench.tsv:$srcline" \
            "src_pp_tokens=$PROJECT_PP" "src_fa=$PROJECT_FA"
        if [ -n "$saved" ]; then RUN_HOST=$saved; else unset RUN_HOST; fi
    done
    if [ -n "$missing" ]; then
        say "the instrument record has no -p$PROJECT_PP -fa$PROJECT_FA row for:$missing"
        say "those rungs stay unprojected. A rung with no measurement is RED,"
        say "which is the correct reading of a rung that was not measured."
        _fail "$BENCH_TSV prices no rung for:$missing. The ladder is not complete and this pass did not finish the artifact. Bench those arms (tools/runs/campaigns/srv1-kernel-arms/3-llama-bench.sh) and re-run"
        return 1
    fi
}

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

main() {
    local arm spec tag kernels verdict commit image_id reused
    local ksource sel_arch sel_kind sel_count
    local -a counts

    say "artifact: $OUT"
    say "build host: $BUILD_HOST   serve host: $SERVE_HOST   arms: ${ARM_LIST[*]}"
    if [ "$STAGE" = build ]; then
        say "stage: build (pass 1, campaign step 1 — stamps only, no BENCH rows)"
    else
        say "stage: all (pass 2, after step 3 — stamps and BENCH rows)"
    fi
    if dry; then say "--dry-run: printing the plan, reading no rig, writing no file"; fi

    preflight_patch || return 1
    preflight_instrument || return 1
    # The gate needs the capability of the card that will LOAD these images, and
    # it comes off that card. Read once, before anything is built, so a serve
    # host that cannot answer stops the run for free.
    for arm in "${ARM_LIST[@]}"; do
        [ "$(spec_get "$(arm_spec "$arm")" backend)" = cuda ] || continue
        if dry; then
            plan_on_host "$SERVE_HOST" nvidia-smi --query-gpu=compute_cap --format=csv,noheader
            say "the gate judges only the arch images that compute capability can load"
        else
            DEVICE_CC=$(device_cc) || return 1
            say "gate target: $SERVE_HOST reports compute capability $DEVICE_CC"
        fi
        break
    done

    if ! dry; then
        mkdir -p "$(dirname "$OUT")"
        : >"$OUT"
    fi

    # §2.1 / §6.4. llama-bench shares no prompt, template or sampler with the
    # serving drivers, and a rung quoted as a serving gain is the misreading
    # guideline 4 blocks. Both microbenchmark files carry this.
    emit microbench_stamp
    emit start_stamp
    emit round_stamp
    emit rig_stamp

    for arm in "${ARM_LIST[@]}"; do
        spec=$(arm_spec "$arm")
        tag=$(tag_of "$arm")
        reused=no

        if image_matches "$tag" "$spec"; then
            reused=yes
            say "$arm: $tag already carries this arm's five variables; reusing it"
            say "$arm: this is step 0's free pass — no build, just the binary"
        elif ! build_arm "$arm" "$spec" "$tag"; then
            emit refused "$(arm_label "$arm" build)" \
                "arm=$arm" "img=$tag" "checkpoint_quant=none" \
                -- "the $arm image did not build on $BUILD_HOST after $((${RUN_TRIES:-3})) attempts; there is no library to dump and no rung to bench"
            say "$arm: BUILD FAILED. Recorded as a refusal (guideline 8) and skipped."
            continue
        fi

        # Step 0 for this arm, before anything is benched with it.
        if dry; then
            plan_on_host "$BUILD_HOST" docker run --rm --entrypoint cat "$tag" /app/kernels.txt
            plan_on_host "$BUILD_HOST" docker run --rm --entrypoint cat "$tag" /app/commit.txt
            label_build_facts "$tag" '<commit read from /app/commit.txt>'
            plan_on_host "$BUILD_HOST" docker image inspect --format '{{.Id}}' "$tag"
            push_arm "$tag"
            BUILT_TAG["$arm"]=$tag
            continue
        fi

        kernels=$(read_kernels "$tag") || kernels=
        ksource=cuobjdump
        if [ -z "$kernels" ]; then
            emit refused "$(arm_label "$arm" kernels)" \
                "arm=$arm" "img=$tag" "checkpoint_quant=none" "tries=3" \
                -- "the $arm image carries no /app/kernels.txt, so cuobjdump never reported on its libraries and the mechanism is unchecked for this arm"
            say "$arm: no cuobjdump record in the image. Refused, not guessed."
            continue
        fi
        # An image built before the per-arch gate carries only the conflated
        # totals. A total cannot be split back into images, so step 0 is re-run
        # against that image's own library rather than read wrong or rebuilt.
        if [ "$(spec_get "$kernels" cuda_library)" = present ] &&
            [ -z "$(spec_get "$kernels" mma_sync_ptx_by_arch)" ]; then
            say "$arm: this image's /app/kernels.txt predates the per-arch gate"
            say "$arm: re-running cuobjdump on its own library (no rebuild)"
            kernels=$(recount_kernels "$tag") || kernels=
            ksource=cuobjdump-recount
            if [ -z "$kernels" ]; then
                emit refused "$(arm_label "$arm" kernels)" \
                    "arm=$arm" "img=$tag" "checkpoint_quant=none" "tries=1" \
                    -- "the $arm image records only a whole-fat-binary mma.sync total, which says nothing about the arch image a cc $DEVICE_CC card loads, and the recount against its own library did not complete"
                say "$arm: no per-arch record and the recount failed. Refused."
                continue
            fi
        fi
        verdict=$(kernels_verdict "$kernels" "$DEVICE_CC") || return 1
        read -r verdict sel_arch sel_kind sel_count <<<"$verdict"
        KERNEL_VERDICT["$arm"]=$verdict
        KERNEL_SELECTED["$arm"]="$sel_arch/$sel_kind lines=$sel_count"
        counts=("cuda_library=$(spec_get "$kernels" cuda_library)")
        if [ "$(spec_get "$kernels" cuda_library)" = present ]; then
            counts+=(
                "device_cc=$DEVICE_CC"
                "selected_arch=$sel_arch"
                "selected_kind=$sel_kind"
                "selected_tensor_core_lines=$sel_count"
                "mma_sync_ptx_by_arch=$(spec_get "$kernels" mma_sync_ptx_by_arch)"
                "hmma_sass_by_arch=$(spec_get "$kernels" hmma_sass_by_arch)"
                "mma_sync_ptx_all_images=$(spec_get "$kernels" mma_sync_ptx)"
                "hmma_sass_all_images=$(spec_get "$kernels" hmma_sass)"
                "ptx_bytes=$(spec_get "$kernels" ptx_bytes)"
                "sass_bytes=$(spec_get "$kernels" sass_bytes)"
            )
        fi
        emit stamp KERNELS "arm=$arm" "tensor_core_instructions=$verdict" \
            "${counts[@]}" "source=$ksource"
        say "$arm: tensor_core_instructions=$verdict on $sel_arch ($sel_kind), $sel_count line(s)"

        commit=$(quiet_on_host "$BUILD_HOST" docker run --rm --entrypoint cat "$tag" /app/commit.txt) || commit=
        image_id=$(quiet_on_host "$BUILD_HOST" docker image inspect --format '{{.Id}}' "$tag") || image_id=
        image_id=${image_id#sha256:}
        if [ -z "$commit" ] || [ -z "$image_id" ]; then
            _fail "$arm: the image reports commit='$commit' id='$image_id'. A BUILD stamp that cannot name what it built resolves no tag (behaviour 3)"
            return 1
        fi
        # The producer half of the label contract: tools/runs/campaigns/srv1-kernel-arms/4-kernel-arms.sh
        # reads org.mcgyvr.build.commit off this tag and fails loudly without it.
        if ! label_build_facts "$tag" "$commit"; then
            _fail "$arm: could not apply org.mcgyvr.build.commit=$commit to $tag. tools/runs/campaigns/srv1-kernel-arms/4-kernel-arms.sh reads that label and refuses to stamp a ### BUILD without it, so the serving sweep would stop on this arm"
            return 1
        fi
        # The relabel added a metadata layer, so the tag now names a new id.
        image_id=$(quiet_on_host "$BUILD_HOST" docker image inspect --format '{{.Id}}' "$tag") || image_id=
        image_id=${image_id#sha256:}
        [ -n "$image_id" ] || { _fail "$arm: $tag has no image id after relabelling"; return 1; }
        emit stamp BUILD "arm=$arm" "commit=$commit" "image_sha256=$image_id" \
            "cuda_architectures=$(spec_get "$spec" cuda_architectures)" \
            "force_mmq=$(spec_get "$spec" force_mmq)" \
            "ggml_native=$(spec_get "$spec" ggml_native)" \
            "cpu_all_variants=$(spec_get "$spec" cpu_all_variants)" \
            "patched=$(spec_get "$spec" patched)" \
            "backend=$(spec_get "$spec" backend)" \
            $([ "$(spec_get "$spec" backend)" = vulkan ] && printf 'icd_deps=%s' "$(spec_get "$spec" icd_deps)") \
            "img=$tag" "toolkit=$CUDA_DEVEL" "runtime_image=$CUDA_RUNTIME" \
            "source_commit_requested=$LCPP_COMMIT" "reused=$reused" \
            "built_on=$BUILD_HOST"

        push_arm "$tag"
        BUILT_TAG["$arm"]=$tag
    done

    if dry; then
        say "gate would run here, on the arch image the serve host's card"
        say "selects: L0/L1 present, L2/L3 absent, else exit 1"
        if [ "$STAGE" = build ]; then
            say "--stage build: no BENCH row. Pass 2 (no --stage) copies them"
            say "from $BENCH_TSV after step 3 has written it."
        else
            say "then one BENCH row per rung, copied from $BENCH_TSV"
            say "an arm with no row there makes this pass exit non-zero"
        fi
        say "then ### END + the start==end re-read"
        return 0
    fi

    if ! gate_the_mechanism; then
        emit end_stamp
        rig_assert_unchanged || true
        return 1
    fi

    if ! project_bench; then
        emit end_stamp
        rig_assert_unchanged || true
        return 1
    fi

    emit end_stamp
    rig_assert_unchanged
    if [ "$STAGE" = build ]; then
        say "pass 1 done: $OUT carries the stamps and owes every BENCH row."
        say "Run tools/runs/campaigns/srv1-kernel-arms/3-llama-bench.sh (step 3), then this script again."
    else
        say "done: $OUT"
    fi
}

main
