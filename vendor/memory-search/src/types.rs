//! Shared types for memory search.

use serde::{Deserialize, Serialize};

/// A parsed memory record from YAML frontmatter + Markdown.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryRecord {
    pub id: String,
    pub record_type: String, // "request" | "work"
    pub who: String,
    pub where_field: String,
    pub topics: Vec<String>,
    pub facet_keys: Vec<String>,
    pub created_at: String,
    pub body: String,
    // RequestRecord fields
    pub what: Option<String>,
    pub why_hypotheses: Vec<String>,
    pub how_steps: Vec<String>,
    // WorkRecord fields
    pub immediate_goal: Option<String>,
    pub actions: Vec<String>,
    pub evidence: Vec<String>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    // Links
    pub link_targets: Vec<String>,
    pub causal_targets: Vec<String>,
}

impl MemoryRecord {
    /// Build a composite text representation for TF-IDF embedding.
    pub fn to_search_text(&self) -> String {
        let mut parts = Vec::new();

        if let Some(ref what) = self.what {
            parts.push(format!("what: {what}"));
        }
        if let Some(ref goal) = self.immediate_goal {
            parts.push(format!("goal: {goal}"));
        }
        if !self.topics.is_empty() {
            parts.push(format!("topics: {}", self.topics.join(", ")));
        }
        for h in &self.why_hypotheses {
            parts.push(format!("why: {h}"));
        }
        for s in &self.how_steps {
            parts.push(format!("step: {s}"));
        }
        for a in &self.actions {
            parts.push(format!("action: {a}"));
        }
        for e in &self.evidence {
            parts.push(format!("evidence: {e}"));
        }
        if !self.inputs.is_empty() || !self.outputs.is_empty() {
            let files: Vec<&str> = self
                .inputs
                .iter()
                .chain(self.outputs.iter())
                .map(|s| s.as_str())
                .collect();
            parts.push(format!("files: {}", files.join(", ")));
        }

        // Include body for additional context
        if !self.body.is_empty() {
            parts.push(self.body.clone());
        }

        parts.join("\n")
    }
}

/// A single search result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub record_id: String,
    pub record_type: String,
    pub score: f64,
    pub vector_score: f64,
    pub facet_score: f64,
    pub keyword_score: f64,
    #[serde(default)]
    pub bm25_score: f64,
    #[serde(default)]
    pub bayes_score: f64,
    #[serde(default)]
    pub hybrid_score: f64,
    #[serde(default)]
    pub vector_db_score: f64,
    pub matched_facets: Vec<String>,
    pub snippet: String,
}

/// Index metadata persisted alongside the index.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexMeta {
    pub built_at: String,
    pub record_count: usize,
    #[serde(default)]
    pub vocabulary_size: usize,
    pub facet_count: usize,
    #[serde(default)]
    pub vector_points: usize,
    #[serde(default)]
    pub engine_version: String,
    #[serde(default)]
    pub embedding_model: String,
    #[serde(default)]
    pub tokenizer: String,
}
