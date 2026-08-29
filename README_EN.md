# PaperLens — Self-hosted Plagiarism & AIGC Detection

<p align="center">
  <b>A one-stop, self-hosted paper checking platform: plagiarism detection + AI-generated content (AIGC) detection + web-wide verification + rewriting assistance</b><br/>
  FastAPI · React · SQLite · fully offline detection core
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license"/></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="python"/>
  <img src="https://img.shields.io/badge/react-18-61dafb.svg" alt="react"/>
</p>

<p align="center">
  English ｜ <a href="README.md">简体中文</a>
</p>

---

PaperLens brings the workflow of commercial platforms (CNKI / PaperPass / Turnitin / GPTZero)
onto your own machine. In the default local mode your document text never leaves the machine;
if you explicitly enable external engines (e.g. GPTZero) or web-wide verification, the
corresponding text or short query fragments are sent to those providers — the submit page
shows exactly who receives what before you run a check. See [README.md](README.md) for the
full data-flow table.

## Features

- **Plagiarism detection** — sentence-level n-gram fingerprinting with inverted-index recall and
  containment verification; character-level (Chinese) and word-level (English) granularity;
  automatic reference-section stripping.
- **Web-wide verification** — suspicious sentences are checked against OpenAlex / arXiv /
  Europe PMC (structured APIs that return abstracts — no scraping needed) with
  Bing / DuckDuckGo as fallback; hits are reported with source URL and snippet, plus a
  separate "web duplication rate".
- **OA corpus crawler** — grow your comparison library from four official open-access APIs
  (arXiv, OpenAlex incl. Chinese OA, DOAJ, Europe PMC) with polite fetching, title dedup,
  and live task progress.
- **AIGC detection (v2 ensemble)** — six statistical fingerprints of LLM text plus two
  smoothness signals from a corpus-backed trigram LM (inter-sentence burstiness and
  token-level surprisal variance); full-text, per-sentence, and paragraph-level scores with
  a feature radar.
- **Multi-engine comparison** — local engine + GPTZero / CopyLeaks (real API calls with your
  key) + a transformers model plugin (HC3-finetuned RoBERTa or your own checkpoints) +
  CNKI/Wanfang/VIP/Zhuque/Turnitin shown honestly as "no public API".
- **Rewriting assistance (dedup & humanize)** — locates matched and AI-suspect sentences,
  applies rule-based rewrites (synonym substitution, cliché replacement, connector thinning,
  long-sentence splitting) with per-edit rationales, then re-measures before/after.
- **CNKI-style reports** — full-text highlighting (red = library match, orange = web hit,
  purple = high AI suspicion), side-by-side fragment comparison, standalone HTML export.

## Quick start

```bash
bash start.sh          # http://localhost:8765
```

Python 3.10+ and Node 18+ required. On first launch, run a crawl from the
「语料采集 / Corpus Crawler」 page (e.g. 200 papers each from arXiv and OpenAlex, ~2 min)
to replace the built-in demo corpus with real OA papers.

## The AIGC method in brief

The detector follows the public evolution of the field — GPTZero's early
perplexity+burstiness, DetectGPT (ICLR'23), [Fast-DetectGPT](https://arxiv.org/abs/2310.05130)
(ICLR'24), [Binoculars](https://arxiv.org/abs/2401.12070) (ICML'24) — all built on the
observation that machine text is *more predictable and smoother* under a language model.

Our offline ensemble combines six statistical fingerprints (sentence-length uniformity,
cliché density, connector regularity, mid-range lexical diversity, punctuation monotony,
templated openers) with two LM smoothness signals from a trigram LM trained on your own
corpus. One notable calibration finding: **absolute perplexity is inverted in-domain** —
human academic papers score *lower* perplexity than AI text under a domain LM — so only
variance-shaped signals are used.

Measured contrast: strongly AI-styled Chinese ≈ 86%, English ≈ 95%, casual human writing
≈ 32%, formal copied excerpts ≈ 40%. As with every statistical detector, treat results as
screening signals and cross-check with other engines.

## Roadmap

- [x] Web-wide verification, OA crawler, transformers plugin slot
- [ ] Chinese SOTA detectors (NLPCC'25 Task1 / DetectRL-ZH systems) via `AIGC_MODEL_ZH`
- [ ] Multilingual detectors (RADAR, M4-RoBERTa) via the same plugin
- [ ] Official vendor AIGC APIs to replace statistical scoring where available
- [ ] LLM-backed rewriting adapter

Full methodology, architecture, and API reference: see [README.md](README.md) (Chinese).

## Disclaimer

For learning, research, and self-checking before submission. Results do not represent any
official institution's verdict; always defer to your institution's designated system.

## License

[MIT](LICENSE)
