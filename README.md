# AI Security Mastery

**90-day learning path from ML fundamentals to production AI security systems**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/1125137519.svg)](https://doi.org/10.5281/zenodo.22131915)

**Status:** v1.0 complete — 18 chapters, 267 sections. v2.0 in progress (see [Roadmap](#roadmap--v20)).

Read online: [ruwgxo.com/book](https://ruwgxo.com/book)

---

## What This Is

A hands-on learning path for security professionals entering AI security. Security-first, implementation-focused, and built from production experience.

Not another ML course. This teaches the attack surface, the detection layer, and the production deployment — not just how transformers work.

---

## Quick Start

**Read the book:** [ruwgxo.com/book](https://ruwgxo.com/book) — rendered, searchable, no setup.

**Work the code:**

```bash
git clone https://github.com/ruwgxo/ai-security-mastery.git
cd ai-security-mastery
pip install -r requirements.txt
```

The book is authored as structured YAML under `book/`. Each chapter has an index (`chapter_NN_index.yaml`) and one file per section (`section_NN_MM_*.yaml`). Every implementation is inline in its section — copy it out and run it.

---

## Learning Path

### Part 1 — ML Foundations (Weeks 1–3)
- Chapter 1: Machine Learning Fundamentals
- Chapter 2: Deep Learning Basics
- Chapter 3: LLM Architecture
- Chapter 4: Modern LLM Internals

### Part 2 — AI Security Landscape (Weeks 4–6)
- Chapter 5: AI Threat Landscape
- Chapter 6: Prompt Injection Attacks
- Chapter 7: Jailbreak Techniques
- Chapter 8: Training Data Poisoning
- Chapter 9: Model Extraction & Stealing
- Chapter 10: Adversarial Machine Learning

### Part 3 — Detection Engineering (Weeks 7–9)
- Chapter 11: Detection Framework Design
- Chapter 12: ML-Based Detection Systems
- Chapter 13: Behavioral Analysis & Monitoring
- Chapter 14: Production Deployment

### Part 4 — Implementation (Weeks 10–12)
- Chapter 15: Building Production Detectors
- Chapter 16: SIEM Integration
- Chapter 17: Monitoring & Tuning
- Chapter 18: Real-World Case Studies

---

## Roadmap — v2.0

- **Agentic AI security**: tool-use injection, agent privilege escalation, MCP
  trust boundaries — the attack surface that emerged after v1 shipped
- **Running prototype**: a live detection endpoint built from the book's own
  chapters — read the theory, then query the system built from it
- **Readable-format generator**: a proper, reusable YAML-book site generator,
  replacing the interim build script behind the current site
- **Executable notebooks in the browser**: JupyterLite on the book site — no
  install, no server, no account
- **Continuous verification**: every embedded code block executed on every commit

Suggestions and corrections are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Tech Stack

Python 3.12+, NumPy, PyTorch, scikit-learn, Transformers, FastAPI, MLflow

---

## Scope

LLM security focus. Out of scope: CV security, RL security, federated learning attacks.

---

## Citation

If this book is useful in your research or writing, see [CITATION.cff](CITATION.cff)
for citation formats. A versioned DOI via Zenodo accompanies each release.

---

## License

MIT — learn freely, build openly.

---

**Author:** Raghav Dinesh | [github.com/ruwgxo](https://github.com/ruwgxo) | [ruwgxo.com](https://ruwgxo.com) | Working in security since 2012
