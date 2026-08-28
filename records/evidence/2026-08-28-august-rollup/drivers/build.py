import json,html,os
HERE=os.path.dirname(os.path.abspath(__file__))
SP=os.path.join(HERE,"..")
P=json.load(open(SP+"/payload.json")); T=P["tables"]; S=P["stats"]
B=json.load(open(SP+"/scoreB.json"))
# the divide-by-n column is THIS cell's own tok/s x size -- never a different-n row
for _rig in ("srv1","srv2"):
    for _r in T[f"{_rig}_multi"]:
        _r["scoreB"]=round(_r["score"]/_r["n"])
TT=json.load(open(SP+"/ttft.json"))["agg"]

SD=[("llama.cpp","srv2","Qwen2.5-Coder-7B IQ4_XS","qwen2.5-coder-1.5b","1",72.7,80.9,150,
     "best of four NMAX settings (76.0 / 79.7 / 80.2 / 80.9)"),
    ("llama.cpp","srv2","Qwen2.5-Coder-7B IQ4_XS","qwen2.5-coder-1.5b","4",212.6,226.2,150,
     "gain survives batching, but shrinks"),
    ("llama.cpp","srv1","Qwen3-Coder-30B-A3B","Qwen3-1.7B","1",22.8,23.5,60,
     "offload-bound at --n-cpu-moe 44; the draft cannot help what the PCIe bus gates"),
    ("vLLM","srv2","Qwen2.5-Coder-7B AWQ","Qwen2.5-Coder-1.5B AWQ","1",68.23,69.33,256,
     "the only vLLM pairing that is not a loss"),
    ("vLLM","srv2","Qwen2.5-Coder-7B AWQ","Qwen2.5-Coder-1.5B AWQ","8 cuda-graphs",475.37,418.39,256,""),
    ("vLLM","srv2","Qwen2.5-Coder-7B AWQ","Qwen2.5-Coder-1.5B AWQ","8 FLASH_ATTN",475.32,411.51,256,""),
    ("vLLM","srv2","Qwen2.5-Coder-7B AWQ","Qwen2.5-Coder-1.5B AWQ","8 eager",320.99,240.23,256,""),
    ("vLLM","srv1","Qwen2.5-Coder-3B AWQ","Qwen2.5-Coder-0.5B AWQ","8 eager",64.87,43.37,256,""),
    ("vLLM","srv1","Qwen2.5-Coder-3B AWQ","Qwen2.5-Coder-0.5B AWQ","8 cuda-graphs",64.85,37.97,256,
     "worst case measured: a third of throughput given away")]
e=html.escape
def fmt(x):
    return f"{x:,}" if isinstance(x,int) else f"{x:,.1f}"

def table(key,rig,mode):
    rows=T[key]; mx=max(r["score"] for r in rows)
    nh = "" if mode=="n1" else "<th class='r'>n</th>"
    bh = "" if mode=="n1" else "<th class='r'>score <i>&divide;n</i></th>"
    out=[f"<div class='tw {rig}'><table><thead><tr>"
         f"<th class='rk'>#</th><th>model</th><th>quant</th><th>engine</th>"
         f"<th class='r'>total&nbsp;B</th><th class='r'>tok/s</th>{nh}"
         f"<th class='r'>score{'' if mode=='n1' else ' <i>&times;n</i>'}</th>{bh}"
         f"</tr></thead><tbody>"]
    span = 6 if mode=="n1" else 8
    for i,r in enumerate(rows,1):
        pct=100*r["score"]/mx
        nc = "" if mode=="n1" else f"<td class='r num'>{r['n']}</td>"
        per = "" if mode=="n1" else f"<span class='per'>{r['per']}/stream</span>"
        bc=""
        if mode!="n1":
            b=r.get("scoreB"); bc=f"<td class='r num alt'>{b:,}</td>" if b else "<td class='r num alt'>&mdash;</td>"
        out.append(
         f"<tr class='main{' top' if i==1 else ''}'><td class='rk'>{i}</td>"
         f"<td class='mdl'>{e(r['name'])}<span class='ty {'moe' if r['typ']=='MoE' else 'dn'}'>{e(r['typ'])}</span></td>"
         f"<td class='mono sm'>{e(r['quant'])}</td>"
         f"<td class='mono sm'>{e(r['eng'] or '—')}</td>"
         f"<td class='r num'>{r['tot']}</td>"
         f"<td class='r num'>{fmt(r['tok'])}{per}</td>{nc}"
         f"<td class='r num sc'><span class='bar' style='width:{pct:.1f}%'></span>"
         f"<span class='scv'>{r['score']:,}</span></td>{bc}</tr>"
         f"<tr class='prov'><td></td><td colspan='{span}'>"
         f"<span class='dt'>{e(r['date'])}</span>"
         f"<span class='pf'>{e(r['file'])}</span><span class='pl'>{e(str(r['loc']))}</span>"
         f"<span class='cfg'>{e(r['cfg'])}</span></td></tr>")
    return "".join(out)+"</tbody></table></div>"

def tableB(rig):
    rows=B[rig]; mx=max(r["scoreB"] for r in rows)
    out=[f"<div class='tw {rig}'><table><thead><tr><th class='rk'>#</th><th>model</th>"
         f"<th class='mono'>quant</th><th>engine</th><th class='r'>total&nbsp;B</th>"
         f"<th class='r'>tok/s</th><th class='r'>n</th><th class='r'>score <i>&divide;n</i></th>"
         f"<th class='r'>was</th></tr></thead><tbody>"]
    for i,r in enumerate(rows,1):
        pct=100*r["scoreB"]/mx
        ra=r.get("rankA"); d = (ra-i) if ra else None
        mv = "<span class='mv same'>=</span>" if d==0 else (
             f"<span class='mv up'>&uarr;{d}</span>" if d and d>0 else (
             f"<span class='mv dn2'>&darr;{-d}</span>" if d else "<span class='mv'>&mdash;</span>"))
        out.append(
         f"<tr class='main{' top' if i==1 else ''}'><td class='rk'>{i}</td>"
         f"<td class='mdl'>{e(r['name'])}<span class='ty {'moe' if r['typ']=='MoE' else 'dn'}'>{e(r['typ'])}</span></td>"
         f"<td class='mono sm'>{e(r['quant'])}</td><td class='mono sm'>{e(r['eng'])}</td>"
         f"<td class='r num'>{r['tot']}</td>"
         f"<td class='r num'>{fmt(r['tok'])}<span class='per'>{r['per']}/stream</span></td>"
         f"<td class='r num'>{r['n']}</td>"
         f"<td class='r num sc'><span class='bar' style='width:{pct:.1f}%'></span>"
         f"<span class='scv'>{r['scoreB']:,}</span></td>"
         f"<td class='r num alt'>{('#'+str(ra)) if ra else '&mdash;'} {mv}</td></tr>"
         f"<tr class='prov'><td></td><td colspan='8'><span class='dt'>{e(r['date'])}</span>"
         f"<span class='pf'>{e(r['file'])}</span><span class='pl'>{e(r['loc'])}</span>"
         f"<span class='cfg'>{e(r['cfg'])}</span></td></tr>")
    return "".join(out)+"</tbody></table></div>"

def sdtable():
    out=["<div class='tw'><table><thead><tr><th>engine</th><th>rig</th><th>target</th>"
         "<th>draft</th><th class='r'>n</th><th class='r'>no draft</th><th class='r'>with draft</th>"
         "<th class='r'>&times;</th><th>note</th></tr></thead><tbody>"]
    for eng,rig,tgt,drf,n,base,sd,tpr,note in SD:
        rat=sd/base; cls="gain" if rat>1.005 else ("loss" if rat<0.995 else "flat")
        out.append(f"<tr class='main sdr'><td class='mono sm'>{e(eng)}</td>"
          f"<td class='mono sm {rig}t'>{rig}</td><td class='mdl sdm'>{e(tgt)}</td>"
          f"<td class='mono sm'>{e(drf)}</td><td class='r num'>{e(n)}</td>"
          f"<td class='r num'>{base}</td><td class='r num'>{sd}</td>"
          f"<td class='r num ratio {cls}'>{rat:.2f}</td>"
          f"<td class='sdn'>{e(note)}<span class='tprn'>{tpr}-token replies</span></td></tr>")
    return "".join(out)+"</tbody></table></div>"

def ttfttable():
    mx=max(r["ttft_ms"] for r in TT)
    out=["<div class='tw'><table><thead><tr><th>rig</th><th>model</th><th class='r'>n</th>"
         "<th class='r'>reqs</th><th class='r'>TTFT p50</th><th class='r'>prefill</th>"
         "<th class='r'>queue</th><th>split</th></tr></thead><tbody>"]
    for r in TT:
        pf=100*r["prefill_ms"]/r["ttft_ms"]; q=100*r["queue_ms"]/r["ttft_ms"]
        w=100*r["ttft_ms"]/mx
        out.append(f"<tr class='main ttr'><td class='mono sm {r['rig']}t'>{r['rig']}</td>"
          f"<td class='mdl sdm'>{e(r['model'])}</td><td class='r num'>{r['n']}</td>"
          f"<td class='r num sm'>{r['reqs']}</td>"
          f"<td class='r num big'>{r['ttft_ms']:,.0f}<span class='u'>ms</span></td>"
          f"<td class='r num sm'>{r['prefill_ms']:,.0f}</td>"
          f"<td class='r num sm'>{r['queue_ms']:,.0f}</td>"
          f"<td class='splitc'><span class='sbar' style='width:{w:.1f}%'>"
          f"<span class='sp pf' style='width:{pf:.1f}%'></span>"
          f"<span class='sp qu' style='width:{q:.1f}%'></span></span></td></tr>")
    return "".join(out)+"</tbody></table></div>"

DROP=[("not on the 475-token protocol",S['drop']['not-475-protocol'],
       "ollama and LMDeploy stop on EOS (replies ran 294–390 tokens); the whole 2026-08-25 expert-offload campaign is a 128-token run."),
      ("restatement of a row already counted",S['drop']['restatement'],
       "Post-swap summary tables and survey repeat arrays re-print earlier runs. levels[i] is the max of its repeats, not a fresh sample."),
      ("secondary baseline mine",S['drop']['baseline-mine'],
       "baseline-2026-08-23..27.jsonl is labelled reference-only, and its implied reply length varies 302–475 tokens. Every directory it mines is covered by a primary read."),
      ("co-resident, not solo",S['drop']['co-resident'],
       "Measured with a second model still holding VRAM — not the number you get running it alone."),
      ("offline harness",S['drop']['offline-harness'],
       "llama-batched-bench is not a server; it does not measure serving throughput."),
      ("speculative decoding",S['drop']['spec-decoding'],
       "Target+draft pairs are a different quantity. Their matched no-draft baselines are kept and do rank."),
      ("contaminated or superseded",S['drop']['contaminated'],
       "srv1 gpt-oss-4b np=32 was re-run as contaminated; its two attempts disagree 22% at n=16."),
      ("retracted by the record",S['drop']['retracted'],
       "The docker --memory=15g cells never bound: the GGUF sat in host page cache outside the cgroup."),
      ("control / bridge run",S['drop']['control-run'],
       "b10481 cells exist to bridge builds, not to be chosen.")]

CAV=[("The headline score multiplies n twice.",
  "<code>agg_tok_s</code> is already summed across all n streams — verified against <code>n × 475 / wall</code> to a 0.13% median error across 295 levels, with the per-stream reading rejected at 87% error. The <b>÷n</b> column in tables 3 and 4, and the re-ranked tables above, carry the corrected reading. Both are shown because the quadratic version is the key as written and as the 08-28 record's own Key 2 applies it."),
 ("Anything inside 2.6% on srv1 or 5.2% on srv2 is noise.",
  "Those are the across-reload spreads, not the 0.04%/0.2% within-service figures the raw files quote. srv1 also drifts about 2.6% downward over six minutes of load, so any A-then-B contrast is biased against B. Ranks 9 and 10 of a table are frequently the same setup twice."),
 ("Peak throughput is not free.",
  "srv1's top fleet row holds 128.1 tok/s at n=32 with a 118.6-second p50 — each caller waits two minutes. srv2's 1.5B ceiling run needs 30.2 s of wall at n=384. The score has no latency term."),
 ("Four claims in the record were falsified on re-measurement.",
  "The srv2 <code>--no-mmap</code> win is +2.1% cold, not +63%. The srv1 ncmoe=38 peak does not exist — 37 is 1.7% above it, inside the noise bar. srv1's memory bandwidth is 19.6 GB/s, not 26.8, which inverts the srv1/srv2 bandwidth ratio. Rows resting on those readings are flagged or dropped."),
 ("Total params is the smarts proxy, not active.",
  "The owner's lean. On active params the podium inverts — GPT-OSS-20B's 97.0 tok/s scores 1,988 on 20.5B total but 349 on 3.6B active, behind GPT-OSS-4B's 548. Active params are carried in the dataset if you want to re-score."),
 ("Two big directories hold no throughput at all.",
  "<code>2026-08-23-phase0-footprint</code> (2.6 MB survey) and <code>phase0-refit</code> set <code>collect.concurrency=false</code> by design — they measure VRAM residency and weight digests. 4.4 MB of evidence, zero cells.")]

WALL=[("14B dense on llama.cpp","both","8.9 GB weights + KV exceeds the budget at every np that fits"),
 ("32B dense","srv1 / srv2","OOM on the 6 GB card; srv2's 15 GB RAM is under the 19.9 GB file"),
 ("gpt-oss-20b MXFP4","srv1","cudaMalloc OOM — 12.1 GB file, 6 GB card"),
 ("gpt-oss-20b Q3_K_M","both","<code>unknown model architecture: 'gptoss'</code> — the unsloth tag; only the official MXFP4 conversion loads"),
 ("7B AWQ on vLLM","srv1","OOM at util 0.85–0.95 — cc 7.5, no FA2. 100% refusal across 8 attempts; there is no srv1 7B vLLM number anywhere"),
 ("nemotron-4b fp8","both","<code>Minimum capability: 89. Current: 75/86</code>"),
 ("vLLM seqs=256 on srv2","srv2","<code>Engine core initialization failed</code> on driver 595.84 — but the 08-24 runs on driver 580 reached n=384"),
 ("speculative decoding, 08-24","both","recorded as refused, but the cause was a shell-quoting bug that split the JSON — it was never actually tested")]

css = """
:root{--paper:#F1F4F4;--surf:#FAFBFB;--ink:#111819;--mut:#5D6B6E;--faint:#859599;--rule:#D6DDDD;--rule2:#E7ECEC;--s1:#8F5B18;--s1b:#F0E4D2;--s2:#0D6670;--s2b:#D8EAEC;
--warn:#8E3527;--warnb:#F2DED9;--bar:#C3CFCF}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--paper:#0D1214;--surf:#141B1D;--ink:#E4ECEC;--mut:#93A3A6;--faint:#6E7E82;
--rule:#232E31;--rule2:#1B2426;--s1:#D9A45E;--s1b:#2E2317;--s2:#57C3CD;--s2b:#0F2A2E;
--warn:#E08C7C;--warnb:#2C1B17;--bar:#2A3639}}
:root[data-theme="dark"]{--paper:#0D1214;--surf:#141B1D;--ink:#E4ECEC;--mut:#93A3A6;
--faint:#6E7E82;--rule:#232E31;--rule2:#1B2426;--s1:#D9A45E;--s1b:#2E2317;--s2:#57C3CD;
--s2b:#0F2A2E;--warn:#E08C7C;--warnb:#2C1B17;--bar:#2A3639}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);margin:0;
font-family:"Source Serif 4",Georgia,serif;font-size:16.5px;line-height:1.6;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 96px}
h1,h2,h3,.lbl,th,.chip{font-family:Archivo,"Helvetica Neue",Arial,sans-serif}
.mono,.num,code,.pf,.pl,.cfg,.dt{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;
font-variant-numeric:tabular-nums}
.lbl{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut);font-weight:600}

header{border-bottom:2px solid var(--ink);padding:56px 0 22px;margin-bottom:8px}
h1{font-size:clamp(30px,5.2vw,52px);line-height:1.02;margin:10px 0 18px;font-weight:700;
letter-spacing:-.022em;text-wrap:balance;max-width:16ch}
.sub{color:var(--mut);max-width:62ch;margin:0 0 26px}
.eq{display:flex;flex-wrap:wrap;align-items:baseline;gap:9px;padding:15px 18px;
background:var(--surf);border:1px solid var(--rule);font-size:15px}
.eq b{font-family:"JetBrains Mono",monospace;font-weight:700}
.eq i{font-style:normal;color:var(--faint)}
.meta{display:flex;flex-wrap:wrap;gap:26px;margin-top:20px}
.meta div{display:flex;flex-direction:column;gap:2px}
.meta .v{font-family:"JetBrains Mono",monospace;font-size:20px;font-weight:500;
font-variant-numeric:tabular-nums}

.rigs{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;margin:34px 0 8px}
.rig{border:1px solid var(--rule);background:var(--surf);padding:16px 18px;border-top:3px solid}
.rig.srv1{border-top-color:var(--s1)} .rig.srv2{border-top-color:var(--s2)}
.rig h3{margin:6px 0 10px;font-size:19px;letter-spacing:-.01em}
.rig.srv1 h3{color:var(--s1)} .rig.srv2 h3{color:var(--s2)}
.rig dl{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0;font-size:13.5px}
.rig dt{color:var(--faint);font-family:Archivo,sans-serif;font-size:11px;letter-spacing:.1em;
text-transform:uppercase;padding-top:3px}
.rig dd{margin:0;font-family:"JetBrains Mono",monospace;font-size:13px}

section{margin-top:52px}
h2{font-size:26px;letter-spacing:-.015em;margin:0 0 4px;font-weight:700}
.hint{color:var(--mut);font-size:14.5px;margin:0 0 22px;max-width:70ch}
.tw{overflow-x:auto;border:1px solid var(--rule);background:var(--surf);margin-bottom:22px}
.tw.srv1{border-left:3px solid var(--s1)} .tw.srv2{border-left:3px solid var(--s2)}
table{border-collapse:collapse;width:100%;min-width:720px}
th{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--mut);
font-weight:600;text-align:left;padding:11px 12px 9px;border-bottom:1px solid var(--rule)}
td{padding:9px 12px;border-bottom:1px solid var(--rule2);vertical-align:baseline}
tr.main.top td{background:color-mix(in srgb,var(--paper) 55%,transparent)}
.tw.srv1 tr.main.top td{background:var(--s1b)} .tw.srv2 tr.main.top td{background:var(--s2b)}
tr.prov td{padding:0 12px 11px;border-bottom:1px solid var(--rule);font-size:11px;color:var(--faint)}
tr.main td{border-bottom:none}
.rk{width:30px;color:var(--faint);font-family:"JetBrains Mono",monospace;font-size:12px}
.mdl{font-weight:600;font-size:15.5px;letter-spacing:-.008em;white-space:nowrap}
.ty{font-family:Archivo,sans-serif;font-size:9.5px;letter-spacing:.09em;margin-left:7px;
padding:2px 5px;border:1px solid var(--rule);color:var(--mut);vertical-align:2px}
.ty.moe{border-color:currentColor}
.r{text-align:right}
.num{font-family:"JetBrains Mono",monospace;font-size:14px}
.sm{font-size:12px;color:var(--mut)}
.per{display:block;font-size:10.5px;color:var(--faint);margin-top:1px}
.sc{position:relative;min-width:118px}
.bar{position:absolute;left:0;right:auto;top:4px;bottom:4px;background:var(--bar);
opacity:.55;z-index:0}
.tw.srv1 .bar{background:var(--s1);opacity:.16} .tw.srv2 .bar{background:var(--s2);opacity:.16}
.scv{position:relative;z-index:1;font-weight:600}
.dt,.pf,.pl,.cfg{margin-right:12px;white-space:nowrap}
.dt{color:var(--mut)}
.pl{color:var(--ink);opacity:.75}
.cfg{opacity:.72}

.cav{display:grid;gap:0;border-top:1px solid var(--rule)}
.cav > div{padding:16px 0;border-bottom:1px solid var(--rule2);display:grid;
grid-template-columns:minmax(200px,.9fr) 2fr;gap:8px 32px}
.cav h4{margin:0;font-family:Archivo,sans-serif;font-size:15px;font-weight:600;
letter-spacing:-.005em;text-wrap:balance}
.cav p{margin:0;font-size:14.5px;color:var(--mut)}
code{font-size:.86em;background:var(--rule2);padding:1px 4px;border-radius:2px}

.drop{width:100%;border-collapse:collapse;min-width:0}
.drop td{border-bottom:1px solid var(--rule2);font-size:14px;padding:10px 12px 10px 0}
.drop td:first-child{font-family:"JetBrains Mono",monospace;text-align:right;width:64px;
font-size:14px;color:var(--ink);font-weight:500;padding-right:16px}
.drop td:nth-child(2){font-family:Archivo,sans-serif;font-size:13.5px;white-space:nowrap;
padding-right:22px}
.drop td:last-child{color:var(--mut);font-size:13.5px}
.walls td{border-bottom:1px solid var(--rule2);padding:9px 14px 9px 0;font-size:13.5px;
vertical-align:baseline}
.walls td:first-child{font-family:"JetBrains Mono",monospace;white-space:nowrap;font-size:12.5px}
.walls td:nth-child(2){font-family:Archivo,sans-serif;font-size:10.5px;letter-spacing:.09em;
text-transform:uppercase;color:var(--warn);white-space:nowrap}
.walls td:last-child{color:var(--mut)}
.walls{width:100%;border-collapse:collapse}

th i{font-style:normal;font-family:"JetBrains Mono",monospace;text-transform:none;
letter-spacing:0;opacity:.62}
.alt{color:var(--mut)}
td.alt .mv{margin-left:6px;font-size:11px;font-family:Archivo,sans-serif}
.mv.up{color:var(--s2)} .mv.dn2{color:var(--warn)} .mv.same{color:var(--faint)}
.srv1t{color:var(--s1);font-weight:600} .srv2t{color:var(--s2);font-weight:600}
tr.sdr td,tr.ttr td{border-bottom:1px solid var(--rule2)}
.sdm{font-size:14px;white-space:nowrap}
.ratio{font-weight:700;font-size:15px}
.ratio.gain{color:var(--s2)} .ratio.loss{color:var(--warn)} .ratio.flat{color:var(--mut)}
.sdn{font-size:12.5px;color:var(--mut);max-width:34ch}
.tprn{display:block;font-family:"JetBrains Mono",monospace;font-size:10.5px;color:var(--faint)}
.big{font-size:16px;font-weight:600}
.u{font-size:10px;color:var(--faint);margin-left:2px}
.splitc{width:190px;min-width:150px}
.sbar{display:flex;height:9px;background:var(--rule2);border:1px solid var(--rule)}
.sp.pf{background:var(--s2);opacity:.85} .sp.qu{background:var(--s1);opacity:.7}
.legend{display:flex;gap:18px;font-size:11.5px;color:var(--mut);margin:10px 0 0;
font-family:Archivo,sans-serif}
.legend span{display:flex;align-items:center;gap:6px}
.legend i{width:13px;height:9px;display:inline-block;border:1px solid var(--rule)}
.math{background:var(--surf);border:1px solid var(--rule);border-left:3px solid var(--ink);
padding:18px 20px;margin:20px 0;font-family:"JetBrains Mono",monospace;font-size:14px;
line-height:2;overflow-x:auto}
.math b{font-weight:700} .math em{font-style:normal;color:var(--mut)}
.math .hl{background:var(--s1b);padding:1px 4px;font-weight:700}
.note{border-left:3px solid var(--warn);background:var(--warnb);padding:14px 18px;
font-size:14.5px;margin:18px 0}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--rule);color:var(--faint);
font-size:13px}
@media(max-width:720px){.cav > div{grid-template-columns:1fr;gap:5px}}
"""

def caption(rig,mode):
    if rig=="srv1":
        return ("GTX 1660 SUPER · 6 GB · 48 GB DDR4" )
    return ("RTX 3060 · 12 GB · 16 GB DDR4")

H=f"""<title>Rig Ladder</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>{css}</style>
<div class="wrap">
<header>
<div class="lbl">mcgyvr · serving evidence · 2026-08-19 → 2026-08-28</div>
<h1>Which setup earns the slot</h1>
<p class="sub">Every decode-throughput measurement taken in August across both rigs, normalised to one
score and ranked. Each cell names the run it came from.</p>
<div class="eq"><b>score</b><i>=</i><b>tok/s</b><i>×</i><b>total params (B)</b><i>×</i><b>n</b>
<i>— aggregate throughput, 475-token replies, ignore_eos, temp 0, one fixed prompt</i></div>
<div class="meta">
<div><span class="lbl">rows extracted</span><span class="v">{S['parsed']:,}</span></div>
<div><span class="lbl">rankable</span><span class="v">{S['rankable']:,}</span></div>
<div><span class="lbl">refusals recorded</span><span class="v">{S['refusals']}</span></div>
<div><span class="lbl">directories mined</span><span class="v">15</span></div>
</div>
</header>

<div class="rigs">
<div class="rig srv1"><div class="lbl">rig one</div><h3>srv1</h3>
<dl><dt>gpu</dt><dd>GTX 1660 SUPER · 6 GB · sm75</dd>
<dt>cpu</dt><dd>i5-9600K · 6c/6t · 4.6 GHz</dd>
<dt>ram</dt><dd>48 GB DDR4-3200 · 19.6 GB/s</dd>
<dt>trait</dt><dd>big RAM, small card → expert offload</dd></dl></div>
<div class="rig srv2"><div class="lbl">rig two</div><h3>srv2</h3>
<dl><dt>gpu</dt><dd>RTX 3060 · 12 GB · sm86</dd>
<dt>cpu</dt><dd>i9-10900F · 10c/20t · turbo off</dd>
<dt>ram</dt><dd>16 GB DDR4-2667 · 20.3 GB/s</dd>
<dt>trait</dt><dd>big card, small RAM → fits on GPU</dd></dl></div>
</div>

<section>
<div class="lbl">table 1 &amp; 2 — n = 1</div>
<h2>One request, one user</h2>
<p class="hint">Nobody waiting behind you. The score collapses to tok/s × size, so it asks one question:
how much model can the rig push at interactive speed. Both rigs answer with a
mixture-of-experts model — few active params to compute, many total params to count. srv2's
answer is <b>North-Mini-Code-1.0</b>, added to the evidence base on 2026-08-27: 30B total on
3B active, whole model on the card at IQ2_M, 90.3 tok/s. It beats the incumbent GPT-OSS-20B
by 36%.</p>
<div class="lbl" style="margin-bottom:7px">srv1 · {caption('srv1','n1')}</div>
{table('srv1_n1','srv1','n1')}
<div class="lbl" style="margin-bottom:7px">srv2 · {caption('srv2','n1')}</div>
{table('srv2_n1','srv2','n1')}
</section>

<section>
<div class="lbl">table 3 &amp; 4 — n = argmax</div>
<h2>Many requests, many users</h2>
<p class="hint">Each setup is taken at the concurrency that maximises its own score, over the measured
ladder {{1 … 384}}. This is where the two rigs stop resembling each other: srv1's best fleet row is a
35B MoE crawling at 4.0 tok/s per stream, srv2's is a 1.5B on vLLM serving 384 streams at once.</p>
<div class="lbl" style="margin-bottom:7px">srv1 · {caption('srv1','multi')}</div>
{table('srv1_multi','srv1','multi')}
<div class="lbl" style="margin-bottom:7px">srv2 · {caption('srv2','multi')}</div>
{table('srv2_multi','srv2','multi')}
</section>


<section>
<div class="lbl">the formula</div>
<h2>Why n is counted twice</h2>
<p class="hint">The formula is right. The number it is fed is the wrong one.</p>
<div class="math">
<em>what the record stores at concurrency n:</em><br>
<b>agg_tok_s</b> = total tokens from all n streams &divide; wall = <b>per_stream &times; n</b><br><br>
<em>so the key, evaluated on the stored number, becomes:</em><br>
score = agg_tok_s &times; size &times; n = per_stream &times; size &times; <span class="hl">n&sup2;</span>
</div>
<p class="hint">Written as <code>tok/s &times; size &times; n</code> with <b>tok/s meaning one stream's rate</b>,
the key is exactly correct &mdash; it is model-mass delivered per second across the fleet. The record
stores the aggregate instead, which already contains n. Feeding the aggregate in makes the score
quadratic in width, so it does not rank setups: it ranks how many slots each one will accept.</p>
<div class="note"><b>Both readings collapse to the same simple thing.</b>
<code>per_stream &times; size &times; n</code> = <code>agg_tok_s &times; size</code>. That is the
<b>&divide;n</b> column added to tables 3 and 4 &mdash; the same cell, with the second n removed.
No new measurement, just the arithmetic the key intended.</div>
<p class="hint">It matters. Under the quadratic score the argmax always drifts to the widest level that
has not yet collapsed; under the corrected one it lands where aggregate throughput actually peaks.
Below is the fleet top ten re-ranked, each setup taken at its own new argmax n.</p>

<div class="lbl" style="margin-bottom:7px">srv1 &middot; corrected fleet score &mdash; tok/s &times; total&nbsp;B</div>
{tableB('srv1')}
<div class="lbl" style="margin-bottom:7px">srv2 &middot; corrected fleet score &mdash; tok/s &times; total&nbsp;B</div>
{tableB('srv2')}
<p class="hint">srv2's answer changes hands entirely. The 1.5B that wins on the quadratic score falls
to fourth; <b>North-Mini-Code-1.0 at n=16</b> takes it on 518.4 tok/s &times; 30B, and
Qwen2.5-Coder-7B AWQ at n=256 &mdash; the setup the 08-28 record picked before the driver capped it at
n=128 &mdash; comes second. A 30B MoE that never accepted more than 16 streams was invisible under the
quadratic score and is the best fleet setup on the rig under the corrected one. On srv1 the
mixture-of-experts models climb three to seven places each: they were being punished for not accepting
128 streams, which was never the question.</p>
</section>

<section>
<div class="lbl">speculative decoding</div>
<h2>What a draft model actually buys</h2>
<p class="hint">Nine measured target/draft pairs, each against its own no-draft baseline from the same
run and the same build. These are not on the 475-token protocol &mdash; reply lengths were 60, 150 and
256 tokens &mdash; so the <b>ratio</b> transfers to the ladder above, the absolute rates do not.</p>
{sdtable()}
<p class="hint">The split is by engine, not by rig. <b>llama.cpp gains</b>: +11% on the srv2 7B at n=1,
still +6% at n=4. <b>vLLM loses under load</b>: every batched pairing measured is negative, down to
0.59&times; on srv1 &mdash; the draft steals the compute the batch was using. At n=1 on srv2 vLLM it is
a wash at 1.02&times;.</p>
<div class="note"><b>It changes no table above.</b> Applied to the two ranked setups that have a
measured pairing, srv1's Qwen3-Coder-30B-A3B goes 790 &rarr; <b>814</b> (holds rank 3) and srv2's
7B IQ4_XS goes 548 &rarr; <b>610</b> (rank 10 &rarr; 8). Nothing else moves, and no fleet row improves
at all. Two SD configurations were never tested: 35B-A3B native MTP and external-draft on srv1 are
narrative-only refusals with no measurement, and vLLM rejects the 1.5B&rarr;7B pair outright without
<code>use_heterogeneous_vocab</code>.</div>
</section>

<section>
<div class="lbl">time to first token</div>
<h2>How long before it starts talking</h2>
<p class="hint">TTFT was never recorded under the 475-token protocol &mdash; neither the llama.cpp nor
the vLLM driver logs it, and it cannot be recovered from p50 and wall alone. It exists in exactly one
place: 334 per-request ollama records in the 08-24 engine sweep, which report prefill, decode and
total separately. <b>TTFT here is derived as total &minus; decode</b>, so it includes queue wait &mdash;
which is the honest number, because that is what the caller feels.</p>
{ttfttable()}
<div class="legend"><span><i style="background:var(--s2);opacity:.85"></i>prefill</span>
<span><i style="background:var(--s1);opacity:.7"></i>queue wait</span>
<span><i style="background:var(--rule2)"></i>bar length &prop; TTFT</span></div>
<p class="hint">At n=1 srv2 answers in <b>20.8 ms</b> against srv1's <b>42.1 ms</b> &mdash; the same
2&times; that shows up everywhere else between these two rigs. The shape changes with width: through
n=32 prefill dominates and TTFT tracks the model, but at n=128 on srv2 <b>queue wait is 523 ms of the
809 ms</b>. Past that point TTFT stops measuring the engine and starts measuring the backlog, which
is precisely the cost the fleet tables charge nothing for.</p>
<div class="note">These are ollama numbers on 1.5B and 7B only. They set the floor and the shape, not
the value for a vLLM or llama.cpp setup in the tables above. Measuring TTFT on the ranked setups is
an unrun experiment.</div>
</section>

<section>
<div class="lbl">before you act on these</div>
<h2>Six things the tables do not say</h2>
<div class="cav">
{''.join(f'<div><h4>{t}</h4><p>{b}</p></div>' for t,b in CAV)}
</div>
</section>

<section>
<div class="lbl">evidence base</div>
<h2>What was dropped, and why</h2>
<p class="hint">{S['parsed']:,} measured rows came out of the August directories. {S['rankable']:,} were
eligible to rank. The gap is not noise — it is rows that answer a different question.</p>
<table class="drop"><tbody>
{''.join(f'<tr><td>{n:,}</td><td>{t}</td><td>{d}</td></tr>' for t,n,d in DROP)}
</tbody></table>
</section>

<section>
<div class="lbl">walls</div>
<h2>Empty cells, with cause</h2>
<p class="hint">A refusal is a recorded result. 195 of them are in the dataset with the engine's own
sentence; these are the ones that shape the tables above.</p>
<table class="walls"><tbody>
{''.join(f'<tr><td>{t}</td><td>{r}</td><td>{c}</td></tr>' for t,r,c in WALL)}
</tbody></table>
</section>

<footer>
Extracted from <code>records/evidence/</code> — 15 directories dated 2026-08-02 through 2026-08-28.
Model parameter counts follow <code>2026-08-28-setup-selection/drivers/analyze.py</code>.
Provenance under each row is <span class="mono">date · file · locator · config</span>; every figure
resolves to that line.
</footer>
</div>"""
open(SP+"/rig-ladder.html","w").write(H)
print("bytes",len(H))
