"""Canonical model -> (display name, type, total_B, active_B).
Source of truth: records/evidence/2026-08-28-setup-selection/drivers/analyze.py MODELS dict,
extended with the HF ids / ollama tags / gguf tags used by the earlier August runs."""
import re
CANON = {
 "qwen2.5-coder-1.5b": ("Qwen2.5-Coder-1.5B","dense",1.54,1.54),
 "qwen2.5-coder-3b":   ("Qwen2.5-Coder-3B","dense",3.09,3.09),
 "qwen2.5-coder-7b":   ("Qwen2.5-Coder-7B","dense",7.61,7.61),
 "qwen2.5-coder-14b":  ("Qwen2.5-Coder-14B","dense",14.70,14.70),
 "qwen2.5-coder-32b":  ("Qwen2.5-Coder-32B","dense",32.50,32.50),
 "qwen3-1.7b":         ("Qwen3-1.7B","dense",1.72,1.72),
 "qwen3-4b":           ("Qwen3-4B","dense",4.02,4.02),
 "qwen3-8b":           ("Qwen3-8B","dense",8.24,8.24),
 "qwen3-coder-30b-a3b":("Qwen3-Coder-30B-A3B","MoE",30.50,3.30),
 "qwen3.6-35b-a3b":    ("Qwen3.6-35B-A3B","MoE",35.00,3.00),
 "qwen3-coder-next-80b-a3b":("Qwen3-Coder-Next-80B-A3B","MoE",80.00,3.30),
 "nemotron-7b":        ("Nemotron-7B","dense",7.60,7.60),
 "nemotron-4b":        ("Nemotron-4B","dense",4.00,4.00),
 "nemotron-3-nano-30b-a3b":("Nemotron-3-Nano-30B-A3B","MoE",30.00,3.00),
 "nemotron-30b-a3b":   ("Nemotron-30B-A3B","MoE",30.00,3.00),
 "deepseek-coder-v2-lite":("DeepSeek-Coder-V2-Lite-16B","MoE",15.70,2.40),
 "gpt-oss-20b":        ("GPT-OSS-20B","MoE",20.50,3.60),
 "gpt-oss-4b":         ("GPT-OSS-4B","dense",4.20,4.20),
 "yi-coder-9b":        ("Yi-Coder-9B","dense",8.83,8.83),
 "north-mini-code-1.0": ("North-Mini-Code-1.0","MoE",30.00,3.00),
}
# ordered patterns: first match wins. Longer/more specific first.
PATS = [
 (r"next.*80b|80b.*a3b|qwen3-coder-next",            "qwen3-coder-next-80b-a3b"),
 (r"35b.*a3b|(^|[^0-9])35b|qwen3\.6.*35b|35B-IQ3XXS",              "qwen3.6-35b-a3b"),
 (r"nemotron.*3.*nano.*30b|nem30b",                  "nemotron-3-nano-30b-a3b"),
 (r"nemotron.*30b",                                  "nemotron-30b-a3b"),
 (r"qwen3.?coder.*30b|30b.?a3b|(^|[^0-9])30b",       "qwen3-coder-30b-a3b"),
 (r"deepseek.?coder.?v2|dscv2|ds16b",                 "deepseek-coder-v2-lite"),
 (r"north.?mini.?code|north-30b",                     "north-mini-code-1.0"),
 (r"yi.?coder.*9b|yi-coder",                          "yi-coder-9b"),
 (r"gpt.?oss.*20b|mxfp4.?20b|gptoss-20b",            "gpt-oss-20b"),
 (r"gpt.?oss.*4b|gptoss-4b",                         "gpt-oss-4b"),
 (r"nemotron.*4b",                                   "nemotron-4b"),
 (r"nemotron.*7b|nemotron7b",                        "nemotron-7b"),
 (r"qwen3.*8b|q3-8b",                                "qwen3-8b"),
 (r"qwen3.*4b|q3-4b",                                "qwen3-4b"),
 (r"qwen3.*1\.7b",                                   "qwen3-1.7b"),
 (r"coder.*32b|(^|[^0-9])32b",                       "qwen2.5-coder-32b"),
 (r"coder.*14b|(^|[^0-9])14b",                       "qwen2.5-coder-14b"),
 (r"coder.*7b|(^|[^0-9])7b",                         "qwen2.5-coder-7b"),
 (r"coder.*3b|(^|[^0-9])3b(?!.*a3b)",                "qwen2.5-coder-3b"),
 (r"coder.*1\.5b|1\.5b|15b-q4|vllm-15b",             "qwen2.5-coder-1.5b"),
]
QUANTS = ["UD-IQ3_XXS","IQ3_XXS","IQ2_XXS","IQ4_XS","Q3_K_XL","Q3_K_M","Q4_K_M","Q4_0","MXFP4","AWQ","FP8","fp8","GPTQ"]

def norm(model, quant=None, extra=""):
    s = f"{model or ''} {quant or ''} {extra or ''}".lower()
    for pat, key in PATS:
        if re.search(pat, s):
            return key, CANON[key]
    return None, None

def guess_quant(*parts):
    s = " ".join(str(p) for p in parts if p)
    for q in QUANTS:
        if q.lower() in s.lower(): return q.upper().replace("FP8","FP8")
    return None
