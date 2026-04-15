//! Hybrid search engine powered by bb25 + BGE-M3 + Qdrant.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::rc::Rc;

use bayesian_bm25::{BM25Scorer, BayesianBM25Scorer, Corpus, Tokenizer};
use regex::Regex;

use crate::facet::{extract_query_facets, FacetIndex};
use crate::qdrant::{
    payload_for_record, qdrant_score_to_probability, require_embedding_dimension, QdrantPoint,
    QdrantStore,
};
use crate::record::load_all_records;
use crate::tei::TeiClient;
use crate::types::{IndexMeta, MemoryRecord, SearchResult};

const KEYWORD_STOPS: &[&str] = &[
    "the", "a", "an", "is", "was", "are", "in", "on", "at", "to", "for", "of", "and", "or",
];

const BB25_K1: f64 = 1.2;
const BB25_B: f64 = 0.75;
const BB25_ALPHA: f64 = 1.0;
const BB25_BETA: f64 = 0.5;

const FINAL_WEIGHT_HYBRID: f64 = 0.90;
const FINAL_WEIGHT_FACET: f64 = 0.07;
const FINAL_WEIGHT_RECENCY: f64 = 0.02;
const FINAL_WEIGHT_LINK: f64 = 0.01;

const ENGINE_VERSION: &str = "bb25-bge-m3-qdrant-v1";
const TOKENIZER_VERSION: &str = "bb25-unicode-v1";

/// Hybrid engine with persistent vector index (Qdrant) and bb25 sparse ranking.
pub struct HybridEngine {
    pub facet_index: FacetIndex,
    pub records: HashMap<String, MemoryRecord>,
    qdrant: QdrantStore,
    tei: TeiClient,
    index_dir: PathBuf,
    needs_migration: bool,
    word_re: Regex,
    tokenizer: Tokenizer,
}

impl HybridEngine {
    pub fn new() -> Self {
        Self::load(Path::new("data/memory/index"))
    }

    /// Load engine state from disk metadata.
    pub fn load(index_dir: &Path) -> Self {
        let meta_path = index_dir.join("rust_index_meta.json");
        let mut needs_migration = true;
        if let Ok(meta_str) = std::fs::read_to_string(&meta_path) {
            if let Ok(meta) = serde_json::from_str::<IndexMeta>(&meta_str) {
                needs_migration = meta.engine_version != ENGINE_VERSION;
            }
        }

        Self {
            facet_index: FacetIndex::new(),
            records: HashMap::new(),
            qdrant: QdrantStore::new(index_dir),
            tei: TeiClient::new(index_dir),
            index_dir: index_dir.to_path_buf(),
            needs_migration,
            word_re: Regex::new(r"\w+").expect("regex must compile"),
            tokenizer: Tokenizer::new(),
        }
    }

    /// Auto-migrate legacy index data by forcing a rebuild once.
    pub fn ensure_engine_current(&mut self, data_dir: &Path) -> anyhow::Result<()> {
        if self.needs_migration {
            self.rebuild(data_dir)?;
            self.needs_migration = false;
        }
        Ok(())
    }

    /// Rebuild the entire index from record files.
    pub fn rebuild(&mut self, data_dir: &Path) -> anyhow::Result<usize> {
        let records = load_all_records(data_dir)?;
        let count = records.len();

        self.records.clear();
        self.facet_index = FacetIndex::new();
        for rec in &records {
            self.facet_index.add(&rec.id, &rec.facet_keys);
            self.records.insert(rec.id.clone(), rec.clone());
        }

        if records.is_empty() {
            self.save(&self.index_dir)?;
            return Ok(0);
        }

        let texts: Vec<String> = records.iter().map(MemoryRecord::to_search_text).collect();
        let embeddings = self.tei.embed_batch(&texts)?;
        if embeddings.len() != records.len() {
            anyhow::bail!(
                "embedding count mismatch: got {}, expected {}",
                embeddings.len(),
                records.len()
            );
        }
        let dim = require_embedding_dimension(&embeddings)?;
        self.qdrant.recreate_collection(dim)?;

        let points: Vec<QdrantPoint> = records
            .iter()
            .zip(embeddings)
            .map(|(record, embedding)| QdrantPoint {
                id: record.id.clone(),
                vector: embedding,
                payload: payload_for_record(record),
            })
            .collect();

        for chunk in points.chunks(128) {
            self.qdrant.upsert_points(chunk, dim)?;
        }

        self.save(&self.index_dir)?;
        Ok(count)
    }

    /// Add or update one record in the index.
    pub fn index_record(&mut self, record: &MemoryRecord) -> anyhow::Result<()> {
        self.facet_index.add(&record.id, &record.facet_keys);
        self.records.insert(record.id.clone(), record.clone());

        let embedding = self.tei.embed(&record.to_search_text())?;
        let point = QdrantPoint {
            id: record.id.clone(),
            vector: embedding,
            payload: payload_for_record(record),
        };
        self.qdrant.upsert_point(&point)?;
        self.save(&self.index_dir)?;
        Ok(())
    }

    /// Remove a record from the index.
    pub fn remove_record(&mut self, record_id: &str) -> anyhow::Result<()> {
        self.facet_index.remove(record_id);
        self.records.remove(record_id);
        self.qdrant.delete_point(record_id)?;
        self.save(&self.index_dir)?;
        Ok(())
    }

    /// Hybrid search over sparse + dense + graph priors.
    pub fn search(&self, query: &str, top_k: usize, mode: &str) -> Vec<SearchResult> {
        let capped_top_k = top_k.max(1);

        let query_facets = extract_query_facets(query);
        let facet_results = if !query_facets.is_empty() {
            self.facet_index
                .weighted_search(&query_facets, capped_top_k * 5)
        } else {
            vec![]
        };
        let facet_map = normalize_rank_scores(&facet_results);

        let query_terms = self.tokenizer.tokenize(query);
        let bayes_map = self
            .build_bayesian_scores(&query_terms)
            .unwrap_or_else(|err| {
                eprintln!("[memory-search] sparse scoring failed: {err}");
                HashMap::new()
            });

        let dense_limit = capped_top_k.saturating_mul(20).max(20);
        let vector_map = self
            .tei
            .embed(query)
            .and_then(|embedding| self.qdrant.search(&embedding, dense_limit))
            .map(|hits| {
                let mut map = HashMap::new();
                for hit in hits {
                    map.insert(hit.id, qdrant_score_to_probability(hit.score));
                }
                map
            })
            .unwrap_or_else(|err| {
                eprintln!("[memory-search] dense search failed: {err}");
                HashMap::new()
            });

        let keywords = self.extract_keywords(query);
        let mut candidates: HashSet<String> = HashSet::new();
        candidates.extend(facet_map.keys().cloned());
        candidates.extend(bayes_map.keys().cloned());
        candidates.extend(vector_map.keys().cloned());

        if candidates.is_empty() {
            return vec![];
        }

        let query_facet_set: HashSet<&str> = query_facets.iter().map(|s| s.as_str()).collect();
        let mut scored: Vec<SearchResult> = candidates
            .into_iter()
            .map(|id| {
                let bayes_score = *bayes_map.get(&id).unwrap_or(&0.0);
                let vector_score = *vector_map.get(&id).unwrap_or(&0.0);
                let facet_score = *facet_map.get(&id).unwrap_or(&0.0);
                let hybrid_score = probabilistic_or(bayes_score, vector_score);
                let recency = self.recency_boost(&id);
                let link = self.link_bonus(&id);

                let score = FINAL_WEIGHT_HYBRID * hybrid_score
                    + FINAL_WEIGHT_FACET * facet_score
                    + FINAL_WEIGHT_RECENCY * recency
                    + FINAL_WEIGHT_LINK * link;

                let matched_facets: Vec<String> = self
                    .facet_index
                    .get_facets_for_record(&id)
                    .into_iter()
                    .filter(|f| query_facet_set.contains(f.as_str()))
                    .collect();

                let record_type = self
                    .records
                    .get(&id)
                    .map(|r| r.record_type.clone())
                    .unwrap_or_else(|| detect_type(&id));

                SearchResult {
                    record_id: id.clone(),
                    record_type,
                    score,
                    vector_score,
                    facet_score,
                    keyword_score: bayes_score,
                    bm25_score: bayes_score,
                    bayes_score,
                    hybrid_score,
                    vector_db_score: vector_score,
                    matched_facets,
                    snippet: self.extract_snippet(&id, &keywords),
                }
            })
            .collect();

        scored.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        if mode == "insight" && !scored.is_empty() {
            let initial_top: Vec<String> =
                scored.iter().take(5).map(|r| r.record_id.clone()).collect();
            let expanded = self.expand_one_hop(&initial_top);
            let mut seen: HashSet<String> = scored.iter().map(|r| r.record_id.clone()).collect();
            for id in expanded {
                if seen.insert(id.clone()) {
                    scored.push(SearchResult {
                        record_id: id.clone(),
                        record_type: detect_type(&id),
                        score: 0.001,
                        vector_score: 0.0,
                        facet_score: 0.0,
                        keyword_score: 0.0,
                        bm25_score: 0.0,
                        bayes_score: 0.0,
                        hybrid_score: 0.0,
                        vector_db_score: 0.0,
                        matched_facets: vec![],
                        snippet: self.extract_snippet(&id, &keywords),
                    });
                }
            }
            scored.sort_by(|a, b| {
                b.score
                    .partial_cmp(&a.score)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
        }

        scored.truncate(capped_top_k);
        scored
    }

    /// Save metadata for dashboard/ops.
    pub fn save(&self, index_dir: &Path) -> anyhow::Result<()> {
        std::fs::create_dir_all(index_dir)?;
        let meta = IndexMeta {
            built_at: chrono::Utc::now().to_rfc3339(),
            record_count: self.records.len(),
            vocabulary_size: self.vocabulary_size(),
            facet_count: self.facet_index.facet_count(),
            vector_points: self.qdrant.count_points().unwrap_or(0),
            engine_version: ENGINE_VERSION.to_string(),
            embedding_model: self.tei.model_name().to_string(),
            tokenizer: TOKENIZER_VERSION.to_string(),
        };
        let meta_json = serde_json::to_string_pretty(&meta)?;
        std::fs::write(index_dir.join("rust_index_meta.json"), meta_json)?;
        Ok(())
    }

    pub fn vector_count(&self) -> usize {
        self.qdrant.count_points().unwrap_or(0)
    }

    pub fn vocabulary_size(&self) -> usize {
        let mut vocab = HashSet::new();
        for record in self.records.values() {
            for token in self.tokenizer.tokenize(&record.to_search_text()) {
                vocab.insert(token);
            }
        }
        vocab.len()
    }

    fn build_bayesian_scores(
        &self,
        query_terms: &[String],
    ) -> anyhow::Result<HashMap<String, f64>> {
        if query_terms.is_empty() || self.records.is_empty() {
            return Ok(HashMap::new());
        }

        let mut corpus = Corpus::new(Tokenizer::new());
        for record in self.records.values() {
            corpus.add_document(&record.id, &record.to_search_text(), vec![]);
        }
        corpus.build_index();
        let corpus = Rc::new(corpus);
        let bm25 = Rc::new(BM25Scorer::new(Rc::clone(&corpus), BB25_K1, BB25_B));
        let bayes = BayesianBM25Scorer::new(bm25, BB25_ALPHA, BB25_BETA);

        let mut scores = HashMap::new();
        for doc in corpus.documents() {
            let score = bayes.score(query_terms, doc).clamp(0.0, 1.0);
            if score > 0.0 {
                scores.insert(doc.id.clone(), score);
            }
        }
        Ok(scores)
    }

    fn extract_keywords(&self, query: &str) -> Vec<String> {
        let lower = query.to_lowercase();
        let cleaned = Regex::new(r"k/[a-z]+/[a-z0-9\-]+")
            .expect("regex must compile")
            .replace_all(&lower, "")
            .to_string();

        let stops: HashSet<&str> = KEYWORD_STOPS.iter().copied().collect();
        self.word_re
            .find_iter(&cleaned)
            .map(|m| m.as_str().to_string())
            .filter(|w| w.len() >= 2 && !stops.contains(w.as_str()))
            .collect()
    }

    fn recency_boost(&self, record_id: &str) -> f64 {
        let record = match self.records.get(record_id) {
            Some(r) => r,
            None => return 0.0,
        };
        if record.created_at.is_empty() {
            return 0.5;
        }

        if let Ok(dt) =
            chrono::NaiveDateTime::parse_from_str(&record.created_at, "%Y-%m-%dT%H:%M:%S")
        {
            let now = chrono::Utc::now().naive_utc();
            let days = (now - dt).num_days().max(0) as f64;
            return 1.0 / (1.0 + days / 30.0);
        }
        if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(&record.created_at) {
            let now = chrono::Utc::now();
            let days = (now - dt.with_timezone(&chrono::Utc)).num_days().max(0) as f64;
            return 1.0 / (1.0 + days / 30.0);
        }
        0.5
    }

    fn link_bonus(&self, record_id: &str) -> f64 {
        self.records
            .get(record_id)
            .map(|r| {
                if !r.causal_targets.is_empty() {
                    1.0
                } else if !r.link_targets.is_empty() {
                    0.5
                } else {
                    0.0
                }
            })
            .unwrap_or(0.0)
    }

    fn expand_one_hop(&self, initial: &[String]) -> Vec<String> {
        let mut seen: HashSet<String> = initial.iter().cloned().collect();
        let mut expanded = Vec::new();

        let mut facet_count: HashMap<String, usize> = HashMap::new();
        for id in initial {
            for facet in self.facet_index.get_facets_for_record(id) {
                *facet_count.entry(facet).or_default() += 1;
            }
        }

        let mut top_facets: Vec<(String, usize)> = facet_count.into_iter().collect();
        top_facets.sort_by(|a, b| b.1.cmp(&a.1));
        for (facet, _) in top_facets.iter().take(5) {
            let results = self
                .facet_index
                .weighted_search(std::slice::from_ref(facet), 5);
            let mut added = 0;
            for (id, _) in results {
                if seen.insert(id.clone()) {
                    expanded.push(id);
                    added += 1;
                    if added >= 3 {
                        break;
                    }
                }
            }
        }
        expanded
    }

    fn extract_snippet(&self, record_id: &str, keywords: &[String]) -> String {
        let record = match self.records.get(record_id) {
            Some(r) => r,
            None => return String::new(),
        };
        let text = record.to_search_text();
        if text.is_empty() {
            return String::new();
        }

        let lower = text.to_lowercase();
        for kw in keywords {
            if let Some(byte_idx) = lower.find(kw.as_str()) {
                let start_chars = lower[..byte_idx].chars().count().saturating_sub(40);
                let kw_chars = kw.chars().count();
                let total_chars = text.chars().count();
                let end_chars = (start_chars + kw_chars + 80).min(total_chars);
                let snippet: String = text
                    .chars()
                    .skip(start_chars)
                    .take(end_chars.saturating_sub(start_chars))
                    .collect();
                if start_chars > 0 || end_chars < total_chars {
                    return format!("...{}...", snippet);
                }
                return snippet;
            }
        }

        let total_chars = text.chars().count();
        let end_chars = total_chars.min(160);
        let snippet: String = text.chars().take(end_chars).collect();
        if end_chars < total_chars {
            return format!("{snippet}...");
        }
        snippet
    }
}

fn normalize_rank_scores(raw: &[(String, f64)]) -> HashMap<String, f64> {
    let mut out = HashMap::new();
    let max_score = raw.iter().map(|(_, s)| *s).fold(0.0_f64, |a, b| a.max(b));
    for (id, score) in raw {
        let normalized = if max_score > 0.0 {
            (score / max_score).clamp(0.0, 1.0)
        } else {
            0.0
        };
        out.insert(id.clone(), normalized);
    }
    out
}

fn probabilistic_or(a: f64, b: f64) -> f64 {
    let aa = a.clamp(0.0, 1.0);
    let bb = b.clamp(0.0, 1.0);
    1.0 - (1.0 - aa) * (1.0 - bb)
}

fn detect_type(id: &str) -> String {
    if id.starts_with("req-") {
        "request".to_string()
    } else if id.starts_with("work-") {
        "work".to_string()
    } else if id.starts_with("know-") {
        "knowledge".to_string()
    } else if id.starts_with("dec-") {
        "decision".to_string()
    } else if id.starts_with("ins-") {
        "insight".to_string()
    } else if id.starts_with("evt-") {
        "event".to_string()
    } else {
        "unknown".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn probabilistic_or_behaves() {
        assert!((probabilistic_or(0.5, 0.5) - 0.75).abs() < 1e-9);
        assert!((probabilistic_or(0.0, 0.0) - 0.0).abs() < 1e-9);
        assert!((probabilistic_or(1.0, 0.2) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn normalize_rank_scores_scales_to_one() {
        let scores = vec![
            ("a".to_string(), 2.0),
            ("b".to_string(), 1.0),
            ("c".to_string(), 0.0),
        ];
        let normalized = normalize_rank_scores(&scores);
        assert!((normalized["a"] - 1.0).abs() < 1e-9);
        assert!((normalized["b"] - 0.5).abs() < 1e-9);
        assert!((normalized["c"] - 0.0).abs() < 1e-9);
    }
}
