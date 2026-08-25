import json,subprocess,sys,time,urllib.request,os,socket
MODEL,MDIR = sys.argv[1],sys.argv[2]
CELLS = json.loads(sys.argv[3])          # [{"nm":38,"t":5,"extra":["--cache-type-k","q8_0"],"tag":"..."}]
IMG="ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"; PORT=8097
H=socket.gethostname()
SHORT="Write a Python function that merges two sorted lists."
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True).stdout.strip()
def post(p,n=128,to=1200):
    b=json.dumps({"prompt":p,"n_predict":n,"temperature":0,"cache_prompt":False}).encode()
    r=urllib.request.Request(f"http://localhost:{PORT}/completion",data=b,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=to) as f: return json.load(f)
for c in CELLS:
    nm,t,extra,tag = c["nm"], c["t"], c.get("extra",[]), c.get("tag","")
    sh("docker rm -f squeeze")
    args = f'-m /models/{os.path.basename(MODEL)} -ngl 99 --n-cpu-moe {nm} -t {t} -fa on --no-warmup --host 0.0.0.0 --port 8080 ' + " ".join(extra)
    sh(f'docker run -d --name squeeze --gpus all -v {MDIR}:/models:ro -p {PORT}:8080 {IMG} {args}')
    ok=False
    for _ in range(300):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y")=="Y": ok=True; break
        if "squeeze" not in sh("docker ps --format '{{.Names}}'"): break
        time.sleep(2)
    label=f"{H}\t{tag}\tnm={nm}\tt={t}\t{' '.join(extra) or '(baseline flags)'}"
    if not ok:
        why = sh("docker logs squeeze 2>&1 | grep -iE 'error|out of memory|failed to allocate' | tail -1")[:110]
        print(f"{label}\tREFUSED\t{why}",flush=True); sh("docker rm -f squeeze"); continue
    vram=sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    try: post("hi",16,900)
    except Exception: pass
    try: d=post(SHORT)
    except Exception as e:
        print(f"{label}\tREQ_FAIL {e}",flush=True); sh("docker rm -f squeeze"); continue
    tm=d["timings"]
    txt=d["content"].replace("\n"," ")[:70]
    print(f"{label}\tdecode={tm['predicted_per_second']:.2f}\tvram={vram}\tout={txt!r}",flush=True)
    sh("docker rm -f squeeze"); time.sleep(2)
