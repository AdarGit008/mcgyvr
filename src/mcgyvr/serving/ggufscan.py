#!/usr/bin/env python3
"""Read a GGUF's tensor table and report what is expert weight and what is not.

**Vendored from ``records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/
ggufscan.py``, which stays where it is.** That copy is the evidence a dated
record was computed from and must not move; this one is a live dependency of
:func:`backends.llamacpp.mmap_gate`, which ships it to the serving host and
runs it there. Two copies of one parser is a cost paid deliberately: the
alternative was importing a module out of ``records/``, which would let an
edit made for the gate silently rewrite what a published measurement claims
to have been computed with.

**The point of reading the header rather than the file size is that the two
answer different questions.** ``stat -c %s`` says what the blob weighs on
disk; only the tensor table says how much of that weight is ``ffn_*_exps`` --
the only part ``--n-cpu-moe`` can move to host RAM. A gate built on the
former refuses a model whose experts would have fitted; see ``mmap_gate``.

Sums the table. Never guesses bits-per-weight from size over parameters: two
defensible estimates of one GGUF's expert bytes disagreed by 14% and both
were wrong (``okf/must-read/touching-models.md``). ``MXFP4`` is ggml type 39
and a reader missing it falls back to f32 and calls an 11.28 GiB file 71 GiB.
"""

import struct, sys, os, json, glob


# (block_elems, bytes_per_block)
T = {0:(1,4),1:(1,2),2:(32,18),3:(32,20),6:(32,22),7:(32,24),8:(32,34),9:(32,36),
     10:(256,84),11:(256,110),12:(256,144),13:(256,176),14:(256,210),15:(256,292),
     16:(256,66),17:(256,74),18:(256,98),19:(256,50),20:(32,18),21:(256,110),
     22:(256,82),23:(256,136),24:(1,1),25:(1,2),26:(1,4),27:(1,8),28:(1,8),
     29:(256,56),30:(1,2),34:(256,54),35:(256,66),39:(32,17)}
NAME = {0:"F32",1:"F16",2:"Q4_0",3:"Q4_1",6:"Q5_0",7:"Q5_1",8:"Q8_0",9:"Q8_1",
    10:"Q2_K",11:"Q3_K",12:"Q4_K",13:"Q5_K",14:"Q6_K",15:"Q8_K",16:"IQ2_XXS",
    17:"IQ2_XS",18:"IQ3_XXS",19:"IQ1_S",20:"IQ4_NL",21:"IQ3_S",22:"IQ2_S",
    23:"IQ4_XS",29:"IQ1_M",30:"BF16",34:"TQ1_0",35:"TQ2_0",39:"MXFP4"}

class R:
    def __init__(s,f): s.f=f
    def u32(s): return struct.unpack("<I",s.f.read(4))[0]
    def u64(s): return struct.unpack("<Q",s.f.read(8))[0]
    def i64(s): return struct.unpack("<q",s.f.read(8))[0]
    def st(s):
        n=s.u64(); return s.f.read(n).decode("utf-8","replace")
    def val(s,t):
        if t==0: return struct.unpack("<B",s.f.read(1))[0]
        if t==1: return struct.unpack("<b",s.f.read(1))[0]
        if t==2: return struct.unpack("<H",s.f.read(2))[0]
        if t==3: return struct.unpack("<h",s.f.read(2))[0]
        if t==4: return s.u32()
        if t==5: return struct.unpack("<i",s.f.read(4))[0]
        if t==6: return struct.unpack("<f",s.f.read(4))[0]
        if t==7: return struct.unpack("<?",s.f.read(1))[0]
        if t==8: return s.st()
        if t==9:
            et=s.u32(); n=s.u64()
            return [s.val(et) for _ in range(n)]
        if t==10: return s.u64()
        if t==11: return s.i64()
        if t==12: return struct.unpack("<d",s.f.read(8))[0]
        raise ValueError(f"kv type {t}")

def scan(path):
    with open(path,"rb") as f:
        r=R(f)
        if f.read(4)!=b"GGUF": return {"file":path,"error":"not gguf"}
        ver=r.u32(); ntensor=r.u64(); nkv=r.u64()
        kv={}
        for _ in range(nkv):
            k=r.st(); t=r.u32()
            try: kv[k]=r.val(t)
            except Exception as e: return {"file":path,"error":f"kv {k}: {e}"}
        tensors=[]
        for _ in range(ntensor):
            name=r.st(); nd=r.u32()
            dims=[r.u64() for _ in range(nd)]
            tt=r.u32(); off=r.u64()
            n=1
            for d in dims: n*=d
            if tt not in T: return {"file":path,"error":f"unknown ggml type {tt} in {name}"}
            be,bb=T[tt]
            tensors.append((name,n,tt,n//be*bb))
    tot=sum(t[3] for t in tensors)
    # expert tensors: ffn_*_exps  |  shared/dense ffn and attention = the rest
    exp=[t for t in tensors if "_exps" in t[0]]
    expb=sum(t[3] for t in exp)

    # PER-BLOCK expert bytes, keyed by block index.
    #
    # `bytes_experts / n_layer` is the WRONG number to place a block with, and
    # it is wrong for 9 of the 10 checkpoints in this store. The distribution is
    # bimodal wherever a quant is non-uniform: Qwen3.6 IQ3_XXS is 262.0 MiB on
    # 37 blocks and 300.0 on 3 (the UD mix lifts ffn_down_exps to IQ4_XS), so
    # the mean of 264.85 matches NO block in the file. `--n-cpu-moe` moves whole
    # blocks, so what a placement decision needs is the MARGINAL block, never
    # the average. Worst case measured: nemotron_h_moe declares block_count 52
    # while only 23 blocks carry experts, making the mean wrong by 2.26x.
    per_block={}
    for t in exp:
        parts=t[0].split(".")
        idx=None
        if len(parts)>2 and parts[1]=="blk": idx=parts[2]
        elif parts[0]=="blk": idx=parts[1]
        if idx is not None: per_block[int(idx)]=per_block.get(int(idx),0)+t[3]

    # The blocks `--n-cpu-moe` can actually move, in the order it moves them.
    # It keeps blocks 0..N-1 on the CPU (verified 24/23/22/1/0, no off-by-one),
    # so the marginal block for a floor of N is block N-1. A grafted MTP head
    # (KAT/Ornith blk 40, 816 MiB) carries expert tensors but is NEVER placed by
    # this knob: counting it put a predicted floor 3 steps above the true one.
    blocks=sorted(per_block)
    layers=len(blocks)

    # Blocks that carry experts but that `--n-cpu-moe` NEVER places.
    #
    # A grafted multi-token-prediction head is a block by tensor naming and not
    # a block by placement: KAT/Ornith `blk.40` carries the full expert set plus
    # `nextn.{eh_proj,enorm,hnorm,shared_head_norm}` and weighs 816 MiB against
    # its neighbours' 364. Counting it as placeable put a predicted floor THREE
    # steps above the true one. Proof it is excluded: at ncmoe 8 the card held
    # 9976.83 - 1080.83 = 8896.00 MiB = 32 x 278.0 exactly, i.e. blocks 8..39
    # with block 40 absent.
    #
    # Detected by tensor name, which is self-evidencing and needs no per-arch
    # key; `<arch>.nextn_predict_layers` is read too and disagreement is
    # reported rather than resolved silently.
    nextn=sorted({int(x.split(".")[1]) for x in
                  (t[0] for t in tensors)
                  if x.startswith("blk.") and ".nextn." in x})
    placeable=[b for b in blocks if b not in set(nextn)]

    # Blocks carrying recurrent (SSM) tensors -- counted, not inferred from
    # `n_layer - caching_layers`. That subtraction assumes every non-attention
    # layer is recurrent, which holds on qwen35moe and fails on
    # nemotron_h_moe: 52 blocks = 6 attention + 23 mamba + 23 MLP-only, so the
    # subtraction says 46 and doubles the state buffer.
    recurrent=sorted({int(x.split(".")[1]) for x in (t[0] for t in tensors)
                      if x.startswith("blk.") and ".ssm_" in x})

    types={}
    for t in tensors: types[NAME.get(t[2],t[2])]=types.get(NAME.get(t[2],t[2]),0)+t[3]
    g=lambda *ks: next((kv[k] for k in ks if k in kv), None)
    arch=kv.get("general.architecture")
    pre=f"{arch}." if arch else ""
    # A PER-LAYER cache descriptor, because no single pair of numbers describes
    # these files. Three checkpoints in this store defeat any scalar summary:
    #
    #  * gemma4 caches 5 layers at head_count_kv 2 x key_length 512 and slides
    #    25 at head_count_kv 8 x key_length_SWA 256 -- two widths and two head
    #    counts in one file. Taking max(head_count_kv) and one key_length is
    #    4x wrong on the full layers and 2x wrong on the sliding ones.
    #  * cohere2moe slides 36 of 49 and caches 13, on a 1-in-4 pattern.
    #  * bailingmoe3 absorbs V into the compressed KV and allocates NO V cache
    #    at all -- the engine prints `V (f16): 0.00 MiB`.
    #
    # So each caching layer states its own width here, and the callers sum.
    hkv=g(pre+"attention.head_count_kv")
    n_layer_kv=g(pre+"block_count") or 0
    n_head=g(pre+"attention.head_count")
    kl=g(pre+"attention.key_length"); vl=g(pre+"attention.value_length")
    kl_swa=g(pre+"attention.key_length_swa"); vl_swa=g(pre+"attention.value_length_swa")
    nemb=g(pre+"embedding_length")
    if kl is None and nemb and n_head: kl=vl=nemb//n_head

    # `sliding_window_pattern` is DECLARED by both checkpoints whose split is
    # not 1:1, and it is the engine's own per-layer is_swa assignment. Reading
    # it removes the last fitted constant here: an assumed alternating split,
    # which is right for gpt-oss and wrong for cohere2moe (13/36) and gemma4
    # (5/25). True in the pattern means the layer SLIDES.
    pattern=g(pre+"attention.sliding_window_pattern")
    swa_window=g(pre+"attention.sliding_window")

    # MLA that absorbs V: `key_length == kv_lora_rank + rope_dim` is the
    # signature of a checkpoint caching one compressed vector per token instead
    # of a K and a V. bailingmoe3 matches (576 = 512 + 64) and allocates no V;
    # deepseek2 declares kv_lora_rank too but caches K and V separately
    # (key_length 192, not 576), so the test must be this equality and not the
    # mere presence of the key.
    # PRIMARY signal is the header's own `key_length_mla`, which is the key
    # llama.cpp itself reads and what a current converter writes for an MLA
    # checkpoint. The arithmetic identity `key_length == kv_lora_rank +
    # rope_dim` is a DERIVATION of the absorbed width, not a test for
    # absorption: it separates the two checkpoints here only because
    # deepseek2's is an older conversion that caches K and V outright, and it
    # would go false on any converter writing rope.dimension_count as the full
    # head dim (gemma4 already does). Disagreement between the two is reported
    # rather than resolved silently.
    lora=g(pre+"attention.kv_lora_rank"); rope=g(pre+"rope.dimension_count")
    kl_mla=g(pre+"attention.key_length_mla")
    mla_absorbed=kl_mla is not None
    mla_by_identity=bool(lora and rope and kl == lora + rope)

    # UNKNOWN, not a guess, when a sliding window is declared WITHOUT the
    # per-layer pattern saying which layers use it. `l % 2 == 0` stood here and
    # was measured on gpt-oss alone -- the one checkpoint where it cannot be
    # caught, because its sliding and full layers are the same width, so only
    # the 12/12 COUNT matters and any half-split reproduces the bytes exactly.
    #
    # It is wrong as a rule. gemma4 slides 25 of 30 and cohere2moe 36 of 49 on
    # a 1-in-4 pattern, and gemma4's sliding layers are TWICE the width of its
    # full ones -- so there the ASSIGNMENT, not just the count, sets the total.
    # Both declare their pattern and never reach this branch, which is the only
    # reason the assumption has never been caught being wrong. A checkpoint
    # that is undeclared, not 1:1 and not uniform in width would be sized wrong
    # with nothing in the output saying anything had been assumed.
    #
    # `None` propagates to `is_swa` and `vramfit.kv_bytes` refuses on it, the
    # way `rs_bytes` refuses a recurrent model that states no state size. The
    # split is OBSERVABLE where it matters: llama.cpp prints
    # `llama_kv_cache_iswa: creating non-SWA KV cache` and `... SWA KV cache`
    # with a layer count on each, so a caller who has measured it hands the
    # rows to `kv_bytes(layers=...)` instead of having them invented here.
    def _is_swa(l):
        if isinstance(pattern,list) and l < len(pattern): return bool(pattern[l])
        if swa_window: return None
        return False

    kv_layers=[]
    if isinstance(hkv,list):
        caching_from="head_count_kv array (non-zero entries)"
        heads=[(l,h) for l,h in enumerate(hkv) if h]
    elif interval_v:=g(pre+"full_attention_interval"):
        caching_from="full_attention_interval"
        heads=[(l,hkv) for l in range(n_layer_kv) if l % int(interval_v) == int(interval_v)-1]
    elif recurrent:
        caching_from="n_layer - recurrent blocks"
        rec=set(recurrent); heads=[(l,hkv) for l in range(n_layer_kv) if l not in rec]
    else:
        caching_from="every layer caches"
        heads=[(l,hkv) for l in range(n_layer_kv)]
    for l,h in heads:
        swa=_is_swa(l)
        k=(kl_swa if (swa and kl_swa) else kl) or 0
        v=(vl_swa if (swa and vl_swa) else vl) or 0
        kv_layers.append({"layer":l,"is_swa":swa,
                          "k_elems":int(h)*int(k),
                          "v_elems":0 if mla_absorbed else int(h)*int(v)})
    caching=len(kv_layers)

    # Recurrent state parameters. bailingmoe3 states none of the `ssm.*` size
    # keys and describes the same state under `kda.*`; a reader that requires
    # `ssm.inner_size` silently reports 0 for a model whose engine allocates
    # 154.12 MiB, and a missing key becomes indistinguishable from a model with
    # no state at all.
    ssm_inner=g(pre+"ssm.inner_size"); ssm_state=g(pre+"ssm.state_size")
    ssm_groups=g(pre+"ssm.group_count"); ssm_conv=g(pre+"ssm.conv_kernel")
    kda=g(pre+"kda.head_dim")
    if ssm_inner is None and kda and n_head:
        ssm_inner=int(n_head)*int(kda); ssm_state=int(kda); ssm_groups=int(n_head)
        ssm_from="kda.head_dim x head_count"
    else:
        ssm_from="ssm.* keys" if ssm_inner is not None else None

    return {
      "file": path,
      "size_bytes": os.path.getsize(path),
      "arch": arch,
      "name": kv.get("general.name"),
      "params_total": sum(t[1] for t in tensors),
      "n_layer": g(pre+"block_count"),
      "n_expert": g(pre+"expert_count"),
      "n_expert_used": g(pre+"expert_used_count"),
      "n_embd": nemb,
      "n_head_kv": (max(hkv) if isinstance(hkv,list) else hkv),
      "n_ctx_train": g(pre+"context_length"),
      "rope_dim": g(pre+"rope.dimension_count"),
      "full_attn_interval": g(pre+"full_attention_interval"),
      "sliding_window": g(pre+"attention.sliding_window"),
      "bytes_total_tensors": tot,
      "bytes_experts": expb,
      "expert_layers": layers,
      "bytes_nonexpert": tot-expb,
      "type_bytes": types,
      # --- added for placement arithmetic; see the comments above each ---
      "expert_blocks": blocks,
      "nextn_blocks": nextn,
      "nextn_predict_layers": g(pre+"nextn_predict_layers"),
      "placeable_blocks": placeable,
      "recurrent_blocks": recurrent,
      "n_recurrent": len(recurrent),
      "n_placeable": len(placeable),
      "expert_bytes_by_block": {str(b): per_block[b] for b in blocks},
      "caching_layers": caching,
      "caching_layers_from": caching_from,
      "kv_layers": kv_layers,
      "mla_absorbed_v": mla_absorbed,
      "mla_by_identity": mla_by_identity,
      "key_length_mla": kl_mla,
      "sliding_window_pattern_declared": isinstance(pattern,list),
      "swa_pattern_from": ("attention.sliding_window_pattern"
                           if isinstance(pattern,list) else
                           (None if swa_window else "no sliding window declared")),
      "key_length": kl,
      "value_length": vl,
      "key_length_swa": kl_swa,
      "value_length_swa": vl_swa,
      "ssm_inner_size": ssm_inner,
      "ssm_state_size": ssm_state,
      "ssm_conv_kernel": ssm_conv,
      "ssm_group_count": ssm_groups,
      "ssm_params_from": ssm_from,
    }

# Guarded, unlike the evidence copy: `mmap_gate` ships this file to the serving
# host and runs it as `python3 -`, where __name__ IS "__main__", but the test
# suite imports it in-process to check the parser against a known blob. An
# unguarded loop would print "[]" on every such import.
if __name__ == "__main__":
    out = []
    for pat in sys.argv[1:]:
        for p in sorted(glob.glob(pat)):
            try:
                out.append(scan(p))
            except Exception as e:
                out.append({"file": p, "error": repr(e)})
    print(json.dumps(out))
