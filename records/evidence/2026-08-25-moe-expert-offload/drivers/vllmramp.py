import json,urllib.request,threading,time,socket,sys
PORT=8000; MODEL=sys.argv[1]; LEVELS=[int(x) for x in sys.argv[2].split(",")]
PROMPT="Write a Python function that merges two sorted lists."
NPRED=475
H=socket.gethostname()
def req(out,idx):
    body={"model":MODEL,"prompt":PROMPT,"max_tokens":NPRED,"temperature":0,"ignore_eos":True}
    r=urllib.request.Request(f"http://localhost:{PORT}/v1/completions",
        data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    t0=time.time()
    try:
        with urllib.request.urlopen(r,timeout=3600) as f: d=json.load(f)
        out[idx]=(d["usage"]["completion_tokens"],time.time()-t0)
    except Exception as e: out[idx]=(0,time.time()-t0)
req([None],0)
print(f"{H}\tvLLM {MODEL.split('/')[-1]}\tlevel\taggregate_tok_s\tp50_s\tcap_frac")
for n in LEVELS:
    out=[None]*n; th=[threading.Thread(target=req,args=(out,i)) for i in range(n)]
    t0=time.time()
    for t in th: t.start()
    for t in th: t.join()
    wall=time.time()-t0
    toks=sum(o[0] for o in out); lat=sorted(o[1] for o in out)
    cap=sum(1 for o in out if o[0]>=NPRED-5)/n
    print(f"{H}\t\tn={n}\t{toks/wall:.1f}\t{lat[len(lat)//2]:.2f}\t{cap:.2f}",flush=True)
