# Kaoyan Existing Data Source Dataset (`kaoyan-existing-data`)

An immutable, read-only, traceable source dataset extracting and preserving raw existing data from **Kaoyan English One (英语一)** across 29 examination years (1998–2026) and 19 rebuilt years (2007–2025).

This repository serves as the authoritative source layer for subsequent Lexicon Fusion pipelines. It strictly adheres to source truth without performing canonical fusion, deduplication, or interpretation.

---

## 1. Directory Structure

```text
kaoyan-existing-data/
├── README.md                          # Documentation and specifications
├── schemas/                           # JSON Schema definitions (Draft-07 / 2020-12)
│   ├── paper.schema.json              # Paper container schema
│   ├── article.schema.json            # Article record schema
│   ├── sentence.schema.json           # Sentence record schema (canonical P/S + sourceLocator)
│   ├── vocabulary.schema.json         # Vocabulary record schema (isolated from phrases)
│   ├── phrase.schema.json             # Phrase & collocation record schema
│   ├── question.schema.json           # Reading comprehension question schema
│   ├── manifest.schema.json           # File manifest record schema (files.jsonl)
│   └── build-manifest.schema.json     # Overall build manifest schema (build.json)
├── records/                           # Extracted raw records partitioned by layer & entity
│   ├── production/                    # Production layer extracted from 题库/英语/data_YYYY.js (1998-2026)
│   │   ├── papers/                    # 29 year-level paper records
│   │   ├── articles/                  # 120 article metadata records
│   │   ├── sentences/                 # 120 sentence files (2,062 total sentences)
│   │   ├── vocabulary/                # 120 vocabulary files (9,030 total words)
│   │   ├── phrases/                   # 120 phrase files (1,095 total phrases)
│   │   └── questions/                 # 120 question files (580 total questions)
│   └── rebuilt/                       # Rebuilt layer extracted from rebuilt_data/single_texts/ (2007-2025)
│       ├── articles/                  # 76 article metadata records
│       ├── sentences/                 # 76 sentence files (1,255 total sentences)
│       ├── vocabulary/                # 76 vocabulary files (1,656 total words, 2007-2015)
│       ├── phrases/                   # 76 phrase files (1,095 total phrases, 2007-2015)
│       └── questions/                 # 76 question files (380 total questions)
├── manifests/                         # Traceability and checksum manifests
│   ├── build.json                     # Aggregate dataset build manifest
│   └── files.jsonl                    # Per-source-file record count and sha256 checksums
├── indexes/                           # Fast lookup indexes
│   ├── articles.json                  # Article key index
│   ├── sentences.json                 # Sentence locator index (articleKey#P{p}-S{s})
│   ├── vocabulary.json                # Lowercased word occurrence index
│   └── phrases.json                   # Lowercased phrase occurrence index
├── audit/                             # Quality control and discrepancy reports
│   ├── report.json                    # Quantitative audit summary and coverage tables
│   └── unresolved.jsonl               # Line-by-line log of anomalies and missing source locators
└── scripts/                           # Reproducible build and validation scripts
    ├── extract.py                     # Extraction pipeline from production JS and rebuilt JSON
    └── validate.py                    # JSON schema validation and audit report generator
```

---

## 2. Core Architectural Principles

### 2.1 Source Layer Separation (Production vs Rebuilt)
- Both layers are extracted and retained independently under `records/production/` and `records/rebuilt/`.
- Neither layer overwrites the other. For common articles (2007–2025), both versions are preserved side-by-side to allow downstream fusion pipelines to evaluate enrichments and diffs.

### 2.2 Physical Separation of Vocabulary and Phrases
- In strict adherence to schema boundaries, lexical items (`vocabulary/`) and multi-word expressions (`phrases/`) are stored in distinct directories.
- No phrases are placed in vocabulary records.

### 2.3 Canonical P/S Locators & Source Locator Fidelity
- Sentences generate a canonical paragraph/sentence locator: `P{paragraph}-S{sentenceWithinParagraph}` (e.g. `P1-S1`, `P2-S1`).
- All original indices (`sentenceIndex`, `sIndex`, `id`, `pIndex`) are preserved untouched inside `sourceLocator`. For example, in 2014 where production sentences carried a continuous article-wide `sentenceIndex`, the paragraph-local `P{p}-S{s}` was computed while preserving `sourceLocator: {"sentenceIndex": ...}`.

### 2.4 Strict Raw Field Preservation
- `frequencyRating`: Retained exactly as formatted in the raw data (e.g. `★★★`, `★★`); NEVER interpreted as Lazynote frequency.
- `isSelfAnnotated`: Retained as raw boolean or null; NEVER interpreted as personalPdf.
- `contextMeaning`, `examMeaning`, `collocationOrDerivation`: Full fidelity preservation.
- Questions, options, target sentences, methodology reviews, and reflections are preserved completely.

### 2.5 Zero Hallucination Audit Policy
- No missing fields or locators are guessed, interpolated, or generated with LLMs.
- Items lacking locators in the source material (e.g. 2013–2015 phrases lacking line coordinates) are recorded into `audit/unresolved.jsonl`.

---

## 3. Dataset Statistics Summary

| Metric | Production Layer (`data_YYYY.js`) | Rebuilt Layer (`rebuilt_data/single_texts/`) |
| :--- | :--- | :--- |
| **Year Range** | 1998–2026 (29 years) | 2007–2025 (19 years) |
| **Total Articles** | 120 | 76 |
| **Total Sentences** | 2,062 | 1,255 |
| **Total Vocabulary** | 9,030 | 1,656 (2007–2015) |
| **Total Phrases** | 1,095 (2007–2015) | 1,095 (2007–2015) |
| **Total Questions** | 580 | 380 |
| **contextMeaning Coverage** | 100.0% | 100.0% |
| **Sentence Translation Coverage** | 100.0% | 100.0% |
| **Duplicate Article Keys** | 0 | 0 |
| **Schema Validation Errors** | 0 | 0 |

---

## 4. 2007–2018 Coverage Comparison

| Year | Articles (Prod / Reb) | Sentences (Prod / Reb) | Vocabulary (Prod / Reb) | Phrases (Prod / Reb) | Questions (Prod / Reb) | Coverage Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **2007** | 4 / 4 | 65 / 65 | 410 / 269 | 250 / 250 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2008** | 4 / 4 | 86 / 86 | 573 / 407 | 236 / 236 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2009** | 4 / 4 | 76 / 76 | 547 / 413 | 226 / 226 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2010** | 4 / 4 | 60 / 60 | 237 / 62 | 53 / 53 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2011** | 4 / 4 | 75 / 75 | 286 / 81 | 58 / 58 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2012** | 4 / 4 | 94 / 94 | 275 / 108 | 68 / 68 | 20 / 20 | Both populated; prod vocabulary contains additional words |
| **2013** | 4 / 4 | 80 / 80 | 263 / 101 | 60 / 60 | 20 / 20 | Phrases lack line locators in raw data (recorded to audit) |
| **2014** | 4 / 4 | 84 / 84 | 285 / 105 | 64 / 64 | 20 / 20 | Phrases lack line locators in raw data (recorded to audit) |
| **2015** | 4 / 4 | 76 / 76 | 286 / 110 | 80 / 80 | 20 / 20 | Phrases lack line locators in raw data (recorded to audit) |
| **2016** | 4 / 4 | 87 / 87 | 135 / 0 | 0 / 0 | 20 / 20 | Rebuilt has syntax & questions only; vocab in prod only |
| **2017** | 4 / 4 | 80 / 80 | 137 / 0 | 0 / 0 | 20 / 20 | Rebuilt has syntax & questions only; vocab in prod only |
| **2018** | 4 / 4 | 85 / 85 | 137 / 0 | 0 / 0 | 20 / 20 | Rebuilt has syntax & questions only; vocab in prod only |

---

## 5. Reproduction & Verification

To reproduce the extraction and validate the entire dataset against schemas and audit rules:

```powershell
# 1. Run extraction from production and rebuilt raw datasets
python scripts/extract.py

# 2. Run schema validation and quality auditing
python scripts/validate.py
```
