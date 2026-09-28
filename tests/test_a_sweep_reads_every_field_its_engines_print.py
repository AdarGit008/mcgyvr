"""The two-card sweep reads each engine's own wording, and nothing reads unread.

On 2026-09-26 three CONFIG/level fields came back ``unread`` on every row: a
thinking model's tokens stream as ``reasoning_content`` (llama.cpp) or
``reasoning`` (vLLM 0.26), llama.cpp's buffer lines print only at ``-lv 4``,
and NCCL 2.28 prints the host-memory channel without ``/connIndex``. The lines
below are those engines' wording; each reader must find every field in them.
"""

from __future__ import annotations

from tools.runs.drivers import mgpu_read as rd

VLLM_TP2 = """\
(EngineCore pid=126) INFO 09-27 05:57:38 [core.py:116] Initializing a V1 LLM engine \
(v0.26.0) with config: model='/root/.cache/huggingface/hub/x', enforce_eager=False, \
kv_cache_dtype=auto, chunked_prefill=True, compilation_config={'cudagraph_mode': \
<CUDAGraphMode.FULL_AND_PIECEWISE: (2, 1)>, 'cudagraph_num_of_warmups': 1}
(Worker pid=155) INFO 09-27 06:16:12 [cuda_communicator.py:264] Using ['PYNCCL'] \
all-reduce backends (in dispatch order) for group 'tp:0' out of potential backends: \
['NCCL_SYMM_MEM', 'QUICK_REDUCE', 'CUSTOM', 'SYMM_MEM', 'PYNCCL'].
srv1:155:155 [0] NCCL INFO Channel 00 : 0[0] -> 1[1] via SHM/direct/direct
srv1:155:155 [0] NCCL INFO Channel 01 : 0[0] -> 1[1] via SHM/direct/direct
(Worker pid=156) WARNING 09-27 05:57:47 [custom_all_reduce.py:162] Custom allreduce is \
disabled because your platform lacks GPU P2P capability or P2P test failed. To silence \
this warning, specify disable_custom_all_reduce=True explicitly.
(Worker_TP0 pid=2) INFO Using MarlinLinearKernel for AWQMarlinLinearMethod
(Worker_TP0 pid=2) INFO Using FLASH_ATTN attention backend
(Worker_TP0 pid=2) INFO Graph capturing finished in 9 secs, took 0.31 GiB
(EngineCore pid=126) INFO 09-27 05:58:10 [kv_cache_utils.py:2177] GPU KV cache size: \
707,344 tokens
(EngineCore pid=126) INFO 09-27 05:58:10 [kv_cache_utils.py:2178] Maximum concurrency \
for 2,048 tokens per request: 345.38x
"""

LCP_LV4 = """\
load_tensors: offloading 28 repeating layers to GPU
load_tensors:          CPU_Mapped model buffer size =   292.36 MiB
load_tensors:        CUDA0 model buffer size =  1949.84 MiB
load_tensors:        CUDA1 model buffer size =  1949.83 MiB
llama_context: n_ctx_seq     = 2048
llama_context: n_ubatch      = 512
llama_kv_cache:      CUDA0 KV buffer size =    30.47 MiB
llama_kv_cache:      CUDA1 KV buffer size =    30.47 MiB
llama_context:      CUDA0 compute buffer size =   304.00 MiB
llama_context:      CUDA1 compute buffer size =   304.00 MiB
llama_context: graph splits = 3
"""


def test_a_thinking_models_tokens_are_counted_in_either_engines_field() -> None:
    assert rd.streamed_token({"reasoning_content": "Let"})
    assert rd.streamed_token({"reasoning": "Let"})
    assert rd.streamed_token({"content": "x"})
    assert not rd.streamed_token({"role": "assistant"})
    assert not rd.streamed_token({"content": ""})


def test_a_tp2_launch_log_leaves_no_field_unread() -> None:
    got = rd.read_vllm(VLLM_TP2, "tp2")
    bad = [f for f in got if f.endswith("=unread") and not f.startswith("nccl_proto")]
    assert bad == []
    assert "transport=SHM/direct/direct" in got
    assert "custom_ar=engine_disabled" in got
    assert "kv_tok=707344" in got
    assert "graphs=FULL_AND_PIECEWISE" in got
    assert "ar_backend=PYNCCL" in got


def test_custom_all_reduce_off_by_flag_is_not_the_engine_refusing_it() -> None:
    log = "INFO config: disable_custom_all_reduce=True, max_num_batched_tokens=2048"
    assert "custom_ar=flag_disabled" in rd.read_vllm(log, "tp2")
    assert "custom_ar=tp1" in rd.read_vllm(log, "pp2")


def test_a_p2p_channel_line_still_reads() -> None:
    log = "x:1:1 [0] NCCL INFO Channel 00/0 : 0[0] -> 1[1] via P2P/CUMEM/read"
    assert "transport=P2P/CUMEM/read" in rd.read_vllm(log, "tp2")


#: A tp2 launch once the driver grants peer access: vLLM enables its custom
#: all-reduce ahead of PYNCCL, NCCL takes the peer path, and under
#: VLLM_SKIP_P2P_CHECK=0 one rank runs vLLM's own peer test while the other
#: reads its result. The backend line is cuda_communicator.py's format at
#: v0.26.0; the cache lines are all_reduce_utils.py's.
VLLM_TP2_PEER = """\
(Worker_TP0 pid=155) INFO 09-28 06:16:02 [all_reduce_utils.py:359] generating GPU P2P \
access cache in /root/.cache/vllm/gpu_p2p_access_cache_for_0,1.json
(Worker_TP1 pid=156) INFO 09-28 06:16:09 [all_reduce_utils.py:408] reading GPU P2P \
access cache from /root/.cache/vllm/gpu_p2p_access_cache_for_0,1.json
(Worker_TP0 pid=155) INFO 09-28 06:16:12 [cuda_communicator.py:264] Using ['CUSTOM', \
'PYNCCL'] all-reduce backends (in dispatch order) for group 'tp:0' out of potential \
backends: ['NCCL_SYMM_MEM', 'QUICK_REDUCE', 'FLASHINFER', 'AITER_CUSTOM', 'CUSTOM', \
'SYMM_MEM', 'PYNCCL'].
srv1:155:155 [0] NCCL INFO Channel 00/0 : 0[0] -> 1[1] via P2P/CUMEM/read
srv1:155:155 [0] NCCL INFO Channel 01/0 : 0[0] -> 1[1] via P2P/CUMEM/read
"""


def test_a_tp2_launch_with_peer_access_reads_custom_all_reduce_on() -> None:
    got = rd.read_vllm(VLLM_TP2_PEER, "tp2")
    assert "custom_ar=on" in got
    assert "ar_backend=CUSTOM,PYNCCL" in got
    assert "transport=P2P/CUMEM/read" in got
    assert "p2p_check=tested" in got


def test_a_peer_backend_is_not_read_off_the_potential_list() -> None:
    """The host-memory log names CUSTOM only among the POTENTIAL backends."""
    got = rd.read_vllm(VLLM_TP2, "tp2")
    assert "custom_ar=engine_disabled" in got
    assert "p2p_check=none" in got


def test_the_engine_refusing_custom_all_reduce_outranks_a_backend_line() -> None:
    log = VLLM_TP2_PEER + (
        "WARNING [custom_all_reduce.py:162] Custom allreduce is disabled because "
        "your platform lacks GPU P2P capability or P2P test failed."
    )
    assert "custom_ar=engine_disabled" in rd.read_vllm(log, "tp2")


def test_a_rank_that_only_reads_the_peer_test_says_so() -> None:
    log = VLLM_TP2_PEER.split("\n", 1)[1]
    assert "p2p_check=cache" in rd.read_vllm(log, "tp2")
    assert any("P2P access cache" in line for line in rd.log_excerpt(log))


def test_a_split_llamacpp_launch_log_names_every_devices_buffers() -> None:
    got = rd.read_lcp(LCP_LV4)
    assert [f for f in got if f.endswith("=unread")] == []
    assert "buf=CPU_Mapped:292,CUDA0:1950,CUDA1:1950" in got
    assert "kvbuf=CUDA0:30,CUDA1:30" in got
    assert "graph_splits=3" in got


def test_an_unread_field_files_the_lines_it_looked_for() -> None:
    raw = rd.log_excerpt(VLLM_TP2 + LCP_LV4)
    assert any("via SHM" in line for line in raw)
    assert any("model buffer size" in line for line in raw)
    assert all("\t" not in line and len(line) <= 300 for line in raw)


DMON = """\
# gpu    pwr  gtemp  mtemp     sm    mem    enc    dec    jpg    ofa   mclk   pclk     fb   bar1   ccpm  rxpci  txpci
# Idx      W      C      C      %      %      %      %      %      %    MHz    MHz     MB     MB     MB   MB/s   MB/s
    0    150     60      -     90     70      0      0      0      0   7501   1882   9000      4      0    120     80
    1    140     58      -     88     69      0      0      0      0   7501   1867   9000      2      0    100     60
    0    152     61      -     92     71      0      0      0      0   7501   1882   9000      4      0    140    100
    1    141     58      -     86     68      0      0      0      0   7501   1867   9000      2      0     90     70
"""  # noqa: E501

MPSTAT = """\
05:05:53 AM  CPU    %usr   %nice    %sys %iowait    %irq   %soft  %steal  %guest  %gnice   %idle
05:05:54 AM  all   20.00    0.00    5.00    0.00    0.00    1.00    0.00    0.00    0.00   74.00
05:05:54 AM    0   90.00    0.00   10.00    0.00    0.00    0.00    0.00    0.00    0.00    0.00
05:05:54 AM    1   10.00    0.00    0.00    0.00    0.00    0.00    0.00    0.00    0.00   90.00
"""  # noqa: E501

VMSTAT = """\
procs -----------memory---------- ---swap-- -----io---- -system-- -------cpu-------
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st gu
 3  0 142736 2690568 535544 11826820  253  459  5285   699  975    1  3  0 97  0  0  0
 0  0 142736 2048000 535544 11826912    4    0     0     0  141  173  0  0 100  0  0  0
"""


def test_the_sidecar_files_read_into_link_core_and_swap_figures() -> None:
    assert rd.read_dmon(DMON) == [
        "sm0=91",
        "pcie0=130/90~140/100",
        "pclk0=1882",
        "sm1=87",
        "pcie1=95/65~100/70",
        "pclk1=1867",
    ]
    assert rd.read_mpstat(MPSTAT) == ["cpu_mean=55", "cpu_hot=100@0", "cpu_soft=1.0"]
    assert rd.read_vmstat(VMSTAT) == ["swap_kib=4", "free_min_mib=2000"]
    assert rd.read_mhz("4600.1\n4500.0\n") == ["cpu_mhz=4550"]


def test_an_empty_sidecar_file_reads_unread_not_zero() -> None:
    assert rd.read_dmon("") == ["dmon=unread"]
    assert rd.read_mpstat("") == ["cpu=unread"]
    assert rd.read_vmstat("") == ["vm=unread"]
