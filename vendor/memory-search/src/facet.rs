//! Facet key matching and weighted search.
//!
//! Ports the Python `facet_index.py` logic to Rust.
//! Facet keys follow the format: `k/<facet>/<value>`

use std::collections::{HashMap, HashSet};

use regex::Regex;

/// Facet type weights for scoring.
fn facet_weight(facet_type: &str) -> f64 {
    match facet_type {
        "step" => 5.0,
        "req" => 4.0,
        "what" | "why" | "how" => 3.0,
        "where" => 2.0,
        "who" => 1.0,
        _ => 1.0,
    }
}

/// In-memory facet index: facet_key -> set of record_ids.
#[derive(Debug, Clone, Default)]
pub struct FacetIndex {
    /// Forward index: facet_key -> record_ids
    forward: HashMap<String, Vec<String>>,
    /// Reverse index: record_id -> facet_keys
    reverse: HashMap<String, HashSet<String>>,
}

impl FacetIndex {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a record with its facet keys.
    pub fn add(&mut self, record_id: &str, facet_keys: &[String]) {
        // Remove old entry if exists
        self.remove(record_id);

        for key in facet_keys {
            self.forward
                .entry(key.clone())
                .or_default()
                .push(record_id.to_string());
        }
        self.reverse
            .insert(record_id.to_string(), facet_keys.iter().cloned().collect());
    }

    /// Remove a record from the index.
    pub fn remove(&mut self, record_id: &str) {
        if let Some(keys) = self.reverse.remove(record_id) {
            for key in &keys {
                if let Some(ids) = self.forward.get_mut(key) {
                    ids.retain(|id| id != record_id);
                    if ids.is_empty() {
                        self.forward.remove(key);
                    }
                }
            }
        }
    }

    /// Weighted search: score each record by sum of matching facet weights.
    pub fn weighted_search(&self, query_facets: &[String], top_k: usize) -> Vec<(String, f64)> {
        let mut scores: HashMap<String, f64> = HashMap::new();

        for facet_key in query_facets {
            let weight = parse_facet_type(facet_key)
                .map(|t| facet_weight(&t))
                .unwrap_or(1.0);

            if let Some(record_ids) = self.forward.get(facet_key) {
                for rid in record_ids {
                    *scores.entry(rid.clone()).or_default() += weight;
                }
            }
        }

        let mut results: Vec<(String, f64)> = scores.into_iter().collect();
        results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        results.truncate(top_k);
        results
    }

    /// Get facet keys for a record.
    pub fn get_facets_for_record(&self, record_id: &str) -> Vec<String> {
        self.reverse
            .get(record_id)
            .map(|s| s.iter().cloned().collect())
            .unwrap_or_default()
    }

    /// Get all related records (records sharing the most facets).
    pub fn get_related(&self, record_id: &str, top_k: usize) -> Vec<(String, usize)> {
        let my_facets = match self.reverse.get(record_id) {
            Some(f) => f,
            None => return vec![],
        };

        let mut overlap: HashMap<String, usize> = HashMap::new();
        for facet in my_facets {
            if let Some(ids) = self.forward.get(facet) {
                for id in ids {
                    if id != record_id {
                        *overlap.entry(id.clone()).or_default() += 1;
                    }
                }
            }
        }

        let mut results: Vec<(String, usize)> = overlap.into_iter().collect();
        results.sort_by(|a, b| b.1.cmp(&a.1));
        results.truncate(top_k);
        results
    }

    /// Total number of unique facet keys.
    pub fn facet_count(&self) -> usize {
        self.forward.len()
    }

    /// Total number of indexed records.
    pub fn record_count(&self) -> usize {
        self.reverse.len()
    }
}

/// Parse the facet type from a facet key like "k/what/value".
fn parse_facet_type(key: &str) -> Option<String> {
    let parts: Vec<&str> = key.splitn(3, '/').collect();
    if parts.len() >= 2 && parts[0] == "k" {
        Some(parts[1].to_string())
    } else {
        None
    }
}

/// Extract facet keys from a natural language query.
pub fn extract_query_facets(query: &str) -> Vec<String> {
    let mut facets = Vec::new();

    // Match explicit facet keys: k/<type>/<value>
    let explicit_re = Regex::new(r"k/[a-z]+/[a-z0-9\-]+").unwrap();
    for m in explicit_re.find_iter(query) {
        facets.push(m.as_str().to_string());
    }

    // Generate implicit what-facets from words
    let word_re = Regex::new(r"[a-z0-9]+(?:-[a-z0-9]+)*").unwrap();
    let lower = query.to_lowercase();
    for m in word_re.find_iter(&lower) {
        let word = m.as_str();
        if word.len() >= 3 {
            let facet = format!("k/what/{word}");
            if !facets.contains(&facet) {
                facets.push(facet);
            }
        }
    }

    facets
}

/// Normalize a facet value (matching Python's normalize_facet_value).
pub fn normalize_facet_value(value: &str) -> String {
    let lower = value.to_lowercase().trim().to_string();
    let re = Regex::new(r"[_\s./]").unwrap();
    let replaced = re.replace_all(&lower, "-").to_string();
    let re2 = Regex::new(r"[^a-z0-9\-]").unwrap();
    let cleaned = re2.replace_all(&replaced, "").to_string();
    let re3 = Regex::new(r"-{2,}").unwrap();
    let collapsed = re3.replace_all(&cleaned, "-").to_string();
    let result = collapsed.trim_matches('-').to_string();
    if result.is_empty() {
        "unknown".to_string()
    } else {
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_facet_index_add_and_search() {
        let mut idx = FacetIndex::new();
        idx.add(
            "req-001",
            &["k/what/auth".to_string(), "k/who/admin".to_string()],
        );
        idx.add(
            "req-002",
            &["k/what/auth".to_string(), "k/what/jwt".to_string()],
        );

        let results = idx.weighted_search(&["k/what/auth".to_string()], 10);
        assert_eq!(results.len(), 2);
        // Both should have score = 3.0 (what weight)
        assert_eq!(results[0].1, 3.0);
    }

    #[test]
    fn test_facet_index_remove() {
        let mut idx = FacetIndex::new();
        idx.add("req-001", &["k/what/auth".to_string()]);
        idx.remove("req-001");

        let results = idx.weighted_search(&["k/what/auth".to_string()], 10);
        assert!(results.is_empty());
    }

    #[test]
    fn test_extract_query_facets() {
        let facets = extract_query_facets("authentication middleware k/who/admin");
        assert!(facets.contains(&"k/who/admin".to_string()));
        assert!(facets.contains(&"k/what/authentication".to_string()));
        assert!(facets.contains(&"k/what/middleware".to_string()));
    }

    #[test]
    fn test_normalize_facet_value() {
        assert_eq!(
            normalize_facet_value("JWT Verification"),
            "jwt-verification"
        );
        assert_eq!(
            normalize_facet_value("src/auth/middleware.py"),
            "src-auth-middleware-py"
        );
        assert_eq!(normalize_facet_value(""), "unknown");
        assert_eq!(normalize_facet_value("hello_world"), "hello-world");
    }

    #[test]
    fn test_weighted_search_scoring() {
        let mut idx = FacetIndex::new();
        idx.add(
            "req-001",
            &[
                "k/step/s01".to_string(),  // weight 5
                "k/what/auth".to_string(), // weight 3
            ],
        );
        idx.add(
            "req-002",
            &["k/who/admin".to_string()], // weight 1
        );

        let results = idx.weighted_search(
            &[
                "k/step/s01".to_string(),
                "k/what/auth".to_string(),
                "k/who/admin".to_string(),
            ],
            10,
        );

        // req-001: 5 + 3 = 8, req-002: 1
        assert_eq!(results[0].0, "req-001");
        assert_eq!(results[0].1, 8.0);
        assert_eq!(results[1].0, "req-002");
        assert_eq!(results[1].1, 1.0);
    }
}
