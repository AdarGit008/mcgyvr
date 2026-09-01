#!/usr/bin/env bash
#
# tools/runs/srv1-build-ladder.sh
#   -> records/evidence/2026-09-02-srv1-kernel-arms/srv1-build-ladder.tsv
#
# Campaign steps 0 and 1 (`lcp-vllm-3-arm-run.md:113-118`):
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
# What lands in the artifact (ARTIFACT-CONTRACT.md §5.5):
#   ### WORKLOAD digest=none comparable_with=microbenchmark-only   (§2.1, §6.4)
#   ### START / ### RIG / ### END                                  (guideline 7)
#   ### BUILD arm=.. commit=.. image_sha256=.. cuda_architectures=.. force_mmq=..
#             ggml_native=.. cpu_all_variants=.. patched=..         (§2.4)
#   ### KERNELS arm=.. tensor_core_instructions=present|absent      (§2.5)
#   one BENCH row per rung                                          (§6.4)
#
# The BENCH rows are NOT measured here. Resolved conflict §6.4: they are the
# step-3 `llama-bench` numbers, copied out of `srv1-llama-bench.tsv` and
# re-filed beside the stamps. If that file does not exist yet, this script emits
# the stamps, says which rows are still owed, and leaves them out. Re-run it
# after step 3 — the builds are reused, so the second pass is cheap. It never
# invents a number.
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
#   --dry-run     print the exact command line for every cell, execute nothing,
#                 read nothing off the rig, write no file.
#   --out PATH    write somewhere other than the contract path (for rehearsal).

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh
# shellcheck disable=SC1091  # sourced at runtime from the script's own directory
. "$HERE/_common.sh"

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
OUT=

usage() {
    sed -n '2,50p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,2\} \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --out)
            [ "$#" -ge 2 ] || { _fail "--out needs a path"; exit 2; }
            OUT=$2
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

ROOT=$(_repo_root)
[ -n "$OUT" ] || OUT="$ROOT/$RUN_REL/$ARTIFACT"
BENCH_TSV=${RUN_BENCH_TSV:-$ROOT/$RUN_REL/srv1-llama-bench.tsv}
MMVQ_PATCH=${RUN_MMVQ_PATCH:-$ROOT/$RUN_REL/mmvq.patch}
THIS_HOST=$(hostname)

read -r -a ARM_LIST <<<"${RUN_ARMS:-L0 L1 L2 L3 L4 A3}"

declare -A KERNEL_VERDICT=()
declare -A BUILT_TAG=()

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
        ssh "$host" "$(printf '%q ' "$@")"
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
# the arms table (lcp-vllm-3-arm-run.md:39-47)
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
        A3) printf 'backend=vulkan\ncuda_architectures=none\nforce_mmq=OFF\nggml_native=OFF\ncpu_all_variants=ON\npatched=no\n' ;;
        *)
            _fail "arm_spec: '$1' is not on this campaign's arms table (lcp-vllm-3-arm-run.md:39-47)"
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
# Step 0, inside the build that produced the library. PTX carries `mma.sync`;
# SASS carries HMMA/IMMA. A virtual-only arch list emits no SASS at all, so the
# PTX dump is the one required to be non-empty. Every count comes from the
# binary; an unreadable dump fails the build rather than reporting a zero.
RUN set -eu; \
    lib=/src/build/bin/libggml-cuda.so; \
    test -f "$lib"; \
    cuobjdump --dump-ptx "$lib" > /tmp/ptx.txt; \
    cuobjdump --dump-sass "$lib" > /tmp/sass.txt; \
    test -s /tmp/ptx.txt; \
    { echo "cuda_library=present"; \
      echo "mma_sync_ptx=$(grep -c 'mma\.sync' /tmp/ptx.txt || true)"; \
      echo "hmma_sass=$(grep -cE 'HMMA|IMMA' /tmp/sass.txt || true)"; \
      echo "ptx_bytes=$(wc -c < /tmp/ptx.txt)"; \
      echo "sass_bytes=$(wc -c < /tmp/sass.txt)"; } > /kernels.txt

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
LABEL org.mcgyvr.arm="${ARM}" \
      org.mcgyvr.backend="cuda" \
      org.mcgyvr.cuda_architectures="${ARCHS}" \
      org.mcgyvr.force_mmq="${FORCE_MMQ}" \
      org.mcgyvr.ggml_native="${NATIVE}" \
      org.mcgyvr.cpu_all_variants="${ALLVAR}" \
      org.mcgyvr.patched="${PATCHED}" \
      org.mcgyvr.toolkit="${BASE_DEVEL}"
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
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake build-essential libcurl4-openssl-dev ca-certificates ninja-build \
      libvulkan-dev glslc glslang-tools \
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
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 libcurl4 curl ca-certificates libvulkan1 vulkan-tools \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/bin/ /app/
COPY --from=build /kernels.txt /app/kernels.txt
COPY --from=build /commit.txt /app/commit.txt
ENV LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH
ENV NVIDIA_DRIVER_CAPABILITIES=all
LABEL org.mcgyvr.arm="${ARM}" \
      org.mcgyvr.backend="vulkan" \
      org.mcgyvr.cuda_architectures="none" \
      org.mcgyvr.force_mmq="OFF" \
      org.mcgyvr.ggml_native="${NATIVE}" \
      org.mcgyvr.cpu_all_variants="${ALLVAR}" \
      org.mcgyvr.patched="no" \
      org.mcgyvr.toolkit="${BASE_DEVEL}"
EXPOSE 8080
ENTRYPOINT ["/app/llama-server"]
DOCKERFILE
}

# --------------------------------------------------------------------------
# build / reuse / push
# --------------------------------------------------------------------------

label_of() {
    quiet_on_host "$BUILD_HOST" docker image inspect \
        --format "{{index .Config.Labels \"org.mcgyvr.$2\"}}" "$1" 2>/dev/null
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

# kernels_verdict KERNELSTXT — present / absent, from the counts and nothing
# else. An unparseable count is a refusal, never an "absent".
kernels_verdict() {
    local txt=$1 lib mma hmma
    lib=$(spec_get "$txt" cuda_library)
    if [ "$lib" = absent ]; then
        printf 'not-applicable'
        return 0
    fi
    mma=$(spec_get "$txt" mma_sync_ptx)
    hmma=$(spec_get "$txt" hmma_sass)
    case ${mma:-x}${hmma:-x} in
        *[!0-9]*)
            _fail "kernels_verdict: cuobjdump counts read mma_sync_ptx='$mma' hmma_sass='$hmma'; that is not a pair of integers and no verdict can be read from it"
            return 1
            ;;
    esac
    if [ "$mma" -gt 0 ] || [ "$hmma" -gt 0 ]; then
        printf 'present'
    else
        printf 'absent'
    fi
}

# The gate, guideline 6. Free, and it ends the campaign before rig time is spent.
gate_the_mechanism() {
    local rung bad=
    for rung in L0 L1; do
        case ${KERNEL_VERDICT[$rung]:-unread} in
            present) ;;
            *) bad="${bad:+$bad; }$rung=${KERNEL_VERDICT[$rung]:-unread} (wanted present)" ;;
        esac
    done
    for rung in L2 L3; do
        case ${KERNEL_VERDICT[$rung]:-unread} in
            absent) ;;
            *) bad="${bad:+$bad; }$rung=${KERNEL_VERDICT[$rung]:-unread} (wanted absent)" ;;
        esac
    done
    if [ -n "$bad" ]; then
        printf '\n' >&2
        say "=============================================================="
        say "STOP. The mechanism is not what the ladder claims: $bad"
        say "L0/L1 must carry tensor-core instructions and L2/L3 must not."
        say "If L2/L3 still contain mma.sync the arch spoof did not take, and"
        say "no throughput number can be attributed to removing it"
        say "(lcp-vllm-3-arm-run.md guideline 6). Not one second of rig time"
        say "is worth spending on the arms below until this reads clean."
        say "=============================================================="
        return 1
    fi
    say "gate passed: L0/L1 present, L2/L3 absent. The ladder may be benched."
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
    if [ ! -f "$BENCH_TSV" ]; then
        say "no instrument record at $BENCH_TSV."
        say "The ladder's BENCH rows ARE the step-3 llama-bench numbers"
        say "(ARTIFACT-CONTRACT.md §6.4) and are copied, never re-measured."
        say "Run tools/runs/srv1-llama-bench.sh, then re-run this script: the"
        say "images are reused, so the second pass costs a cuobjdump read."
        return 0
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
    fi
}

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

main() {
    local arm spec tag kernels verdict commit image_id reused
    local -a counts

    say "artifact: $OUT"
    say "build host: $BUILD_HOST   serve host: $SERVE_HOST   arms: ${ARM_LIST[*]}"
    if dry; then say "--dry-run: printing the plan, reading no rig, writing no file"; fi

    preflight_patch || return 1

    if ! dry; then
        mkdir -p "$(dirname "$OUT")"
        : >"$OUT"
    fi

    # §2.1 / §6.4. llama-bench shares no prompt, template or sampler with the
    # serving drivers, and a rung quoted as a serving gain is the misreading
    # guideline 4 blocks. Both microbenchmark files carry this.
    emit microbench_stamp
    emit start_stamp
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
            plan_on_host "$BUILD_HOST" docker image inspect --format '{{.Id}}' "$tag"
            push_arm "$tag"
            BUILT_TAG["$arm"]=$tag
            continue
        fi

        kernels=$(read_kernels "$tag") || kernels=
        if [ -z "$kernels" ]; then
            emit refused "$(arm_label "$arm" kernels)" \
                "arm=$arm" "img=$tag" "checkpoint_quant=none" "tries=3" \
                -- "the $arm image carries no /app/kernels.txt, so cuobjdump never reported on its libraries and the mechanism is unchecked for this arm"
            say "$arm: no cuobjdump record in the image. Refused, not guessed."
            continue
        fi
        verdict=$(kernels_verdict "$kernels")
        KERNEL_VERDICT["$arm"]=$verdict
        counts=("cuda_library=$(spec_get "$kernels" cuda_library)")
        if [ "$(spec_get "$kernels" cuda_library)" = present ]; then
            counts+=(
                "mma_sync_ptx=$(spec_get "$kernels" mma_sync_ptx)"
                "hmma_sass=$(spec_get "$kernels" hmma_sass)"
                "ptx_bytes=$(spec_get "$kernels" ptx_bytes)"
                "sass_bytes=$(spec_get "$kernels" sass_bytes)"
            )
        fi
        emit stamp KERNELS "arm=$arm" "tensor_core_instructions=$verdict" \
            "${counts[@]}" "source=cuobjdump"
        say "$arm: tensor_core_instructions=$verdict"

        commit=$(quiet_on_host "$BUILD_HOST" docker run --rm --entrypoint cat "$tag" /app/commit.txt) || commit=
        image_id=$(quiet_on_host "$BUILD_HOST" docker image inspect --format '{{.Id}}' "$tag") || image_id=
        image_id=${image_id#sha256:}
        if [ -z "$commit" ] || [ -z "$image_id" ]; then
            _fail "$arm: the image reports commit='$commit' id='$image_id'. A BUILD stamp that cannot name what it built resolves no tag (behaviour 3)"
            return 1
        fi
        emit stamp BUILD "arm=$arm" "commit=$commit" "image_sha256=$image_id" \
            "cuda_architectures=$(spec_get "$spec" cuda_architectures)" \
            "force_mmq=$(spec_get "$spec" force_mmq)" \
            "ggml_native=$(spec_get "$spec" ggml_native)" \
            "cpu_all_variants=$(spec_get "$spec" cpu_all_variants)" \
            "patched=$(spec_get "$spec" patched)" \
            "backend=$(spec_get "$spec" backend)" \
            "img=$tag" "toolkit=$CUDA_DEVEL" "runtime_image=$CUDA_RUNTIME" \
            "source_commit_requested=$LCPP_COMMIT" "reused=$reused" \
            "built_on=$BUILD_HOST"

        push_arm "$tag"
        BUILT_TAG["$arm"]=$tag
    done

    if dry; then
        say "gate would run here: L0/L1 present, L2/L3 absent, else exit 1"
        say "then one BENCH row per rung, copied from $BENCH_TSV"
        say "then ### END + the start==end re-read"
        return 0
    fi

    if ! gate_the_mechanism; then
        emit end_stamp
        rig_assert_unchanged || true
        return 1
    fi

    project_bench

    emit end_stamp
    rig_assert_unchanged
    say "done: $OUT"
}

main
