//! TF-IDF indexer for semantic vector search.

use std::collections::HashMap;
use std::path::Path;

use anyhow::Result;
use regex::Regex;
use serde::{Deserialize, Serialize};

/// English stopwords to exclude from tokenization.
const STOPWORDS: &[&str] = &[
    "the", "a", "an", "is", "was", "are", "in", "on", "at", "to", "for", "of", "and", "or", "it",
    "its", "be", "has", "had", "do", "did", "not", "this", "that", "with", "from", "by", "as",
    "but", "if", "so", "no", "he", "she", "we", "they", "my", "your", "his", "her", "our", "me",
    "him", "us", "them", "who", "which", "what", "when", "where", "how", "all", "each", "any",
    "few", "more", "most", "some", "such", "than", "too", "very", "can", "will", "just", "should",
    "now",
];

/// Persistent TF-IDF model data.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct TfidfModel {
    vocabulary: HashMap<String, usize>,
    idf: Vec<f64>,
    document_count: usize,
}

/// TF-IDF index supporting fit, embed, search, and incremental updates.
pub struct TfidfIndex {
    vocabulary: HashMap<String, usize>,
    idf: Vec<f64>,
    vectors: HashMap<String, Vec<f64>>,
    document_count: usize,
    word_re: Regex,
    stopwords: std::collections::HashSet<String>,
}

impl TfidfIndex {
    pub fn new() -> Self {
        Self {
            vocabulary: HashMap::new(),
            idf: Vec::new(),
            vectors: HashMap::new(),
            document_count: 0,
            word_re: Regex::new(r"\w+").unwrap(),
            stopwords: STOPWORDS.iter().map(|s| s.to_string()).collect(),
        }
    }

    /// Fit the TF-IDF model on a corpus and generate vectors for all documents.
    pub fn fit(&mut self, documents: &[(String, String)]) {
        self.document_count = documents.len();
        if self.document_count == 0 {
            return;
        }

        // Build vocabulary and document frequencies
        let mut df: HashMap<String, usize> = HashMap::new();
        let mut all_tokens: Vec<Vec<String>> = Vec::new();

        for (_id, text) in documents {
            let tokens = self.tokenize(text);
            let unique: std::collections::HashSet<&String> = tokens.iter().collect();
            for term in &unique {
                *df.entry((*term).clone()).or_default() += 1;
            }
            all_tokens.push(tokens);
        }

        // Filter low-frequency terms (keep terms appearing in at least 1 doc)
        // and build vocabulary
        let mut vocab: Vec<(String, usize)> = df.into_iter().collect();
        vocab.sort_by(|a, b| a.0.cmp(&b.0)); // deterministic ordering

        self.vocabulary.clear();
        self.idf.clear();

        let n = self.document_count as f64;
        for (idx, (term, freq)) in vocab.iter().enumerate() {
            self.vocabulary.insert(term.clone(), idx);
            // IDF with smoothing: log((1 + N) / (1 + df)) + 1
            self.idf.push(((1.0 + n) / (1.0 + *freq as f64)).ln() + 1.0);
        }

        // Generate vectors for all documents
        self.vectors.clear();
        for (i, (id, _text)) in documents.iter().enumerate() {
            let vec = self.compute_tfidf(&all_tokens[i]);
            self.vectors.insert(id.clone(), vec);
        }
    }

    /// Embed a text string into a TF-IDF vector.
    pub fn embed(&self, text: &str) -> Vec<f64> {
        let tokens = self.tokenize(text);
        self.compute_tfidf(&tokens)
    }

    /// Search for the most similar documents to a query.
    pub fn search(&self, query: &str, top_k: usize) -> Vec<(String, f64)> {
        if self.vocabulary.is_empty() || self.vectors.is_empty() {
            return vec![];
        }

        let query_vec = self.embed(query);
        if is_zero_vector(&query_vec) {
            return vec![];
        }

        let mut scores: Vec<(String, f64)> = self
            .vectors
            .iter()
            .map(|(id, doc_vec)| {
                let sim = cosine_similarity(&query_vec, doc_vec);
                (id.clone(), sim)
            })
            .filter(|(_, sim)| *sim > 0.0)
            .collect();

        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(top_k);
        scores
    }

    /// Add a single document (incremental, uses existing vocabulary).
    pub fn add(&mut self, id: &str, text: &str) {
        if self.vocabulary.is_empty() {
            // Can't add incrementally without a fitted vocabulary
            return;
        }
        let vec = self.embed(text);
        self.vectors.insert(id.to_string(), vec);
    }

    /// Remove a document from the index.
    pub fn remove(&mut self, id: &str) {
        self.vectors.remove(id);
    }

    /// Check if a record is indexed.
    pub fn contains(&self, id: &str) -> bool {
        self.vectors.contains_key(id)
    }

    /// Number of indexed documents.
    pub fn doc_count(&self) -> usize {
        self.vectors.len()
    }

    /// Vocabulary size.
    pub fn vocab_size(&self) -> usize {
        self.vocabulary.len()
    }

    /// Save the model (vocabulary + IDF) and vectors to disk.
    pub fn save(&self, dir: &Path) -> Result<()> {
        std::fs::create_dir_all(dir)?;

        let model = TfidfModel {
            vocabulary: self.vocabulary.clone(),
            idf: self.idf.clone(),
            document_count: self.document_count,
        };
        let model_json = serde_json::to_string_pretty(&model)?;
        std::fs::write(dir.join("tfidf_model.json"), model_json)?;

        let vectors_json = serde_json::to_string(&self.vectors)?;
        std::fs::write(dir.join("vectors.json"), vectors_json)?;

        Ok(())
    }

    /// Load the model and vectors from disk.
    pub fn load(dir: &Path) -> Result<Self> {
        let model_path = dir.join("tfidf_model.json");
        let vectors_path = dir.join("vectors.json");

        if !model_path.exists() || !vectors_path.exists() {
            return Ok(Self::new());
        }

        let model_str = std::fs::read_to_string(&model_path)?;
        let model: TfidfModel = serde_json::from_str(&model_str)?;

        let vectors_str = std::fs::read_to_string(&vectors_path)?;
        let vectors: HashMap<String, Vec<f64>> = serde_json::from_str(&vectors_str)?;

        Ok(Self {
            vocabulary: model.vocabulary,
            idf: model.idf,
            vectors,
            document_count: model.document_count,
            word_re: Regex::new(r"\w+").unwrap(),
            stopwords: STOPWORDS.iter().map(|s| s.to_string()).collect(),
        })
    }

    // --- Internal ---

    fn tokenize(&self, text: &str) -> Vec<String> {
        let lower = text.to_lowercase();
        self.word_re
            .find_iter(&lower)
            .map(|m| m.as_str().to_string())
            .filter(|w| w.len() >= 2 && !self.stopwords.contains(w))
            .collect()
    }

    fn compute_tfidf(&self, tokens: &[String]) -> Vec<f64> {
        let dim = self.vocabulary.len();
        if dim == 0 {
            return vec![];
        }

        // Count term frequencies
        let mut tf: HashMap<&str, usize> = HashMap::new();
        for token in tokens {
            *tf.entry(token.as_str()).or_default() += 1;
        }

        let total = tokens.len() as f64;
        let mut vec = vec![0.0_f64; dim];

        for (term, count) in &tf {
            if let Some(&idx) = self.vocabulary.get(*term) {
                let tf_val = *count as f64 / total.max(1.0);
                vec[idx] = tf_val * self.idf[idx];
            }
        }

        // L2 normalize
        l2_normalize(&mut vec);
        vec
    }
}

/// Cosine similarity between two vectors.
pub fn cosine_similarity(a: &[f64], b: &[f64]) -> f64 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }
    let dot: f64 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f64 = a.iter().map(|x| x * x).sum::<f64>().sqrt();
    let norm_b: f64 = b.iter().map(|x| x * x).sum::<f64>().sqrt();
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    dot / (norm_a * norm_b)
}

fn l2_normalize(vec: &mut [f64]) {
    let norm: f64 = vec.iter().map(|x| x * x).sum::<f64>().sqrt();
    if norm > 0.0 {
        for v in vec.iter_mut() {
            *v /= norm;
        }
    }
}

fn is_zero_vector(vec: &[f64]) -> bool {
    vec.iter().all(|&v| v == 0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fit_and_search() {
        let docs = vec![
            (
                "doc1".to_string(),
                "authentication jwt middleware".to_string(),
            ),
            (
                "doc2".to_string(),
                "database migration postgres".to_string(),
            ),
            (
                "doc3".to_string(),
                "authentication oauth tokens".to_string(),
            ),
        ];

        let mut index = TfidfIndex::new();
        index.fit(&docs);

        assert_eq!(index.doc_count(), 3);
        assert!(index.vocab_size() > 0);

        let results = index.search("authentication jwt", 10);
        assert!(!results.is_empty());
        // doc1 should be most relevant (exact match)
        assert_eq!(results[0].0, "doc1");
    }

    #[test]
    fn test_similar_texts_higher_score() {
        let docs = vec![
            (
                "auth".to_string(),
                "jwt authentication middleware security".to_string(),
            ),
            (
                "db".to_string(),
                "database migration postgres schema tables".to_string(),
            ),
            (
                "auth2".to_string(),
                "oauth authentication tokens security".to_string(),
            ),
        ];

        let mut index = TfidfIndex::new();
        index.fit(&docs);

        let results = index.search("authentication security", 10);
        // auth docs should rank higher than db doc
        let auth_scores: Vec<f64> = results
            .iter()
            .filter(|(id, _)| id.starts_with("auth"))
            .map(|(_, s)| *s)
            .collect();
        let db_scores: Vec<f64> = results
            .iter()
            .filter(|(id, _)| id == "db")
            .map(|(_, s)| *s)
            .collect();

        assert!(!auth_scores.is_empty());
        if !db_scores.is_empty() {
            assert!(auth_scores[0] > db_scores[0]);
        }
    }

    #[test]
    fn test_add_and_remove() {
        let docs = vec![
            ("doc1".to_string(), "hello world".to_string()),
            ("doc2".to_string(), "foo bar".to_string()),
        ];

        let mut index = TfidfIndex::new();
        index.fit(&docs);

        assert!(index.contains("doc1"));
        index.remove("doc1");
        assert!(!index.contains("doc1"));

        index.add("doc3", "hello test");
        assert!(index.contains("doc3"));
    }

    #[test]
    fn test_cosine_similarity_known_values() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert!((cosine_similarity(&a, &b) - 1.0).abs() < 1e-10);

        let c = vec![0.0, 1.0, 0.0];
        assert!((cosine_similarity(&a, &c)).abs() < 1e-10);

        let d = vec![1.0, 1.0, 0.0];
        let sim = cosine_similarity(&a, &d);
        assert!((sim - (1.0 / 2.0_f64.sqrt())).abs() < 1e-10);
    }

    #[test]
    fn test_save_and_load() {
        let dir = tempfile::tempdir().unwrap();
        let docs = vec![
            ("doc1".to_string(), "authentication jwt".to_string()),
            ("doc2".to_string(), "database postgres".to_string()),
        ];

        let mut index = TfidfIndex::new();
        index.fit(&docs);
        index.save(dir.path()).unwrap();

        let loaded = TfidfIndex::load(dir.path()).unwrap();
        assert_eq!(loaded.doc_count(), 2);
        assert_eq!(loaded.vocab_size(), index.vocab_size());

        // Verify search produces same results
        let orig_results = index.search("authentication", 5);
        let loaded_results = loaded.search("authentication", 5);
        assert_eq!(orig_results.len(), loaded_results.len());
        assert_eq!(orig_results[0].0, loaded_results[0].0);
    }

    #[test]
    fn test_empty_index() {
        let index = TfidfIndex::new();
        let results = index.search("anything", 10);
        assert!(results.is_empty());
    }
}
