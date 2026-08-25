import json,subprocess,sys,time,urllib.request,os
BLOB="/usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a"
IMG="ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"; PORT=8098
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True).stdout.strip()
def post(p,n=128,to=1800):
    b=json.dumps({"prompt":p,"n_predict":n,"temperature":0,"cache_prompt":False}).encode()
    r=urllib.request.Request(f"http://localhost:{PORT}/completion",data=b,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=to) as f: return json.load(f)
CELLS=[(20,None),(20,"15g"),(40,None),(40,"15g")]
for nm,mem in CELLS:
    sh("docker rm -f memcap")
    memflag=f"--memory={mem} --memory-swap={mem}" if mem else ""
    sh(f'docker run -d --name memcap --gpus all {memflag} -v /usr/share/ollama/.ollama/models/blobs:/models:ro '
       f'-p {PORT}:8080 {IMG} -m /models/{os.path.basename(BLOB)} -ngl 99 --n-cpu-moe {nm} -t 4 '
       f'-c 4096 -fa on --no-warmup --host 0.0.0.0 --port 8080')
    ok=False
    for _ in range(240):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y")=="Y": ok=True; break
        if "memcap" not in sh("docker ps --format '{{.Names}}'"): break
        time.sleep(2)
    lab=f"n-cpu-moe={nm} mem={mem or 'unlimited(31G)'}"
    if not ok:
        print(f"{lab}\tFAILED\t{sh('docker logs memcap 2>&1 | tail -2')[:150]}",flush=True); sh("docker rm -f memcap"); continue
    vram=sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    try: post("hi",16,900)
    except Exception as e: print(f"{lab}\tWARMUP_FAIL {e}",flush=True)
    t0=time.time()
    try: d=post("Write a Python function that merges two sorted lists.")
    except Exception as e:
        print(f"{lab}\tREQ_FAIL {e}",flush=True); sh("docker rm -f memcap"); continue
    tm=d["timings"]
    stat=sh("docker stats --no-stream --format '{{.MemUsage}}' memcap")
    print(f"{lab}\tdecode={tm['predicted_per_second']:.2f}\tprefill={tm['prompt_per_second']:.1f}\tvram={vram}\tcgroup_mem={stat}\twall={time.time()-t0:.1f}s",flush=True)
    sh("docker rm -f memcap"); time.sleep(3)
