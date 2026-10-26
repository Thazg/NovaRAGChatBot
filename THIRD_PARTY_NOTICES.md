# Third-party materials and attribution

The [MIT license](LICENSE) applies to Nova's project code. It does not relicense research papers, quoted evidence, external model weights, dependency code or third-party marks.

## Research corpus

The benchmark's [manifest](backend/evaluation/arxiv_corpus/manifest.json) records source titles, pinned arXiv versions and original URLs. [Checksums](backend/evaluation/arxiv_corpus/checksums.json) identify the downloaded PDF bytes. PDFs and extracted corpus files are not tracked in the current source tree; reproduction downloads them from their original source. Questions/reference answers are project-authored, while evidence spans quote the cited papers and retain their authors' rights.

The license links on the versioned arXiv pages were inspected on 2026-10-26:

| Paper and attribution | Version/source | License linked by arXiv |
| --- | --- | --- |
| Retrieval-Augmented Generation, Patrick Lewis et al. | [2005.11401v4](https://arxiv.org/abs/2005.11401v4) | [arXiv non-exclusive distribution](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) |
| Dense Passage Retrieval, Vladimir Karpukhin et al. | [2004.04906v3](https://arxiv.org/abs/2004.04906v3) | arXiv non-exclusive distribution |
| REALM, Kelvin Guu et al. | [2002.08909v1](https://arxiv.org/abs/2002.08909v1) | arXiv non-exclusive distribution |
| ColBERT, Omar Khattab and Matei Zaharia | [2004.12832v2](https://arxiv.org/abs/2004.12832v2) | arXiv non-exclusive distribution |
| HyDE, Luyu Gao et al. | [2212.10496v1](https://arxiv.org/abs/2212.10496v1) | arXiv non-exclusive distribution |
| Ragas, Shahul Es et al. | [2309.15217v2](https://arxiv.org/abs/2309.15217v2) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Self-RAG, Akari Asai et al. | [2310.11511v1](https://arxiv.org/abs/2310.11511v1) | CC BY 4.0 |
| Lost in the Middle, Nelson F. Liu et al. | [2307.03172v3](https://arxiv.org/abs/2307.03172v3) | arXiv non-exclusive distribution |
| Corrective RAG, Shi-Qi Yan et al. | [2401.15884v3](https://arxiv.org/abs/2401.15884v3) | arXiv non-exclusive distribution |
| RAPTOR, Parth Sarthi et al. | [2401.18059v1](https://arxiv.org/abs/2401.18059v1) | CC BY 4.0 |

arXiv's distribution license grants rights to arXiv; it is not a blanket third-party reuse license. [arXiv's license guidance](https://info.arxiv.org/help/license/index.html) also notes that versions can have different terms. Check original notices, permissions and applicable reuse terms before redistributing full text, evidence excerpts, derived corpora or older Git-history material. Attribution here does not establish permission for every redistribution. Project-generated reference answers summarize sources; they are not the papers' own claims of benchmark performance.

## Product screenshot

The [README login screenshot](frontend/e2e/portfolio-flow.spec.ts-snapshots/login-dark-chromium-win32.png) captures Nova's actual login component in Chromium/Windows with controlled API fixtures. It contains no research-paper excerpt, uploaded document or model answer. [Capture context](docs/assets/README.md) explains its scope; it is not a generated mockup or evidence of live-service availability.

## Icons, dependencies and model weights

- The inline GitHub mark comes from [Primer Octicons](https://github.com/primer/octicons), copyright 2026 GitHub Inc., under [MIT](https://github.com/primer/octicons/blob/main/LICENSE). The complete upstream notice is retained in [GitHubMark.tsx](frontend/src/components/brand/GitHubMark.tsx). The mark identifies a repository link and does not imply endorsement.
- JavaScript and Python dependencies retain their package licenses and notices. See the [npm lockfile](frontend/package-lock.json), package LICENSE files and Python wheel metadata. Preserve required notices when bundling/distributing them; the project's MIT badge is not a dependency-license audit certificate.
- The PostgreSQL driver `psycopg` has its own LGPL-3.0-only package license; preserve its [upstream terms](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt), including the terms of bundled binary libraries when distributing wheels/containers. It is not covered by Nova’s MIT license.
- Model weights are not bundled. Ollama/Groq and optional embedding/reranker experiments use separately obtained models/services with their own model licenses and provider terms. Check those exact versions before redistribution or use.
