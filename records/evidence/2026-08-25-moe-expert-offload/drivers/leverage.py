# Leverage = decode tok/s x model size (GB) -> GB.tok/s of model exercised per second
CELLS = [
 # host, engine/config, model, size_GB, tok_s, vram_MiB
 ("srv2","ollama auto","deepseek-coder-v2:16b (MoE)",8.9,134.34,9500),
 ("srv2","llama.cpp n-cpu-moe 20","qwen3-coder:30b (MoE)",18.56,31.57,11283),
 ("srv2","ollama auto","qwen3-coder-next Q3 (MoE)",36.0,15.76,10615),
 ("srv2","ollama auto","gpt-oss:20b (MoE)",13.0,40.85,10883),
 ("srv2","ollama auto","qwen3-coder:30b (MoE)",18.56,28.62,10787),
 ("srv2","llama.cpp n-cpu-moe 24","qwen3-coder:30b (MoE)",18.56,26.32,9889),
 ("srv1","llama.cpp n-cpu-moe 40","qwen3-coder:30b (MoE)",18.56,25.43,4410),
 ("srv1","llama.cpp n-cpu-moe 44","qwen3-coder:30b (MoE)",18.56,25.37,2966),
 ("srv1","llama.cpp n-cpu-moe 48","qwen3-coder:30b (MoE)",18.56,21.60,1472),
 ("srv2","llama.cpp n-cpu-moe 32","qwen3-coder:30b (MoE)",18.56,20.73,7197),
 ("srv2","llama.cpp n-cpu-moe 40","qwen3-coder:30b (MoE)",18.56,17.80,4457),
 ("srv2","llama.cpp n-cpu-moe 48","qwen3-coder:30b (MoE)",18.56,15.07,1519),
 ("srv2","ollama auto","nemotron-3-nano:30b-a3b IQ2",18.0,13.18,5981),
 ("srv2","ollama auto","qwen2.5-coder:14b (dense)",9.0,34.57,9171),
 ("srv2","ollama auto","qwen2.5-coder:7b (dense)",4.7,66.57,4665),
 ("srv1","ollama auto","qwen2.5-coder:7b (dense)",4.7,50.11,4618),
]
rows=[]
for h,c,m,gb,t,v in CELLS:
    lev = t*gb
    rows.append((lev, lev/(v/1024.0), h,c,m,gb,t,v))
rows.sort(reverse=True)
print(f"{'leverage':>9} {'lev/GB-VRAM':>11}  {'host':<5} {'tok/s':>6} {'GB':>5} {'VRAM GB':>7}  config / model")
print("-"*104)
for lev,lpv,h,c,m,gb,t,v in rows:
    print(f"{lev:9.0f} {lpv:11.0f}  {h:<5} {t:6.1f} {gb:5.1f} {v/1024:7.1f}  {c} :: {m}")
