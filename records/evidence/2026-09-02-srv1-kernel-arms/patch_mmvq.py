import sys
p = "/src/ggml/src/ggml-cuda/mmvq.cu"
s = open(p).read()
old = """    if (GGML_CUDA_CC_IS_NVIDIA(cc)) {
        if (cc == GGML_CUDA_CC_VOLTA || cc >= GGML_CUDA_CC_ADA_LOVELACE) {
            return MMVQ_MAX_BATCH_SIZE;
        }
        if (cc >= GGML_CUDA_CC_TURING) {
            return get_mmvq_mmid_max_batch_turing_plus(type);
        }
        return get_mmvq_mmid_max_batch_pascal_older(type);
    }"""
new = """    if (GGML_CUDA_CC_IS_NVIDIA(cc)) {
        // PATCH: select on the highest COMPILED arch, not the raw runtime cc.
        // The device kernel's __launch_bounds__ are baked from __CUDA_ARCH__, so a build
        // without Turing SASS/PTX gets the Pascal table on the device while this host
        // function handed out Turing limits. The mismatch is a hard
        // "CUDA error: invalid argument" in ggml_cuda_mul_mat_vec_q at 5-8 concurrent
        // MoE decode slots. get_device_table_id(cc) at line ~108 of THIS FILE already
        // does the right thing; this function was simply missed.
        const int cc_c = ggml_cuda_highest_compiled_arch(cc);
        if (cc_c == GGML_CUDA_CC_VOLTA || cc_c >= GGML_CUDA_CC_ADA_LOVELACE) {
            return MMVQ_MAX_BATCH_SIZE;
        }
        if (cc_c >= GGML_CUDA_CC_TURING) {
            return get_mmvq_mmid_max_batch_turing_plus(type);
        }
        return get_mmvq_mmid_max_batch_pascal_older(type);
    }"""
assert s.count(old) == 1, f"patch anchor matched {s.count(old)} times - ABORT"
open(p, "w").write(s.replace(old, new, 1))
print("mmvq.cu patched OK")
