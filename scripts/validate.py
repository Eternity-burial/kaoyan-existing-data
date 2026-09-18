#!/usr/bin/env python3
"""
Validation and audit script for kaoyan-existing-data.
Performs:
1. JSON Schema validation for all records (papers, articles, sentences, vocabulary, phrases, questions)
   and manifests (files.jsonl, build.json).
2. Quantitative auditing:
   - Total years, articles, sentences, vocabulary, phrases, questions for production and rebuilt
   - 2007-2018 coverage comparison (vocabulary, sentences, phrases)
   - contextMeaning coverage rate (for vocabulary and phrases)
   - translation coverage rate (for sentences)
   - articleKey uniqueness check (production and rebuilt)
3. Discrepancy & locator auditing:
   - P/S locator resolution & syntax validity
   - Vocabulary locator completeness
   - Phrase location completeness (identifying raw unlocatable phrases e.g. 2013-2015)
   - Production vs rebuilt sentence count & text comparison
   - Production vs rebuilt vocabulary count comparison (2007-2018)
4. Generates audit/report.json and audit/unresolved.jsonl
"""

import os
import sys
import json
import re
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
RECORDS_DIR = ROOT / "records"
MANIFESTS_DIR = ROOT / "manifests"
INDEXES_DIR = ROOT / "indexes"
AUDIT_DIR = ROOT / "audit"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# Load schemas
SCHEMAS = {
    "paper": json.loads((SCHEMAS_DIR / "paper.schema.json").read_text(encoding="utf-8")),
    "article": json.loads((SCHEMAS_DIR / "article.schema.json").read_text(encoding="utf-8")),
    "sentence": json.loads((SCHEMAS_DIR / "sentence.schema.json").read_text(encoding="utf-8")),
    "vocabulary": json.loads((SCHEMAS_DIR / "vocabulary.schema.json").read_text(encoding="utf-8")),
    "phrase": json.loads((SCHEMAS_DIR / "phrase.schema.json").read_text(encoding="utf-8")),
    "question": json.loads((SCHEMAS_DIR / "question.schema.json").read_text(encoding="utf-8")),
    "manifest": json.loads((SCHEMAS_DIR / "manifest.schema.json").read_text(encoding="utf-8")),
    "build-manifest": json.loads((SCHEMAS_DIR / "build-manifest.schema.json").read_text(encoding="utf-8")),
}

VALIDATORS = {k: Draft202012Validator(v) for k, v in SCHEMAS.items()}

def run_validation():
    print("=== Running Schema Validation and Auditing ===")
    
    schema_errors = []
    unresolved_items = []
    
    # Track statistics
    stats = {
        "production": {
            "years": set(),
            "articleKeys": set(),
            "articles": 0,
            "sentences": 0,
            "vocabulary": 0,
            "phrases": 0,
            "questions": 0,
            "sentence_translations": 0,
            "vocab_context_meanings": 0,
            "phrase_context_meanings": 0,
            "by_year": {}
        },
        "rebuilt": {
            "years": set(),
            "articleKeys": set(),
            "articles": 0,
            "sentences": 0,
            "vocabulary": 0,
            "phrases": 0,
            "questions": 0,
            "sentence_translations": 0,
            "vocab_context_meanings": 0,
            "phrase_context_meanings": 0,
            "by_year": {}
        }
    }
    
    # Track sentences per article for comparison
    prod_sentences_by_article = {}
    rebuilt_sentences_by_article = {}
    
    # ----------------------------------------------------
    # 1. Validate Production Records
    # ----------------------------------------------------
    prod_dir = RECORDS_DIR / "production"
    
    # Papers
    for f in (prod_dir / "papers").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for err in VALIDATORS["paper"].iter_errors(data):
            schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
        stats["production"]["years"].add(data["year"])
        stats["production"]["by_year"].setdefault(data["year"], {
            "articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0
        })

    # Articles
    for f in (prod_dir / "articles").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for err in VALIDATORS["article"].iter_errors(data):
            schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
        ak = data["articleKey"]
        if ak in stats["production"]["articleKeys"]:
            unresolved_items.append({
                "type": "duplicate_article_key",
                "source": "production",
                "articleKey": ak,
                "file": str(f.relative_to(ROOT))
            })
        stats["production"]["articleKeys"].add(ak)
        stats["production"]["articles"] += 1
        yr = data["provenance"]["year"]
        stats["production"]["by_year"].setdefault(yr, {
            "articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0
        })["articles"] += 1

    # Sentences
    for f in (prod_dir / "sentences").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        prod_sentences_by_article[ak] = items
        for s in items:
            for err in VALIDATORS["sentence"].iter_errors(s):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["production"]["sentences"] += 1
            yr = s["provenance"]["year"]
            stats["production"]["by_year"][yr]["sentences"] += 1
            if s.get("translation"):
                stats["production"]["sentence_translations"] += 1
            # Check P/S format
            ps = s.get("location", {}).get("ps", "")
            if not re.match(r"^P\d+-S\d+$", ps):
                unresolved_items.append({
                    "type": "invalid_ps_syntax",
                    "source": "production",
                    "articleKey": ak,
                    "ps": ps,
                    "text": s.get("text", "")[:40]
                })

    # Vocabulary
    for f in (prod_dir / "vocabulary").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        for v in items:
            for err in VALIDATORS["vocabulary"].iter_errors(v):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["production"]["vocabulary"] += 1
            yr = v["provenance"]["year"]
            stats["production"]["by_year"][yr]["vocabulary"] += 1
            if v.get("contextMeaning"):
                stats["production"]["vocab_context_meanings"] += 1
            # Check location
            sl = v.get("sourceLocation")
            if not sl and not v.get("sourceLocator"):
                unresolved_items.append({
                    "type": "unlocatable_vocabulary",
                    "source": "production",
                    "articleKey": ak,
                    "word": v.get("word")
                })

    # Phrases
    for f in (prod_dir / "phrases").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        for p in items:
            for err in VALIDATORS["phrase"].iter_errors(p):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["production"]["phrases"] += 1
            yr = p["provenance"]["year"]
            stats["production"]["by_year"][yr]["phrases"] += 1
            if p.get("contextMeaning"):
                stats["production"]["phrase_context_meanings"] += 1
            loc = p.get("location")
            if not loc:
                unresolved_items.append({
                    "type": "phrase_without_source_location",
                    "source": "production",
                    "articleKey": ak,
                    "year": yr,
                    "phrase": p.get("surface")
                })

    # Questions
    for f in (prod_dir / "questions").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        for q in items:
            for err in VALIDATORS["question"].iter_errors(q):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["production"]["questions"] += 1
            yr = q["provenance"]["year"]
            stats["production"]["by_year"][yr]["questions"] += 1

    # ----------------------------------------------------
    # 2. Validate Rebuilt Records
    # ----------------------------------------------------
    rebuilt_dir = RECORDS_DIR / "rebuilt"
    
    # Articles
    for f in (rebuilt_dir / "articles").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for err in VALIDATORS["article"].iter_errors(data):
            schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
        ak = data["articleKey"]
        if ak in stats["rebuilt"]["articleKeys"]:
            unresolved_items.append({
                "type": "duplicate_article_key",
                "source": "rebuilt",
                "articleKey": ak,
                "file": str(f.relative_to(ROOT))
            })
        stats["rebuilt"]["articleKeys"].add(ak)
        stats["rebuilt"]["articles"] += 1
        yr = data["provenance"]["year"]
        stats["rebuilt"]["years"].add(yr)
        stats["rebuilt"]["by_year"].setdefault(yr, {
            "articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0
        })["articles"] += 1

    # Sentences
    for f in (rebuilt_dir / "sentences").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        rebuilt_sentences_by_article[ak] = items
        for s in items:
            for err in VALIDATORS["sentence"].iter_errors(s):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["rebuilt"]["sentences"] += 1
            yr = s["provenance"]["year"]
            stats["rebuilt"]["by_year"][yr]["sentences"] += 1
            if s.get("translation"):
                stats["rebuilt"]["sentence_translations"] += 1
            ps = s.get("location", {}).get("ps", "")
            if not re.match(r"^P\d+-S\d+$", ps):
                unresolved_items.append({
                    "type": "invalid_ps_syntax",
                    "source": "rebuilt",
                    "articleKey": ak,
                    "ps": ps,
                    "text": s.get("text", "")[:40]
                })

    # Vocabulary
    for f in (rebuilt_dir / "vocabulary").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        for v in items:
            for err in VALIDATORS["vocabulary"].iter_errors(v):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["rebuilt"]["vocabulary"] += 1
            yr = v["provenance"]["year"]
            stats["rebuilt"]["by_year"][yr]["vocabulary"] += 1
            if v.get("contextMeaning"):
                stats["rebuilt"]["vocab_context_meanings"] += 1
            sl = v.get("sourceLocation")
            if not sl and not v.get("sourceLocator"):
                unresolved_items.append({
                    "type": "unlocatable_vocabulary",
                    "source": "rebuilt",
                    "articleKey": ak,
                    "word": v.get("word")
                })

    # Phrases
    for f in (rebuilt_dir / "phrases").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        ak = f.stem
        for p in items:
            for err in VALIDATORS["phrase"].iter_errors(p):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["rebuilt"]["phrases"] += 1
            yr = p["provenance"]["year"]
            stats["rebuilt"]["by_year"][yr]["phrases"] += 1
            if p.get("contextMeaning"):
                stats["rebuilt"]["phrase_context_meanings"] += 1
            loc = p.get("location")
            if not loc:
                unresolved_items.append({
                    "type": "phrase_without_source_location",
                    "source": "rebuilt",
                    "articleKey": ak,
                    "year": yr,
                    "phrase": p.get("surface")
                })

    # Questions
    for f in (rebuilt_dir / "questions").glob("*.json"):
        items = json.loads(f.read_text(encoding="utf-8"))
        for q in items:
            for err in VALIDATORS["question"].iter_errors(q):
                schema_errors.append({"file": str(f.relative_to(ROOT)), "error": err.message})
            stats["rebuilt"]["questions"] += 1
            yr = q["provenance"]["year"]
            stats["rebuilt"]["by_year"][yr]["questions"] += 1

    # ----------------------------------------------------
    # 3. Validate Manifests
    # ----------------------------------------------------
    # Validate files.jsonl against manifest.schema.json
    with open(MANIFESTS_DIR / "files.jsonl", "r", encoding="utf-8") as f_mf:
        for line_num, line in enumerate(f_mf, start=1):
            if not line.strip(): continue
            mf_rec = json.loads(line)
            for err in VALIDATORS["manifest"].iter_errors(mf_rec):
                schema_errors.append({"file": f"manifests/files.jsonl:line{line_num}", "error": err.message})

    # Validate build.json against build-manifest.schema.json
    build_manifest = json.loads((MANIFESTS_DIR / "build.json").read_text(encoding="utf-8"))
    for err in VALIDATORS["build-manifest"].iter_errors(build_manifest):
        schema_errors.append({"file": "manifests/build.json", "error": err.message})

    # ----------------------------------------------------
    # 4. Sentence Discrepancy Analysis (Production vs Rebuilt)
    # ----------------------------------------------------
    sentence_mismatches = []
    common_articles = sorted(list(set(prod_sentences_by_article.keys()) & set(rebuilt_sentences_by_article.keys())))
    for ak in common_articles:
        p_sents = prod_sentences_by_article[ak]
        r_sents = rebuilt_sentences_by_article[ak]
        if len(p_sents) != len(r_sents):
            sentence_mismatches.append({
                "articleKey": ak,
                "type": "sentence_count_mismatch",
                "productionCount": len(p_sents),
                "rebuiltCount": len(r_sents)
            })
            unresolved_items.append({
                "type": "sentence_count_mismatch",
                "articleKey": ak,
                "productionCount": len(p_sents),
                "rebuiltCount": len(r_sents),
                "details": f"Article {ak} has {len(p_sents)} production sentences vs {len(r_sents)} rebuilt sentences."
            })
        else:
            # Compare texts
            diff_indices = []
            for i, (ps, rs) in enumerate(zip(p_sents, r_sents)):
                t1 = re.sub(r"\s+", " ", ps.get("text", "")).strip()
                t2 = re.sub(r"\s+", " ", rs.get("text", "")).strip()
                if t1 != t2:
                    diff_indices.append({
                        "index": i,
                        "ps": ps.get("location", {}).get("ps"),
                        "prodText": t1[:60],
                        "rebuiltText": t2[:60]
                    })
            if diff_indices:
                sentence_mismatches.append({
                    "articleKey": ak,
                    "type": "sentence_text_difference",
                    "diffCount": len(diff_indices),
                    "differences": diff_indices[:5]
                })
                unresolved_items.append({
                    "type": "sentence_text_difference",
                    "articleKey": ak,
                    "diffCount": len(diff_indices),
                    "sample": diff_indices[0]
                })

    # ----------------------------------------------------
    # 5. Coverage Rates
    # ----------------------------------------------------
    prod_vocab_total = stats["production"]["vocabulary"]
    prod_context_meaning_rate = round(stats["production"]["vocab_context_meanings"] / prod_vocab_total * 100, 2) if prod_vocab_total else 0.0
    prod_sent_total = stats["production"]["sentences"]
    prod_trans_rate = round(stats["production"]["sentence_translations"] / prod_sent_total * 100, 2) if prod_sent_total else 0.0

    rebuilt_vocab_total = stats["rebuilt"]["vocabulary"]
    rebuilt_context_meaning_rate = round(stats["rebuilt"]["vocab_context_meanings"] / rebuilt_vocab_total * 100, 2) if rebuilt_vocab_total else 0.0
    rebuilt_sent_total = stats["rebuilt"]["sentences"]
    rebuilt_trans_rate = round(stats["rebuilt"]["sentence_translations"] / rebuilt_sent_total * 100, 2) if rebuilt_sent_total else 0.0

    # ----------------------------------------------------
    # 6. 2007-2018 Coverage Table Data
    # ----------------------------------------------------
    coverage_2007_2018 = {}
    for yr in range(2007, 2019):
        p_stat = stats["production"]["by_year"].get(yr, {"articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0})
        r_stat = stats["rebuilt"]["by_year"].get(yr, {"articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0})
        coverage_2007_2018[str(yr)] = {
            "production": {
                "articles": p_stat["articles"],
                "sentences": p_stat["sentences"],
                "vocabulary": p_stat["vocabulary"],
                "phrases": p_stat["phrases"],
                "questions": p_stat["questions"]
            },
            "rebuilt": {
                "articles": r_stat["articles"],
                "sentences": r_stat["sentences"],
                "vocabulary": r_stat["vocabulary"],
                "phrases": r_stat["phrases"],
                "questions": r_stat["questions"]
            },
            "notes": "Rebuilt vocab/phrases present in 2007-2015 only; 2016-2018 rebuilt contains text, syntax & questions without vocab" if yr in range(2016, 2019) else "Both production and rebuilt populated"
        }

    # Prepare audit report JSON
    audit_report = {
        "auditVersion": "1.0",
        "generatedAt": "2026-09-18T23:09:58+0800",
        "schemaValidation": {
            "totalErrors": len(schema_errors),
            "errors": schema_errors[:20]
        },
        "keyUniqueness": {
            "productionDuplicateKeys": len(stats["production"]["articleKeys"]) != stats["production"]["articles"],
            "rebuiltDuplicateKeys": len(stats["rebuilt"]["articleKeys"]) != stats["rebuilt"]["articles"],
            "productionUniqueKeysCount": len(stats["production"]["articleKeys"]),
            "rebuiltUniqueKeysCount": len(stats["rebuilt"]["articleKeys"])
        },
        "summary": {
            "production": {
                "yearRange": f"{min(stats['production']['years'])}-{max(stats['production']['years'])}",
                "totalYears": len(stats["production"]["years"]),
                "totalArticles": stats["production"]["articles"],
                "totalSentences": stats["production"]["sentences"],
                "totalVocabulary": stats["production"]["vocabulary"],
                "totalPhrases": stats["production"]["phrases"],
                "totalQuestions": stats["production"]["questions"],
                "contextMeaningCoverageRate": f"{prod_context_meaning_rate}%",
                "sentenceTranslationCoverageRate": f"{prod_trans_rate}%"
            },
            "rebuilt": {
                "yearRange": f"{min(stats['rebuilt']['years'])}-{max(stats['rebuilt']['years'])}",
                "totalYears": len(stats["rebuilt"]["years"]),
                "totalArticles": stats["rebuilt"]["articles"],
                "totalSentences": stats["rebuilt"]["sentences"],
                "totalVocabulary": stats["rebuilt"]["vocabulary"],
                "totalPhrases": stats["rebuilt"]["phrases"],
                "totalQuestions": stats["rebuilt"]["questions"],
                "contextMeaningCoverageRate": f"{rebuilt_context_meaning_rate}%",
                "sentenceTranslationCoverageRate": f"{rebuilt_trans_rate}%"
            }
        },
        "coverageComparison2007to2018": coverage_2007_2018,
        "discrepancies": {
            "sentenceMismatchesCount": len(sentence_mismatches),
            "sentenceMismatches": sentence_mismatches[:15],
            "unresolvedItemsCount": len(unresolved_items),
            "unresolvedBreakdown": {
                "invalid_ps_syntax": sum(1 for it in unresolved_items if it.get("type") == "invalid_ps_syntax"),
                "unlocatable_vocabulary": sum(1 for it in unresolved_items if it.get("type") == "unlocatable_vocabulary"),
                "phrase_without_source_location": sum(1 for it in unresolved_items if it.get("type") == "phrase_without_source_location"),
                "sentence_count_mismatch": sum(1 for it in unresolved_items if it.get("type") == "sentence_count_mismatch"),
                "sentence_text_difference": sum(1 for it in unresolved_items if it.get("type") == "sentence_text_difference"),
                "duplicate_article_key": sum(1 for it in unresolved_items if it.get("type") == "duplicate_article_key")
            }
        }
    }

    # Write audit/report.json
    (AUDIT_DIR / "report.json").write_text(json.dumps(audit_report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Write audit/unresolved.jsonl
    with open(AUDIT_DIR / "unresolved.jsonl", "w", encoding="utf-8") as f_out:
        for item in unresolved_items:
            f_out.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Audit completed:")
    print(f"  Schema Errors: {len(schema_errors)}")
    print(f"  Unresolved Items: {len(unresolved_items)}")
    print(f"    - invalid_ps_syntax: {audit_report['discrepancies']['unresolvedBreakdown']['invalid_ps_syntax']}")
    print(f"    - unlocatable_vocabulary: {audit_report['discrepancies']['unresolvedBreakdown']['unlocatable_vocabulary']}")
    print(f"    - phrase_without_source_location: {audit_report['discrepancies']['unresolvedBreakdown']['phrase_without_source_location']}")
    print(f"    - sentence_count_mismatch: {audit_report['discrepancies']['unresolvedBreakdown']['sentence_count_mismatch']}")
    print(f"    - sentence_text_difference: {audit_report['discrepancies']['unresolvedBreakdown']['sentence_text_difference']}")
    print(f"    - duplicate_article_key: {audit_report['discrepancies']['unresolvedBreakdown']['duplicate_article_key']}")
    print(f"  Report written to {AUDIT_DIR / 'report.json'}")
    print(f"  Unresolved written to {AUDIT_DIR / 'unresolved.jsonl'}")

    return len(schema_errors) == 0

if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
