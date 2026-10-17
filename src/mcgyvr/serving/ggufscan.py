#
""

import struct, sys, os, json, glob


#
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
            tensors.append((name,n,tt,n//be*bb,nd))
    tot=sum(t[3] for t in tensors)
    #
    exp=[t for t in tensors if "_exps" in t[0]]
    expb=sum(t[3] for t in exp)

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    per_block={}
    for t in exp:
        parts=t[0].split(".")
        idx=None
        if len(parts)>2 and parts[1]=="blk": idx=parts[2]
        elif parts[0]=="blk": idx=parts[1]
        if idx is not None: per_block[int(idx)]=per_block.get(int(idx),0)+t[3]

    #
    #
    #
    #
    #
    blocks=sorted(per_block)
    layers=len(blocks)

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    nextn=sorted({int(x.split(".")[1]) for x in
                  (t[0] for t in tensors)
                  if x.startswith("blk.") and ".nextn." in x})
    placeable=[b for b in blocks if b not in set(nextn)]

    #
    #
    #
    #
    #
    recurrent=sorted({int(x.split(".")[1]) for x in (t[0] for t in tensors)
                      if x.startswith("blk.") and ".ssm_" in x})

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    by_block={}; matrix_by_block={}
    b_input=0; b_output=0; b_output_matrix=0
    for t in tensors:
        parts=t[0].split(".")
        if parts[0]=="blk" and len(parts)>1 and parts[1].isdigit():
            b=int(parts[1])
            by_block[b]=by_block.get(b,0)+t[3]
            matrix_by_block[b]=matrix_by_block.get(b,0)+(t[3] if t[4]==2 else 0)
        elif parts[0]=="token_embd":
            b_input+=t[3]
        else:
            b_output+=t[3]
            if t[4]==2: b_output_matrix+=t[3]

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    tp={f"{w}.{k}" for w in ("attn_q","attn_k","attn_v","attn_qkv") for k in ("weight","bias")}
    tp|={"attn_output.weight","attn_gate.weight","ffn_down.weight","ffn_down_exps.weight",
         "ffn_down_exps.bias","ffn_gate_up.weight","ffn_gate_up_exps.weight"}
    tp|={f"{w}.{k}" for w in ("ffn_up","ffn_up_exps","ffn_gate","ffn_gate_exps")
         for k in ("weight","bias")}
    tp_by_block={}; tp_output=0; tp_refused=[]
    for t in tensors:
        parts=t[0].split(".",2)
        if len(parts)==3 and parts[0]=="blk" and parts[1].isdigit() and parts[2] in tp:
            b=int(parts[1]); tp_by_block[b]=tp_by_block.get(b,0)+t[3]
            if t[0].endswith("ffn_down_exps.bias") and t[2]!=0:
                tp_refused.append(t[0])
        elif t[0] in ("output.weight","output.bias"):
            tp_output+=t[3]

    types={}
    for t in tensors: types[NAME.get(t[2],t[2])]=types.get(NAME.get(t[2],t[2]),0)+t[3]
    g=lambda *ks: next((kv[k] for k in ks if k in kv), None)
    arch=kv.get("general.architecture")
    pre=f"{arch}." if arch else ""
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    hkv=g(pre+"attention.head_count_kv")
    n_layer_kv=g(pre+"block_count") or 0
    n_head=g(pre+"attention.head_count")
    kl=g(pre+"attention.key_length"); vl=g(pre+"attention.value_length")
    kl_swa=g(pre+"attention.key_length_swa"); vl_swa=g(pre+"attention.value_length_swa")
    nemb=g(pre+"embedding_length")
    if kl is None and nemb and n_head: kl=vl=nemb//n_head

    #
    #
    #
    #
    #
    pattern=g(pre+"attention.sliding_window_pattern")
    swa_window=g(pre+"attention.sliding_window")

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    lora=g(pre+"attention.kv_lora_rank"); rope=g(pre+"rope.dimension_count")
    kl_mla=g(pre+"attention.key_length_mla")
    mla_absorbed=kl_mla is not None
    mla_by_identity=bool(lora and rope and kl == lora + rope)

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
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
                          "v_elems":0 if mla_absorbed else int(h)*int(v),
                          #
                          #
                          "heads":int(h)})
    caching=len(kv_layers)

    #
    #
    #
    #
    #
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
      #
      #
      "token_embd_bytes": next((t[3] for t in tensors if t[0]=="token_embd.weight"), None),
      "output_bytes": next((t[3] for t in tensors if t[0]=="output.weight"), None),
      "bytes_experts": expb,
      "expert_layers": layers,
      "bytes_nonexpert": tot-expb,
      "type_bytes": types,
      #
      "expert_blocks": blocks,
      "nextn_blocks": nextn,
      "nextn_predict_layers": g(pre+"nextn_predict_layers"),
      "placeable_blocks": placeable,
      "recurrent_blocks": recurrent,
      "n_recurrent": len(recurrent),
      "n_placeable": len(placeable),
      "expert_bytes_by_block": {str(b): per_block[b] for b in blocks},
      "bytes_by_block": {str(b): by_block[b] for b in sorted(by_block)},
      "bytes_matrix_by_block": {str(b): matrix_by_block[b] for b in sorted(by_block)},
      "bytes_input": b_input,
      "bytes_output": b_output,
      "bytes_output_matrix": b_output_matrix,
      #
      #
      "tied_embeddings": not any(t[0]=="output.weight" for t in tensors),
      "bytes_tensor_split_by_block": {str(b): tp_by_block.get(b,0) for b in sorted(by_block)},
      "bytes_output_tensor_split": tp_output,
      "tensor_split_refused": tp_refused,
      "n_head": n_head,
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

#
#
#
#
if __name__ == "__main__":
    out = []
    for pat in sys.argv[1:]:
        for p in sorted(glob.glob(pat)):
            try:
                out.append(scan(p))
            except Exception as e:
                out.append({"file": p, "error": repr(e)})
    print(json.dumps(out))
