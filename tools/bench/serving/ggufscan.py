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
    # per-layer expert bytes
    layers=set()
    for t in exp:
        p=t[0].split(".")
        if len(p)>2 and p[1]=="blk": layers.add(p[2])
        elif p[0]=="blk": layers.add(p[1])
    types={}
    for t in tensors: types[NAME.get(t[2],t[2])]=types.get(NAME.get(t[2],t[2]),0)+t[3]
    g=lambda *ks: next((kv[k] for k in ks if k in kv), None)
    arch=kv.get("general.architecture")
    pre=f"{arch}." if arch else ""
    return {
      "file": path,
      "size_bytes": os.path.getsize(path),
      "arch": arch,
      "name": kv.get("general.name"),
      "params_total": sum(t[1] for t in tensors),
      "n_layer": g(pre+"block_count"),
      "n_expert": g(pre+"expert_count"),
      "n_expert_used": g(pre+"expert_used_count"),
      "n_embd": g(pre+"embedding_length"),
      "n_head_kv": g(pre+"attention.head_count_kv"),
      "n_ctx_train": g(pre+"context_length"),
      "rope_dim": g(pre+"rope.dimension_count"),
      "full_attn_interval": g(pre+"full_attention_interval"),
      "sliding_window": g(pre+"attention.sliding_window"),
      "bytes_total_tensors": tot,
      "bytes_experts": expb,
      "expert_layers": len(layers),
      "bytes_nonexpert": tot-expb,
      "type_bytes": types,
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
