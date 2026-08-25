import json,subprocess,sys,time,urllib.request,socket,os
MODEL,MDIR,TAG=sys.argv[1],sys.argv[2],sys.argv[3]
CELLS=[c.split(":") for c in sys.argv[4:]]
IMG="ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"; PORT=8099
H=socket.gethostname()
SEG='''def process_record(record, config):
    result = {}
    for key, spec in config.items():
        raw = record.get(key)
        if raw is None and spec.get("required"):
            raise ValueError(f"missing required field {key}")
        result[key] = spec["cast"](raw) if raw is not None else spec.get("default")
    return result
'''
LONG=("Here is a Python module. Read it carefully, then answer the question at the end.\n\n"
      + SEG*22 + "\nQuestion: rewrite process_record so it collects every validation error "
      "instead of raising on the first one, and returns them alongside the result.")
SHORT="Write a Python function that merges two sorted lists."

def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True).stdout.strip()
def post(prompt,npred=128,timeout=900):
    body=json.dumps({"prompt":prompt,"n_predict":npred,"temperature":0,"cache_prompt":False}).encode()
    req=urllib.request.Request(f"http://localhost:{PORT}/completion",data=body,
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.load(r)
def energy():
    try: return int(sh("sudo -n cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"))
    except Exception: return None
def mhz():
    try:
        v=[float(l.split(":")[1]) for l in open("/proc/cpuinfo") if l.startswith("cpu MHz")]
        return round(sum(v)/len(v))
    except Exception: return 0

for nm,th in CELLS:
    sh("docker rm -f llmoe")
    sh(f'docker run -d --name llmoe --gpus all -v {MDIR}:/models:ro -p {PORT}:8080 {IMG} '
       f'-m /models/{os.path.basename(MODEL)} -ngl 99 --n-cpu-moe {nm} -t {th} '
       f'-c 4096 -fa on --no-warmup --host 0.0.0.0 --port 8080')
    ok=False
    for _ in range(150):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y")=="Y": ok=True; break
        if "llmoe" not in sh("docker ps --format '{{.Names}}'"): break
        time.sleep(2)
    if not ok:
        print(f"{H}\t{TAG}\tncpumoe={nm}\tt={th}\tFAILED",flush=True); sh("docker rm -f llmoe"); continue
    vram=sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    try: post("hi",16,600)
    except Exception: pass
    for lab,pr in (("SHORT",SHORT),("LONG ",LONG)):
        e0,t0=energy(),time.time()
        try: d=post(pr)
        except Exception as ex:
            print(f"{H}\t{TAG}\tncpumoe={nm}\tt={th}\t{lab}\tERR {ex}",flush=True); continue
        t1,e1=time.time(),energy()
        w=f"{(e1-e0)/1e6/(t1-t0):.1f}" if (e0 is not None and e1 is not None and e1>=e0) else "n/a"
        tm=d.get("timings",{})
        print(f"{H}\t{TAG}\tncpumoe={nm}\tt={th}\t{lab}\tvram={vram}\t"
              f"decode={tm.get('predicted_per_second',0):.2f}\tprefill={tm.get('prompt_per_second',0):.1f}\t"
              f"prompt_tok={tm.get('prompt_n',0)}\tpkg_W={w}\tMHz={mhz()}",flush=True)
    sh("docker rm -f llmoe"); time.sleep(3)
