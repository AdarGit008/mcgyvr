import json,glob,os,sys,re,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sizemap import norm, guess_quant
SP=os.path.dirname(os.path.abspath(__file__))

# Reasons a measured row cannot enter the ranking. Order matters for reporting.
EXCL = [
 ("baseline-mine",   r"baseline mine"),
 ("control-run",     r"control run"),
 ("aborted",         r"aborted run"),
 ("spec-decoding",   r"spec-decode|\bSD\b"),
 ("co-resident",     r"co-?resident"),
 ("retracted",       r"invalid|retracted"),
 ("restatement",     r"duplicate/restatement|do not double-count|do NOT double-count|historical|restated from"),
 ("contaminated",    r"contaminat|superseded by"),
]
rows=[]; refusals=[]; drop=collections.Counter(); unmapped=collections.Counter()
for path in sorted(glob.glob(SP+"/../rows-merged.jsonl")) or [SP+"/../rows-merged.jsonl"]:
    for ln,line in enumerate(open(path),1):
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except Exception: drop["unparseable"]+=1; continue
        d["_from"]=d.get("_extract") or (os.path.basename(path)+f":{ln}")
        if d.get("kind")=="refusal": refusals.append(d); continue
        if d.get("n") is None or not d.get("agg_tok_s"): drop["no-number"]+=1; continue
        blob=f"{d.get('note','')} {d.get('config','')}"
        d["_excl"]=None
        for tag,pat in EXCL:
            if re.search(pat,blob,re.I): d["_excl"]=tag; break
        if d.get("engine")=="batched-bench": d["_excl"]="offline-harness"
        if d.get("tokens_per_request")!=475 and not d["_excl"]: d["_excl"]="not-475-protocol"
        key,info=norm(d.get("model"),d.get("quant"),d.get("config"))
        if not key: unmapped[str(d.get("model"))[:50]]+=1; continue
        d["_key"],d["_name"],d["_type"],d["_tot"],d["_act"]=key,*info
        d["_quant"]=d.get("quant") or guess_quant(d.get("model"),d.get("config")) or "?"
        if d["_excl"]: drop[d["_excl"]]+=1
        rows.append(d)

def rank(rig,mode):
    cand=collections.defaultdict(dict)
    for d in rows:
        if d.get("rig")!=rig or d["_excl"]: continue
        k=(d.get("engine"),d["_key"]); n=int(d["n"]); cur=cand[k].get(n)
        if cur is None or d["agg_tok_s"]>cur["agg_tok_s"]: cand[k][n]=d
    out=[]
    for k,pts in cand.items():
        if mode=="n1":
            if 1 not in pts: continue
            d=pts[1]; out.append((d["agg_tok_s"]*d["_tot"],1,d))
        else:
            bn=max(pts,key=lambda n: pts[n]["agg_tok_s"]*n); d=pts[bn]
            out.append((d["agg_tok_s"]*d["_tot"]*bn,bn,d))
    return sorted(out,key=lambda t:-t[0])

if __name__=="__main__":
    ranked=sum(1 for d in rows if not d["_excl"])
    print(f"total={len(rows)+sum(drop.values())-sum(drop[k] for k in ('unparseable','no-number'))} parsed={len(rows)} rankable={ranked} refusals={len(refusals)}")
    print("dropped:",dict(drop)); print("unmapped:",dict(unmapped))
    res={}
    for rig in ("srv1","srv2"):
        for mode in ("n1","multi"):
            res[(rig,mode)]=rank(rig,mode)
            print(f"\n### {rig} {mode}")
            for i,(s,n,d) in enumerate(res[(rig,mode)][:10],1):
                print(f"{i:2}|{d['_name']}|{d['_type']}|{d['_quant']}|{d['engine']}|{d['_tot']}|{d['_act']}|n={n}|{d['agg_tok_s']}|{s:.0f}|{d.get('date')}|{d.get('src_file')}|{d.get('src_locator')}|{(d.get('config') or '')[:70]}")
    # emit exactly what drivers/build.py consumes
    OUT=os.path.join(SP,"..")
    T={}
    for (rig,mode),v in res.items():
        T[f"{rig}_{mode}"]=[dict(name=d["_name"],typ=d["_type"],quant=d["_quant"],eng=d.get("engine"),
            tot=d["_tot"],act=d["_act"],n=n,tok=d["agg_tok_s"],per=round(d["agg_tok_s"]/n,1),
            score=round(s),date=d.get("date"),cfg=(d.get("config") or "")[:90],
            file=d.get("src_file"),loc=str(d.get("src_locator")),p50=d.get("p50_latency_s"))
            for s,n,d in v[:10]]
    Bo={}
    for rig in ("srv1","srv2"):
        posA={(d.get("engine"),d["_key"]):i for i,(s,n,d) in enumerate(res[(rig,"multi")],1)}
        cand=collections.defaultdict(dict)
        for d in rows:
            if d.get("rig")!=rig or d["_excl"]: continue
            k=(d.get("engine"),d["_key"]); n=int(d["n"]); c=cand[k].get(n)
            if c is None or d["agg_tok_s"]>c["agg_tok_s"]: cand[k][n]=d
        L=[]
        for k,pts in cand.items():
            bn=max(pts,key=lambda n: pts[n]["agg_tok_s"]); d=pts[bn]
            L.append((d["agg_tok_s"]*d["_tot"],bn,d))
        L.sort(key=lambda t:-t[0])
        Bo[rig]=[dict(name=d["_name"],typ=d["_type"],quant=d["_quant"],eng=d["engine"],tot=d["_tot"],
            n=n,tok=d["agg_tok_s"],per=round(d["agg_tok_s"]/n,1),scoreB=round(s),
            rankA=posA.get((d.get("engine"),d["_key"])),date=d.get("date"),
            file=d.get("src_file"),loc=str(d.get("src_locator")),cfg=(d.get("config") or "")[:90])
            for s,n,d in L[:10]]
    stats=dict(parsed=len(rows),rankable=ranked,refusals=len(refusals),drop=dict(drop))
    json.dump(dict(tables=T,stats=stats),open(os.path.join(OUT,"payload.json"),"w"),indent=1)
    json.dump(Bo,open(os.path.join(OUT,"scoreB.json"),"w"),indent=1)
    print("wrote payload.json + scoreB.json")
