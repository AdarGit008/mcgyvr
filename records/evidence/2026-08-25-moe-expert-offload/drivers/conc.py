import json,urllib.request,threading,time,sys,socket
PORT=int(sys.argv[1]) if len(sys.argv)>1 else 8080
PATH=sys.argv[2] if len(sys.argv)>2 else "/completion"
LEVELS=[int(x) for x in (sys.argv[3].split(",") if len(sys.argv)>3 else ["1","2","4","8","16"])]
NPRED=128
H=socket.gethostname()
PROMPTS=[f"Write a Python function that merges two sorted lists. Variant {i}: name it merge_{i}." for i in range(64)]
def req(i,out,idx):
    body={"prompt":PROMPTS[i%len(PROMPTS)],"n_predict":NPRED,"temperature":0,"cache_prompt":False}
    if PATH.startswith("/v1"):
        body={"model":"m","prompt":PROMPTS[i%len(PROMPTS)],"max_tokens":NPRED,"temperature":0}
    r=urllib.request.Request(f"http://localhost:{PORT}{PATH}",data=json.dumps(body).encode(),
                             headers={"Content-Type":"application/json"})
    t0=time.time()
    try:
        with urllib.request.urlopen(r,timeout=1800) as f: d=json.load(f)
        if PATH.startswith("/v1"): n=d["usage"]["completion_tokens"]
        else: n=d["timings"]["predicted_n"]
        out[idx]=(n,time.time()-t0)
    except Exception as e: out[idx]=(0,time.time()-t0)
# warm
req(0,[None],0)
print(f"{H}\tlevel\taggregate_tok_s\tper_stream\tp50_latency_s\ttokens")
for n in LEVELS:
    out=[None]*n; th=[threading.Thread(target=req,args=(i,out,i)) for i in range(n)]
    t0=time.time()
    for t in th: t.start()
    for t in th: t.join()
    wall=time.time()-t0
    toks=sum(o[0] for o in out); lat=sorted(o[1] for o in out)
    p50=lat[len(lat)//2]
    print(f"{H}\tn={n}\t{toks/wall:.2f}\t{toks/wall/n:.2f}\t{p50:.2f}\t{toks}",flush=True)
