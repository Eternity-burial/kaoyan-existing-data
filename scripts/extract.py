# -*- coding: utf-8 -*-
"""
Kaoyan Existing Data Extractor
Extracts production data (1998-2026) and rebuilt data (2007-2025)
into kaoyan-existing-data records, indexes, and manifests.
"""
import os, sys, glob, json, hashlib, datetime, time, re
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(BASE_DIR)) # D:\tj\822\考研题库
PROD_DIR = os.path.join(REPO_ROOT, '题库', '英语')
REBUILT_DIR = os.path.join(REPO_ROOT, 'rebuilt_data', 'single_texts')

RECORDS_DIR = os.path.join(BASE_DIR, 'records')
MANIFESTS_DIR = os.path.join(BASE_DIR, 'manifests')
INDEXES_DIR = os.path.join(BASE_DIR, 'indexes')
AUDIT_DIR = os.path.join(BASE_DIR, 'audit')

def sha256_file(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk: break
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"

def now_iso():
    return datetime.datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')

def extract_production_paper(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    pos = content.find('window.ENGLISH_DATA[')
    if pos == -1:
        raise ValueError(f"window.ENGLISH_DATA not found in {file_path}")
    eq_pos = content.find('=', pos)
    b_pos = content.find('{', eq_pos)
    r_pos = content.rfind('}')
    if b_pos == -1 or r_pos == -1:
        raise ValueError(f"JSON braces not found in {file_path}")
    
    data = json.loads(content[b_pos:r_pos+1])
    return data

def main():
    t0 = time.time()
    print("=== Starting Kaoyan Existing Data Extraction ===")
    
    # Ensure dirs
    for layer in ['production', 'rebuilt']:
        for cat in ['articles', 'sentences', 'vocabulary', 'phrases', 'questions']:
            os.makedirs(os.path.join(RECORDS_DIR, layer, cat), exist_ok=True)
    os.makedirs(os.path.join(RECORDS_DIR, 'production', 'papers'), exist_ok=True)
    os.makedirs(MANIFESTS_DIR, exist_ok=True)
    os.makedirs(INDEXES_DIR, exist_ok=True)
    os.makedirs(AUDIT_DIR, exist_ok=True)
    
    extracted_at = now_iso()
    
    files_manifest = []
    
    # Global index accumulators
    index_articles = {}
    index_sentences = defaultdict(list)
    index_vocabulary = defaultdict(list)
    index_phrases = defaultdict(list)
    
    total_stats = {
        "production": defaultdict(int),
        "rebuilt": defaultdict(int)
    }
    
    # ----------------------------------------------------
    # 1. Process Production Data (1998-2026)
    # ----------------------------------------------------
    print("1. Processing Production Layer (1998-2026)...")
    prod_files = sorted(glob.glob(os.path.join(PROD_DIR, 'data_*.js')))
    
    for pf in prod_files:
        fn = os.path.basename(pf)
        m = re.search(r'data_(\d{4})\.js', fn)
        if not m: continue
        year = int(m.group(1))
        content_hash = sha256_file(pf)
        rel_file = os.path.relpath(pf, REPO_ROOT).replace('\\', '/')
        
        try:
            data = extract_production_paper(pf)
        except Exception as e:
            print(f"Error parsing {fn}: {e}")
            files_manifest.append({
                "sourceFile": rel_file,
                "sourceLayer": "production",
                "year": year,
                "status": "failed",
                "contentHash": content_hash,
                "recordsProduced": {"articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0}
            })
            continue
        
        texts = data.get('texts', [])
        paper_key = f"ky-en1-{year}"
        track = "legacy" if year <= 2009 else "englishOne"
        
        article_keys_for_paper = []
        prod_art_count = 0
        prod_sent_count = 0
        prod_vocab_count = 0
        prod_phrase_count = 0
        prod_q_count = 0
        
        for t_idx, t in enumerate(texts, start=1):
            num = t.get('number') or t_idx
            article_key = f"ky-en1-{year}-r-t{num}"
            article_keys_for_paper.append(article_key)
            prod_art_count += 1
            
            # --- Sentences Extraction ---
            paras = t.get('paragraphs') or t.get('textAnalysis', {}).get('paragraphs', [])
            art_sentences = []
            
            for p_idx, para in enumerate(paras, start=1):
                raw_sentences = para.get('sentences', [])
                for s_idx, s in enumerate(raw_sentences, start=1):
                    canonical_ps = f"P{p_idx}-S{s_idx}"
                    
                    # Source locator preservation
                    source_locator = {}
                    for loc_key in ['sIndex', 'sentenceIndex', 'id', 'sid', 'order']:
                        if loc_key in s:
                            source_locator[loc_key] = s[loc_key]
                    if 'pIndex' in para:
                        source_locator['pIndex'] = para['pIndex']
                    
                    text_en = s.get('text') or s.get('en') or s.get('english') or ""
                    trans_zh = s.get('translation') or s.get('zh') or s.get('chinese')
                    syntax = s.get('syntaxAnalysis')
                    
                    # Collect raw fields
                    known_keys = {'text', 'en', 'english', 'translation', 'zh', 'chinese', 'syntaxAnalysis', 'sIndex', 'sentenceIndex', 'id', 'sid', 'order', 'vocab', 'vocabulary'}
                    raw_fields = {k: v for k, v in s.items() if k not in known_keys}
                    
                    sent_rec = {
                        "schemaVersion": "kaoyan-existing-sentence-1.0",
                        "source": "production",
                        "articleKey": article_key,
                        "location": {
                            "paragraph": p_idx,
                            "sentence": s_idx,
                            "ps": canonical_ps
                        },
                        "sourceLocator": source_locator,
                        "text": text_en,
                        "translation": trans_zh,
                        "syntaxAnalysis": syntax,
                        "rawFields": raw_fields,
                        "provenance": {
                            "sourceLayer": "production",
                            "sourceFile": rel_file,
                            "year": year,
                            "articleKey": article_key,
                            "extractedAt": extracted_at,
                            "contentHash": content_hash
                        }
                    }
                    art_sentences.append(sent_rec)
                    prod_sent_count += 1
                    
                    # Index sentence
                    index_sentences[f"{article_key}#{canonical_ps}"].append({
                        "source": "production",
                        "articleKey": article_key,
                        "ps": canonical_ps,
                        "text": text_en,
                        "translation": trans_zh
                    })
            
            # --- Vocabulary Extraction ---
            art_vocab = []
            # Check text-level vocabulary (2007-2015)
            if 'vocabulary' in t and isinstance(t['vocabulary'], list):
                for v in t['vocabulary']:
                    word_str = v.get('word', '').strip()
                    if not word_str: continue
                    known_v = {'word', 'surface', 'ipa', 'pos', 'location', 'contextMeaning', 'meaning', 'examMeaning', 'collocationOrDerivation', 'frequencyRating', 'isSelfAnnotated'}
                    v_raw = {k: val for k, val in v.items() if k not in known_v}
                    
                    v_rec = {
                        "schemaVersion": "kaoyan-existing-vocabulary-1.0",
                        "source": "production",
                        "articleKey": article_key,
                        "surface": v.get('surface') or word_str,
                        "word": word_str,
                        "ipa": v.get('ipa'),
                        "pos": v.get('pos'),
                        "sourceLocation": v.get('location'),
                        "contextMeaning": v.get('contextMeaning') or v.get('meaning'),
                        "examMeaning": v.get('examMeaning'),
                        "collocationOrDerivation": v.get('collocationOrDerivation'),
                        "frequencyRating": v.get('frequencyRating'),
                        "isSelfAnnotated": v.get('isSelfAnnotated'),
                        "rawFields": v_raw,
                        "provenance": {
                            "sourceLayer": "production",
                            "sourceFile": rel_file,
                            "year": year,
                            "articleKey": article_key,
                            "extractedAt": extracted_at,
                            "contentHash": content_hash
                        }
                    }
                    art_vocab.append(v_rec)
                    prod_vocab_count += 1
                    
                    index_vocabulary[word_str.lower()].append({
                        "source": "production",
                        "articleKey": article_key,
                        "word": word_str,
                        "location": v.get('location'),
                        "contextMeaning": v.get('contextMeaning') or v.get('meaning')
                    })
            
            # Check sentence-level vocabulary (1998-2006, 2016-2026)
            for p_idx, para in enumerate(paras, start=1):
                for s_idx, s in enumerate(para.get('sentences', []), start=1):
                    canonical_ps = f"P{p_idx}-S{s_idx}"
                    s_vocab = s.get('vocab') or s.get('vocabulary')
                    if s_vocab and isinstance(s_vocab, list):
                        for v in s_vocab:
                            word_str = v.get('word', '').strip()
                            if not word_str: continue
                            known_v = {'word', 'surface', 'ipa', 'pos', 'meaning', 'contextMeaning', 'examMeaning', 'collocationOrDerivation', 'frequencyRating', 'isSelfAnnotated'}
                            v_raw = {k: val for k, val in v.items() if k not in known_v}
                            
                            v_rec = {
                                "schemaVersion": "kaoyan-existing-vocabulary-1.0",
                                "source": "production",
                                "articleKey": article_key,
                                "surface": v.get('surface') or word_str,
                                "word": word_str,
                                "ipa": v.get('ipa'),
                                "pos": v.get('pos'),
                                "sourceLocation": canonical_ps,
                                "contextMeaning": v.get('meaning') or v.get('contextMeaning'),
                                "examMeaning": v.get('examMeaning'),
                                "collocationOrDerivation": v.get('collocationOrDerivation'),
                                "frequencyRating": v.get('frequencyRating'),
                                "isSelfAnnotated": v.get('isSelfAnnotated'),
                                "rawFields": v_raw,
                                "provenance": {
                                    "sourceLayer": "production",
                                    "sourceFile": rel_file,
                                    "year": year,
                                    "articleKey": article_key,
                                    "extractedAt": extracted_at,
                                    "contentHash": content_hash
                                }
                            }
                            art_vocab.append(v_rec)
                            prod_vocab_count += 1
                            
                            index_vocabulary[word_str.lower()].append({
                                "source": "production",
                                "articleKey": article_key,
                                "word": word_str,
                                "location": canonical_ps,
                                "contextMeaning": v.get('meaning') or v.get('contextMeaning')
                            })
            
            # --- Phrases Extraction ---
            art_phrases = []
            if 'phrasesAndCollocations' in t and isinstance(t['phrasesAndCollocations'], list):
                for ph in t['phrasesAndCollocations']:
                    ph_str = (ph.get('phrase') or ph.get('collocation') or ph.get('surface') or '').strip()
                    if not ph_str: continue
                    known_ph = {'phrase', 'collocation', 'surface', 'location', 'meaning', 'contextMeaning'}
                    ph_raw = {k: val for k, val in ph.items() if k not in known_ph}
                    
                    loc = ph.get('location')
                    if not loc and isinstance(ph.get('collocationNotes'), str) and ph['collocationNotes'].startswith('位置:'):
                        loc = ph['collocationNotes'].split('位置:', 1)[1].strip()
                    
                    ph_rec = {
                        "schemaVersion": "kaoyan-existing-phrase-1.0",
                        "source": "production",
                        "articleKey": article_key,
                        "surface": ph_str,
                        "location": loc,
                        "contextMeaning": ph.get('meaning') or ph.get('contextMeaning'),
                        "rawFields": ph_raw,
                        "provenance": {
                            "sourceLayer": "production",
                            "sourceFile": rel_file,
                            "year": year,
                            "articleKey": article_key,
                            "extractedAt": extracted_at,
                            "contentHash": content_hash
                        }
                    }
                    art_phrases.append(ph_rec)
                    prod_phrase_count += 1
                    
                    index_phrases[ph_str.lower()].append({
                        "source": "production",
                        "articleKey": article_key,
                        "surface": ph_str,
                        "location": ph.get('location'),
                        "contextMeaning": ph.get('meaning') or ph.get('contextMeaning')
                    })
            
            # --- Questions Extraction ---
            art_questions = []
            for q_idx, q in enumerate(t.get('questions', []), start=1):
                qi = q.get('qIndex') or q_idx
                stem = q.get('stem') or q.get('questionText') or ""
                ans = q.get('officialAnswer') or q.get('answer') or ""
                known_q = {'qIndex', 'stem', 'questionText', 'officialAnswer', 'answer', 'stemTranslation', 'options', 'standardType', 'type', 'typeDisplayName', 'targetSentences', 'verbatimEvidence', 'synonymMapping', 'methodologyReview', 'presetReflection', 'tangchiModel', 'paperVariants'}
                q_raw = {k: val for k, val in q.items() if k not in known_q}
                
                q_rec = {
                    "schemaVersion": "kaoyan-existing-question-1.0",
                    "source": "production",
                    "articleKey": article_key,
                    "qIndex": qi,
                    "questionNumber": q.get('number') or qi,
                    "stem": stem,
                    "stemTranslation": q.get('stemTranslation'),
                    "options": q.get('options', {}),
                    "officialAnswer": ans,
                    "standardType": q.get('standardType'),
                    "type": q.get('type') or q.get('typeDisplayName'),
                    "targetSentences": q.get('targetSentences'),
                    "verbatimEvidence": q.get('verbatimEvidence'),
                    "synonymMapping": q.get('synonymMapping'),
                    "methodologyReview": q.get('methodologyReview') or q.get('presetReflection') or q.get('tangchiModel'),
                    "paperVariants": q.get('paperVariants'),
                    "rawFields": q_raw,
                    "provenance": {
                        "sourceLayer": "production",
                        "sourceFile": rel_file,
                        "year": year,
                        "articleKey": article_key,
                        "extractedAt": extracted_at,
                        "contentHash": content_hash
                    }
                }
                art_questions.append(q_rec)
                prod_q_count += 1
            
            # --- Article Record ---
            known_art = {'id', 'number', 'title', 'chineseTitle', 'topic', 'topicDomain', 'subTopic', 'overview', 'wordCount', 'readingTimeEstimate', 'difficultyRating', 'sourcePublication', 'backgroundKnowledgeCapsule', 'topicVocabularyCapsule', 'nuancesAndConfusions', 'paragraphs', 'textAnalysis', 'vocabulary', 'phrasesAndCollocations', 'questions', 'syntax_analysis'}
            art_raw = {k: val for k, val in t.items() if k not in known_art}
            
            capsules = {}
            for cap_key in ['backgroundKnowledgeCapsule', 'topicVocabularyCapsule', 'nuancesAndConfusions', 'syntax_analysis']:
                if cap_key in t:
                    capsules[cap_key] = t[cap_key]
            
            art_rec = {
                "schemaVersion": "kaoyan-existing-article-1.0",
                "source": "production",
                "articleKey": article_key,
                "year": year,
                "textNumber": num,
                "title": t.get('title', ''),
                "chineseTitle": t.get('chineseTitle'),
                "topic": t.get('topic'),
                "topicDomain": t.get('topicDomain'),
                "subTopic": t.get('subTopic'),
                "overview": t.get('overview'),
                "wordCount": t.get('wordCount'),
                "readingTimeEstimate": t.get('readingTimeEstimate'),
                "difficultyRating": t.get('difficultyRating'),
                "sourcePublication": t.get('sourcePublication'),
                "paragraphCount": len(paras),
                "sentenceCount": len(art_sentences),
                "vocabularyCount": len(art_vocab),
                "phraseCount": len(art_phrases),
                "questionCount": len(art_questions),
                "capsules": capsules,
                "rawFields": art_raw,
                "provenance": {
                    "sourceLayer": "production",
                    "sourceFile": rel_file,
                    "year": year,
                    "articleKey": article_key,
                    "extractedAt": extracted_at,
                    "contentHash": content_hash
                }
            }
            
            # Write article records
            with open(os.path.join(RECORDS_DIR, 'production', 'articles', f"{article_key}.json"), 'w', encoding='utf-8') as f:
                json.dump(art_rec, f, ensure_ascii=False, indent=2)
            with open(os.path.join(RECORDS_DIR, 'production', 'sentences', f"{article_key}.json"), 'w', encoding='utf-8') as f:
                json.dump(art_sentences, f, ensure_ascii=False, indent=2)
            with open(os.path.join(RECORDS_DIR, 'production', 'vocabulary', f"{article_key}.json"), 'w', encoding='utf-8') as f:
                json.dump(art_vocab, f, ensure_ascii=False, indent=2)
            with open(os.path.join(RECORDS_DIR, 'production', 'phrases', f"{article_key}.json"), 'w', encoding='utf-8') as f:
                json.dump(art_phrases, f, ensure_ascii=False, indent=2)
            with open(os.path.join(RECORDS_DIR, 'production', 'questions', f"{article_key}.json"), 'w', encoding='utf-8') as f:
                json.dump(art_questions, f, ensure_ascii=False, indent=2)
            
            # Article index
            if article_key not in index_articles:
                index_articles[article_key] = {
                    "articleKey": article_key,
                    "year": year,
                    "textNumber": num,
                    "title": t.get('title', ''),
                    "sources": ["production"],
                    "production": {
                        "sentenceCount": len(art_sentences),
                        "vocabularyCount": len(art_vocab),
                        "phraseCount": len(art_phrases),
                        "questionCount": len(art_questions)
                    }
                }
            else:
                index_articles[article_key]["sources"].append("production")
                index_articles[article_key]["production"] = {
                    "sentenceCount": len(art_sentences),
                    "vocabularyCount": len(art_vocab),
                    "phraseCount": len(art_phrases),
                    "questionCount": len(art_questions)
                }
        
        # --- Paper Record ---
        paper_raw = {k: v for k, v in data.items() if k not in {'year', 'subject', 'title', 'texts'}}
        paper_rec = {
            "schemaVersion": "kaoyan-existing-paper-1.0",
            "source": "production",
            "paperKey": paper_key,
            "exam": "kaoyan",
            "track": track,
            "year": year,
            "title": data.get('title', f"{year}考研英语(一)真题"),
            "subject": data.get('subject', '英语(一)'),
            "articleKeys": article_keys_for_paper,
            "rawFields": paper_raw,
            "provenance": {
                "sourceLayer": "production",
                "sourceFile": rel_file,
                "year": year,
                "extractedAt": extracted_at,
                "contentHash": content_hash
            }
        }
        with open(os.path.join(RECORDS_DIR, 'production', 'papers', f"{paper_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(paper_rec, f, ensure_ascii=False, indent=2)
        
        files_manifest.append({
            "sourceFile": rel_file,
            "sourceLayer": "production",
            "year": year,
            "status": "parsed",
            "contentHash": content_hash,
            "recordsProduced": {
                "articles": prod_art_count,
                "sentences": prod_sent_count,
                "vocabulary": prod_vocab_count,
                "phrases": prod_phrase_count,
                "questions": prod_q_count
            }
        })
        
        total_stats["production"]["papers"] += 1
        total_stats["production"]["articles"] += prod_art_count
        total_stats["production"]["sentences"] += prod_sent_count
        total_stats["production"]["vocabulary"] += prod_vocab_count
        total_stats["production"]["phrases"] += prod_phrase_count
        total_stats["production"]["questions"] += prod_q_count
    
    print(f"  Production stats: {dict(total_stats['production'])}")
    
    # ----------------------------------------------------
    # 2. Process Rebuilt Data (single_texts, 2007-2025)
    # ----------------------------------------------------
    print("2. Processing Rebuilt Layer (2007-2025 single_texts)...")
    rebuilt_files = sorted(glob.glob(os.path.join(REBUILT_DIR, 'text_*.json')))
    
    for rf in rebuilt_files:
        fn = os.path.basename(rf)
        m = re.search(r'text_(\d{4})_t(\d+)\.json', fn)
        if not m: continue
        year = int(m.group(1))
        num = int(m.group(2))
        article_key = f"ky-en1-{year}-r-t{num}"
        content_hash = sha256_file(rf)
        rel_file = os.path.relpath(rf, REPO_ROOT).replace('\\', '/')
        
        try:
            t = json.load(open(rf, 'r', encoding='utf-8', errors='replace'))
        except Exception as e:
            print(f"Error parsing {fn}: {e}")
            files_manifest.append({
                "sourceFile": rel_file,
                "sourceLayer": "rebuilt",
                "year": year,
                "status": "failed",
                "contentHash": content_hash,
                "recordsProduced": {"articles": 0, "sentences": 0, "vocabulary": 0, "phrases": 0, "questions": 0}
            })
            continue
        
        # --- Sentences Extraction ---
        paras = t.get('paragraphs') or t.get('textAnalysis', {}).get('paragraphs', [])
        reb_sentences = []
        for p_idx, para in enumerate(paras, start=1):
            raw_sentences = para.get('sentences', [])
            for s_idx, s in enumerate(raw_sentences, start=1):
                canonical_ps = f"P{p_idx}-S{s_idx}"
                source_locator = {}
                for loc_key in ['sIndex', 'sentenceIndex', 'id', 'sid', 'order']:
                    if loc_key in s:
                        source_locator[loc_key] = s[loc_key]
                if 'pIndex' in para:
                    source_locator['pIndex'] = para['pIndex']
                
                text_en = s.get('text') or s.get('en') or s.get('english') or ""
                trans_zh = s.get('translation') or s.get('zh') or s.get('chinese')
                syntax = s.get('syntaxAnalysis')
                
                known_keys = {'text', 'en', 'english', 'translation', 'zh', 'chinese', 'syntaxAnalysis', 'sIndex', 'sentenceIndex', 'id', 'sid', 'order', 'vocab', 'vocabulary'}
                raw_fields = {k: v for k, v in s.items() if k not in known_keys}
                
                sent_rec = {
                    "schemaVersion": "kaoyan-existing-sentence-1.0",
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "location": {
                        "paragraph": p_idx,
                        "sentence": s_idx,
                        "ps": canonical_ps
                    },
                    "sourceLocator": source_locator,
                    "text": text_en,
                    "translation": trans_zh,
                    "syntaxAnalysis": syntax,
                    "rawFields": raw_fields,
                    "provenance": {
                        "sourceLayer": "rebuilt",
                        "sourceFile": rel_file,
                        "year": year,
                        "articleKey": article_key,
                        "extractedAt": extracted_at,
                        "contentHash": content_hash
                    }
                }
                reb_sentences.append(sent_rec)
                
                index_sentences[f"{article_key}#{canonical_ps}"].append({
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "ps": canonical_ps,
                    "text": text_en,
                    "translation": trans_zh
                })
        
        # --- Vocabulary Extraction ---
        reb_vocab = []
        if 'vocabulary' in t and isinstance(t['vocabulary'], list):
            for v in t['vocabulary']:
                word_str = v.get('word', '').strip()
                if not word_str: continue
                known_v = {'word', 'surface', 'ipa', 'pos', 'location', 'contextMeaning', 'meaning', 'examMeaning', 'collocationOrDerivation', 'frequencyRating', 'isSelfAnnotated'}
                v_raw = {k: val for k, val in v.items() if k not in known_v}
                
                v_rec = {
                    "schemaVersion": "kaoyan-existing-vocabulary-1.0",
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "surface": v.get('surface') or word_str,
                    "word": word_str,
                    "ipa": v.get('ipa'),
                    "pos": v.get('pos'),
                    "sourceLocation": v.get('location'),
                    "contextMeaning": v.get('contextMeaning') or v.get('meaning'),
                    "examMeaning": v.get('examMeaning'),
                    "collocationOrDerivation": v.get('collocationOrDerivation'),
                    "frequencyRating": v.get('frequencyRating'),
                    "isSelfAnnotated": v.get('isSelfAnnotated'),
                    "rawFields": v_raw,
                    "provenance": {
                        "sourceLayer": "rebuilt",
                        "sourceFile": rel_file,
                        "year": year,
                        "articleKey": article_key,
                        "extractedAt": extracted_at,
                        "contentHash": content_hash
                    }
                }
                reb_vocab.append(v_rec)
                
                index_vocabulary[word_str.lower()].append({
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "word": word_str,
                    "location": v.get('location'),
                    "contextMeaning": v.get('contextMeaning') or v.get('meaning')
                })
        
        # --- Phrases Extraction ---
        reb_phrases = []
        if 'phrasesAndCollocations' in t and isinstance(t['phrasesAndCollocations'], list):
            for ph in t['phrasesAndCollocations']:
                ph_str = (ph.get('phrase') or ph.get('collocation') or ph.get('surface') or '').strip()
                if not ph_str: continue
                known_ph = {'phrase', 'collocation', 'surface', 'location', 'meaning', 'contextMeaning'}
                ph_raw = {k: val for k, val in ph.items() if k not in known_ph}
                
                loc = ph.get('location')
                if not loc and isinstance(ph.get('collocationNotes'), str) and ph['collocationNotes'].startswith('位置:'):
                    loc = ph['collocationNotes'].split('位置:', 1)[1].strip()
                
                ph_rec = {
                    "schemaVersion": "kaoyan-existing-phrase-1.0",
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "surface": ph_str,
                    "location": loc,
                    "contextMeaning": ph.get('meaning') or ph.get('contextMeaning'),
                    "rawFields": ph_raw,
                    "provenance": {
                        "sourceLayer": "rebuilt",
                        "sourceFile": rel_file,
                        "year": year,
                        "articleKey": article_key,
                        "extractedAt": extracted_at,
                        "contentHash": content_hash
                    }
                }
                reb_phrases.append(ph_rec)
                
                index_phrases[ph_str.lower()].append({
                    "source": "rebuilt",
                    "articleKey": article_key,
                    "surface": ph_str,
                    "location": ph.get('location'),
                    "contextMeaning": ph.get('meaning') or ph.get('contextMeaning')
                })
        
        # --- Questions Extraction ---
        reb_questions = []
        for q_idx, q in enumerate(t.get('questions', []), start=1):
            qi = q.get('qIndex') or q_idx
            stem = q.get('stem') or q.get('questionText') or ""
            ans = q.get('officialAnswer') or q.get('answer') or ""
            known_q = {'qIndex', 'stem', 'questionText', 'officialAnswer', 'answer', 'stemTranslation', 'options', 'standardType', 'type', 'typeDisplayName', 'targetSentences', 'verbatimEvidence', 'synonymMapping', 'methodologyReview', 'presetReflection', 'tangchiModel', 'paperVariants'}
            q_raw = {k: val for k, val in q.items() if k not in known_q}
            
            q_rec = {
                "schemaVersion": "kaoyan-existing-question-1.0",
                "source": "rebuilt",
                "articleKey": article_key,
                "qIndex": qi,
                "questionNumber": q.get('number') or qi,
                "stem": stem,
                "stemTranslation": q.get('stemTranslation'),
                "options": q.get('options', {}),
                "officialAnswer": ans,
                "standardType": q.get('standardType'),
                "type": q.get('type') or q.get('typeDisplayName'),
                "targetSentences": q.get('targetSentences'),
                "verbatimEvidence": q.get('verbatimEvidence'),
                "synonymMapping": q.get('synonymMapping'),
                "methodologyReview": q.get('methodologyReview') or q.get('presetReflection') or q.get('tangchiModel'),
                "paperVariants": q.get('paperVariants'),
                "rawFields": q_raw,
                "provenance": {
                    "sourceLayer": "rebuilt",
                    "sourceFile": rel_file,
                    "year": year,
                    "articleKey": article_key,
                    "extractedAt": extracted_at,
                    "contentHash": content_hash
                }
            }
            reb_questions.append(q_rec)
        
        # --- Article Record ---
        known_art = {'id', 'number', 'title', 'chineseTitle', 'topic', 'topicDomain', 'subTopic', 'overview', 'wordCount', 'readingTimeEstimate', 'difficultyRating', 'sourcePublication', 'backgroundKnowledgeCapsule', 'topicVocabularyCapsule', 'nuancesAndConfusions', 'paragraphs', 'textAnalysis', 'vocabulary', 'phrasesAndCollocations', 'questions', 'syntax_analysis'}
        art_raw = {k: val for k, val in t.items() if k not in known_art}
        
        capsules = {}
        for cap_key in ['backgroundKnowledgeCapsule', 'topicVocabularyCapsule', 'nuancesAndConfusions', 'syntax_analysis']:
            if cap_key in t:
                capsules[cap_key] = t[cap_key]
        
        art_rec = {
            "schemaVersion": "kaoyan-existing-article-1.0",
            "source": "rebuilt",
            "articleKey": article_key,
            "year": year,
            "textNumber": num,
            "title": t.get('title', ''),
            "chineseTitle": t.get('chineseTitle'),
            "topic": t.get('topic'),
            "topicDomain": t.get('topicDomain'),
            "subTopic": t.get('subTopic'),
            "overview": t.get('overview'),
            "wordCount": t.get('wordCount'),
            "readingTimeEstimate": t.get('readingTimeEstimate'),
            "difficultyRating": t.get('difficultyRating'),
            "sourcePublication": t.get('sourcePublication'),
            "paragraphCount": len(paras),
            "sentenceCount": len(reb_sentences),
            "vocabularyCount": len(reb_vocab),
            "phraseCount": len(reb_phrases),
            "questionCount": len(reb_questions),
            "capsules": capsules,
            "rawFields": art_raw,
            "provenance": {
                "sourceLayer": "rebuilt",
                "sourceFile": rel_file,
                "year": year,
                "articleKey": article_key,
                "extractedAt": extracted_at,
                "contentHash": content_hash
            }
        }
        
        # Write rebuilt records
        with open(os.path.join(RECORDS_DIR, 'rebuilt', 'articles', f"{article_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(art_rec, f, ensure_ascii=False, indent=2)
        with open(os.path.join(RECORDS_DIR, 'rebuilt', 'sentences', f"{article_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(reb_sentences, f, ensure_ascii=False, indent=2)
        with open(os.path.join(RECORDS_DIR, 'rebuilt', 'vocabulary', f"{article_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(reb_vocab, f, ensure_ascii=False, indent=2)
        with open(os.path.join(RECORDS_DIR, 'rebuilt', 'phrases', f"{article_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(reb_phrases, f, ensure_ascii=False, indent=2)
        with open(os.path.join(RECORDS_DIR, 'rebuilt', 'questions', f"{article_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(reb_questions, f, ensure_ascii=False, indent=2)
        
        # Article index
        if article_key not in index_articles:
            index_articles[article_key] = {
                "articleKey": article_key,
                "year": year,
                "textNumber": num,
                "title": t.get('title', ''),
                "sources": ["rebuilt"],
                "rebuilt": {
                    "sentenceCount": len(reb_sentences),
                    "vocabularyCount": len(reb_vocab),
                    "phraseCount": len(reb_phrases),
                    "questionCount": len(reb_questions)
                }
            }
        else:
            if "rebuilt" not in index_articles[article_key]["sources"]:
                index_articles[article_key]["sources"].append("rebuilt")
            index_articles[article_key]["rebuilt"] = {
                "sentenceCount": len(reb_sentences),
                "vocabularyCount": len(reb_vocab),
                "phraseCount": len(reb_phrases),
                "questionCount": len(reb_questions)
            }
        
        files_manifest.append({
            "sourceFile": rel_file,
            "sourceLayer": "rebuilt",
            "year": year,
            "status": "parsed",
            "contentHash": content_hash,
            "recordsProduced": {
                "articles": 1,
                "sentences": len(reb_sentences),
                "vocabulary": len(reb_vocab),
                "phrases": len(reb_phrases),
                "questions": len(reb_questions)
            }
        })
        
        total_stats["rebuilt"]["articles"] += 1
        total_stats["rebuilt"]["sentences"] += len(reb_sentences)
        total_stats["rebuilt"]["vocabulary"] += len(reb_vocab)
        total_stats["rebuilt"]["phrases"] += len(reb_phrases)
        total_stats["rebuilt"]["questions"] += len(reb_questions)
    
    print(f"  Rebuilt stats: {dict(total_stats['rebuilt'])}")
    
    # ----------------------------------------------------
    # 3. Write Manifests
    # ----------------------------------------------------
    print("3. Writing manifests/files.jsonl and manifests/build.json...")
    with open(os.path.join(MANIFESTS_DIR, 'files.jsonl'), 'w', encoding='utf-8') as f:
        for row in files_manifest:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    
    build_meta = {
        "dataset": "kaoyan-existing-data",
        "description": "Extracted existing production and rebuilt dataset for Kaoyan English One (1998-2026)",
        "generatedAt": extracted_at,
        "sourceLayers": {
            "production": {
                "years": sorted(list(set(r['year'] for r in files_manifest if r['sourceLayer'] == 'production'))),
                "sourceFilesCount": sum(1 for r in files_manifest if r['sourceLayer'] == 'production'),
                "records": dict(total_stats["production"])
            },
            "rebuilt": {
                "years": sorted(list(set(r['year'] for r in files_manifest if r['sourceLayer'] == 'rebuilt'))),
                "sourceFilesCount": sum(1 for r in files_manifest if r['sourceLayer'] == 'rebuilt'),
                "records": dict(total_stats["rebuilt"])
            }
        },
        "totals": {
            "totalSourceFiles": len(files_manifest),
            "articles": len(index_articles),
            "uniqueSentenceLocators": len(index_sentences),
            "uniqueVocabularyHeadwords": len(index_vocabulary),
            "uniquePhrases": len(index_phrases)
        }
    }
    with open(os.path.join(MANIFESTS_DIR, 'build.json'), 'w', encoding='utf-8') as f:
        json.dump(build_meta, f, ensure_ascii=False, indent=2)
    
    # ----------------------------------------------------
    # 4. Write Indexes
    # ----------------------------------------------------
    print("4. Writing indexes/articles.json, sentences.json, vocabulary.json, phrases.json...")
    with open(os.path.join(INDEXES_DIR, 'articles.json'), 'w', encoding='utf-8') as f:
        json.dump(index_articles, f, ensure_ascii=False, indent=2)
    with open(os.path.join(INDEXES_DIR, 'sentences.json'), 'w', encoding='utf-8') as f:
        json.dump(index_sentences, f, ensure_ascii=False, indent=2)
    with open(os.path.join(INDEXES_DIR, 'vocabulary.json'), 'w', encoding='utf-8') as f:
        json.dump(index_vocabulary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(INDEXES_DIR, 'phrases.json'), 'w', encoding='utf-8') as f:
        json.dump(index_phrases, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - t0
    print(f"=== Extraction Completed in {elapsed:.1f}s ===")

if __name__ == '__main__':
    main()
