---
title: "How Much Can Two Nvidia L4s Serve? It Depends on the Prompt."
date: 2026-04-28
---

# How much can two L4s serve? It depends on the prompt.

*Follow-up to [Streaming LLM inference on EKS](https://nicolas-richard.github.io/posts/streaming-llm-inference-on-eks.html). The first post covered the build — Terraform, EKS, vLLM Production Stack, the streaming gateway. This one covers the obvious next question: now that it works, how much can it actually serve?*

## A simple question with two answers

After getting the cluster running, I wanted one number to put on the front of the README: *how many requests per second can two L4 GPUs handle?*

It turns out that's the wrong question, because the answer depends entirely on what the requests *look like*.

Same hardware, same concurrency, same five-minute sustained load. Only the workload shape differs:

| Workload | req/s | p95 TTFT | $/M total tokens |
|---|---|---|---|
| Cache-friendly: long shared system prompt + short user query | **13.0** | **503 ms** | **$0.069** |
| Cache-hostile: independent random prompts | 6.7 | 1,843 ms | $0.127 |

Two times the throughput. Three-and-a-half times lower latency. Roughly half the cost per token. Same dollars per hour. The difference is whether the requests share context — and whether the router knows about it.

## The setup, briefly

Full architecture in the [previous post](https://nicolas-richard.github.io/posts/streaming-llm-inference-on-eks.html). The relevant bits:

- 2× AWS `g6.2xlarge`
- Qwen2.5-7B-Instruct, BF16, vLLM 0.19.1
- vLLM Production Stack as the router, with `routingLogic=prefixaware` — so requests with the same prefix consistently land on the same worker, and the KV cache stays warm
- 2× `g6.2xlarge` on-demand in us-east-1 = **$1.96/hr**

The `prefixaware` routing is the architectural point of vLLM Production Stack over plain vLLM. With round-robin routing across two workers, the same prefix would land on either worker depending on which one was idle, and you'd end up paying prefill for the same 384 tokens of system prompt twice — once on each worker — even though it's the same text.

## How I measured this

`vllm bench serve` — the official vLLM benchmarking CLI — drives synthetic load against the cluster from a small runner pod sitting in the same VPC as the workers, so measurements aren't bottlenecked by the laptop's network.

Two workload shapes, both with **512 tokens of input and 128 of output** so the only thing that varies between arms is the *sharing pattern*:

- **Cache-friendly:** `--dataset-name prefix_repetition` — 384 tokens of shared system-prompt-like text (drawn from a pool of 8 distinct prefixes) plus 128 unique tokens per prompt. Models the chatbot/RAG/agent shape.
- **Cache-hostile:** `--dataset-name random --random-input-len 512` — every prompt is independently random tokens. Nothing to cache.

And two run shapes:

- **Concurrency sweep:** `--max-concurrency` stepped through {1, 2, 4, 8, 16, 32, 64, 128}, with 60-second gaps between steps for clean Grafana time-windows.
- **Sustained burst:** `--max-concurrency 128` with thousands of prompts, pinned at the target concurrency for ~5 minutes uninterrupted. The headline numbers in this post come from these.

The harness — a thin bash wrapper that handles run-tagging, target-concurrency warmup before each measured run, and a timestamped manifest for Grafana correlation — is in the public repo.

## What the sweep doesn’t tell you

My first measurement was a concurrency sweep — the canonical way to characterize a serving system. C ∈ {1, 2, 4, 8, 16, 32, 64, 128}, ~1 minute per step, fixed prompt count per step. 

   | C | req/s | output tok/s | p95 TTFT | p95 TPOT | p95 ITL |
   |---|-------|--------------|----------|----------|---------|
   | 4 | 0.74 | 65 | 182 ms | 59 ms | 59 ms |
   | 16 | 2.55 | 233 | 222 ms | 61 ms | 67 ms |
   | 64 | 7.66 | 725 | 1,567 ms | 79 ms | 97 ms |
   | 128 | 11.06 | 1,065 | 2,731 ms | 125 ms | 168 ms |

That sweep said C=128 had p95 TTFT of **2,731 ms** with the cache-friendly workload.

When I re-ran C=128 as a *sustained 5-minute burst* with the same workload, p95 TTFT was **503 ms**.

A 5.4× difference for the same concurrency, on the same hardware, at the same workload mix. The sweep wasn't lying — it was answering a different question. *"How does the system perform during the first minute of load at C=128?"* is not the same question as *"How does the system perform at sustained C=128?"* The first measurement bakes in the cold-cache prefills that happen before the cache fills; the second amortizes them over enough requests that the steady state dominates the p95.

The lesson: sweep methodology is great for finding shape — where adding more concurrency stops increasing throughput, where latency starts to climb. It is the wrong tool for headline numbers. Headline numbers need sustained load.

## The numbers

Once the methodology was right, three sustained-load numbers were enough to answer "how much can it serve" honestly:

**~128 concurrent users at p95 TTFT 503 ms** — under chatbot-style load (long shared system prompt + short user query). At the same C=128 under independent random prompts, p95 TTFT is **1,843 ms** — 3.7× higher.

**~7,900 tokens/sec total throughput** — under cache-friendly load. ~4,300 tok/s under random. The user-perceived part — output tokens specifically — is 1,222/s vs 855/s. The "how fast does it write" number.

**~$0.07 per million total tokens** — under cache-friendly load. ~$0.13/M under random. Not a quality-equivalent comparison to GPT-4o or Claude Sonnet — Qwen 7B is much smaller — but a real number for *what does it cost to self-host a 7B-class model on commodity GPUs?*

## Why the cache-friendly version is so much better

Two reasons, both visible in the metrics.

**Prefill compute disappears.** A cache-friendly request is 384 tokens of shared system prompt plus 128 tokens of unique user input. With the prefix cached on the worker — because the prefix-aware router consistently routes the same prefix to the same worker — only the 128 unique tokens need to be prefilled. The other 384 are reused from KV cache. Prefill is the expensive prep stage that determines TTFT, so cutting it by 75% cuts TTFT by a similar factor.

**The GPU spends its time on decode, not prefill.** Decode is the user-perceived part — the actual token-by-token generation. Random-prompt workloads make the GPU spend a chunk of every request re-prefilling text it has seen many times before. Cache-friendly workloads let it spend that time generating new tokens for the *next* request instead.

At C=128, either workload keeps the GPUs continuously busy. The difference is what they are busy *doing* — and the cache-friendly version turns more of that work into tokens the user actually receives.

## What I'm not claiming

- **Not "this beats frontier APIs."** Different model class, different quality envelope.
- **Not "13 req/s is universal."** The numbers are workload-shaped. Random prompts → ~half the throughput, ~3× the TTFT.

## Where this goes next

Two open threads I haven't pulled on yet:

The first is comparing prefix-aware routing against round-robin routing on the *same* cache-friendly workload. Right now I've shown that *prefix caching* helps. To prove the *router specifically* earns its keep — versus relying on the workers' own caches with naive routing — I need an A/B with `routingLogic=roundrobin`. With round-robin, each prefix's cache state would be split across both workers, and each worker's hit rate should drop roughly in half. That's a single Helm value flip on the cluster.

The second is the cancellation-chain bug I noticed while running the sweeps: when a client disconnects, vLLM keeps generating tokens nobody will see. The router doesn't propagate cancellation to the engine. That's a real production-shape concern — abandoned requests still burn GPU time at sustained C=128 — but it doesn't show up in throughput numbers. It only shows up when you correlate gateway in-flight metrics against `finished_reason` on the workers.

Both are blog-post-shaped on their own. For now, this one ships.

