//! YAML frontmatter parser for memory records.

use std::path::Path;

use anyhow::{Context, Result};

use crate::types::MemoryRecord;

/// Parse a YAML-frontmatter Markdown file into a MemoryRecord.
pub fn parse_record(path: &Path) -> Result<MemoryRecord> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read {}", path.display()))?;

    let (meta, body) = split_frontmatter(&content)?;
    let yaml: serde_yaml::Value =
        serde_yaml::from_str(&meta).with_context(|| "Failed to parse YAML frontmatter")?;

    let id = yaml_str(&yaml, "id").unwrap_or_default();
    let record_type = yaml_str(&yaml, "type").unwrap_or_else(|| {
        if id.starts_with("req-") {
            "request".to_string()
        } else if id.starts_with("know-") {
            "knowledge".to_string()
        } else if id.starts_with("dec-") {
            "decision".to_string()
        } else if id.starts_with("ins-") {
            "insight".to_string()
        } else if id.starts_with("evt-") {
            "event".to_string()
        } else {
            "work".to_string()
        }
    });

    let who = yaml_str(&yaml, "who").unwrap_or_default();
    let where_field = if record_type == "work" {
        // WorkRecord: where is an object with inputs/outputs, skip string extraction
        String::new()
    } else {
        yaml_str(&yaml, "where").unwrap_or_default()
    };

    let topics = yaml_str_list(&yaml, "topics");
    let facet_keys = yaml_str_list(&yaml, "facet_keys");
    let created_at = yaml_str(&yaml, "created_at").unwrap_or_default();

    // RequestRecord fields
    let what = yaml_str(&yaml, "what");
    let why_hypotheses = extract_why_hypotheses(&yaml);
    let how_steps = extract_how_steps(&yaml);

    // WorkRecord-specific fields
    let (immediate_goal, actions, evidence, inputs, outputs) = if record_type == "work" {
        extract_work_fields(&yaml)
    } else {
        // For semantic types, extract evidence if present at top level
        let evidence = yaml_str_list(&yaml, "evidence");
        (None, vec![], evidence, vec![], vec![])
    };

    // Links
    let link_targets = extract_link_targets(&yaml, "links");
    let causal_targets = if record_type == "request" {
        extract_link_targets(&yaml, "causality")
    } else {
        extract_work_causality(&yaml)
    };

    Ok(MemoryRecord {
        id,
        record_type,
        who,
        where_field,
        topics,
        facet_keys,
        created_at,
        body,
        what,
        why_hypotheses,
        how_steps,
        immediate_goal,
        actions,
        evidence,
        inputs,
        outputs,
        link_targets,
        causal_targets,
    })
}

/// Load all records from a data directory.
pub fn load_all_records(data_dir: &Path) -> Result<Vec<MemoryRecord>> {
    let mut records = Vec::new();

    // (subdir, file prefix)
    let dirs: &[(&str, &str)] = &[
        ("requests", "req-"),
        ("works", "work-"),
        ("knowledge", "know-"),
        ("decisions", "dec-"),
        ("insights", "ins-"),
        ("events", "evt-"),
    ];

    for &(subdir, prefix) in dirs {
        let dir = data_dir.join("memory").join(subdir);
        if !dir.exists() {
            continue;
        }
        for entry in walkdir::WalkDir::new(&dir).min_depth(1).max_depth(1) {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map_or(false, |e| e == "md")
                && path
                    .file_name()
                    .map_or(false, |n| n.to_string_lossy().starts_with(prefix))
            {
                match parse_record(path) {
                    Ok(rec) => records.push(rec),
                    Err(e) => {
                        eprintln!("Warning: failed to parse {}: {e}", path.display());
                    }
                }
            }
        }
    }

    Ok(records)
}

/// Find and parse a single record by ID.
pub fn find_record(data_dir: &Path, record_id: &str) -> Result<MemoryRecord> {
    let subdir = if record_id.starts_with("req-") {
        "requests"
    } else if record_id.starts_with("work-") {
        "works"
    } else if record_id.starts_with("know-") {
        "knowledge"
    } else if record_id.starts_with("dec-") {
        "decisions"
    } else if record_id.starts_with("ins-") {
        "insights"
    } else if record_id.starts_with("evt-") {
        "events"
    } else {
        "works"
    };
    let path = data_dir
        .join("memory")
        .join(subdir)
        .join(format!("{record_id}.md"));

    parse_record(&path)
}

// --- Helpers ---

fn split_frontmatter(content: &str) -> Result<(String, String)> {
    let trimmed = content.trim_start();
    if !trimmed.starts_with("---") {
        anyhow::bail!("No YAML frontmatter found (missing opening ---)");
    }

    let after_first = &trimmed[3..];
    if let Some(end_idx) = after_first.find("\n---") {
        let meta = after_first[..end_idx].trim().to_string();
        let body = after_first[end_idx + 4..].trim().to_string();
        Ok((meta, body))
    } else {
        anyhow::bail!("No closing --- found for frontmatter");
    }
}

fn yaml_str(yaml: &serde_yaml::Value, key: &str) -> Option<String> {
    yaml.get(key).and_then(|v| match v {
        serde_yaml::Value::String(s) => Some(s.clone()),
        serde_yaml::Value::Number(n) => Some(n.to_string()),
        serde_yaml::Value::Bool(b) => Some(b.to_string()),
        _ => None,
    })
}

fn yaml_str_list(yaml: &serde_yaml::Value, key: &str) -> Vec<String> {
    yaml.get(key)
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| match item {
                    serde_yaml::Value::String(s) => Some(s.clone()),
                    _ => None,
                })
                .collect()
        })
        .unwrap_or_default()
}

fn extract_why_hypotheses(yaml: &serde_yaml::Value) -> Vec<String> {
    yaml.get("why")
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| {
                    item.get("hypothesis")
                        .and_then(|h| h.as_str())
                        .map(|s| s.to_string())
                })
                .collect()
        })
        .unwrap_or_default()
}

fn extract_how_steps(yaml: &serde_yaml::Value) -> Vec<String> {
    yaml.get("how")
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| {
                    item.get("goal")
                        .and_then(|g| g.as_str())
                        .map(|s| s.to_string())
                })
                .collect()
        })
        .unwrap_or_default()
}

fn extract_work_fields(
    yaml: &serde_yaml::Value,
) -> (
    Option<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
) {
    let immediate_goal = yaml
        .get("why")
        .and_then(|v| v.get("immediate_goal"))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let actions = yaml
        .get("what")
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| {
                    let action = item.get("action").and_then(|a| a.as_str())?;
                    let output = item.get("output").and_then(|o| o.as_str()).unwrap_or("");
                    if output.is_empty() {
                        Some(action.to_string())
                    } else {
                        Some(format!("{action}: {output}"))
                    }
                })
                .collect()
        })
        .unwrap_or_default();

    let evidence = yaml_str_list(yaml, "evidence");

    let inputs = yaml
        .get("where")
        .and_then(|v| v.get("inputs"))
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| item.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let outputs = yaml
        .get("where")
        .and_then(|v| v.get("outputs"))
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| item.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    (immediate_goal, actions, evidence, inputs, outputs)
}

fn extract_link_targets(yaml: &serde_yaml::Value, key: &str) -> Vec<String> {
    yaml.get(key)
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| {
                    item.get("target_id")
                        .and_then(|t| t.as_str())
                        .map(|s| s.to_string())
                })
                .collect()
        })
        .unwrap_or_default()
}

fn extract_work_causality(yaml: &serde_yaml::Value) -> Vec<String> {
    yaml.get("why")
        .and_then(|v| v.get("causality"))
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| {
                    item.get("target_id")
                        .and_then(|t| t.as_str())
                        .map(|s| s.to_string())
                })
                .collect()
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn write_temp_record(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::with_suffix(".md").unwrap();
        f.write_all(content.as_bytes()).unwrap();
        f.flush().unwrap();
        f
    }

    #[test]
    fn test_parse_request_record() {
        let content = r#"---
id: req-20260226-0001
type: request
who: U06CLS6E694
where: D06CVUV964C
topics:
  - authentication
  - jwt
facet_keys:
  - k/who/u06cls6e694
  - k/what/authentication
why:
  - hypothesis: "SRP violation in auth module"
    confidence: 0.8
    evidence:
      - "mixed concerns in middleware"
how:
  - step_id: s01
    goal: "Extract JWT verifier"
    done: false
    expected_artifacts:
      - src/auth/jwt_verifier.py
created_at: "2026-02-26T22:51:08"
---

# Test request

## What
JWT authentication refactoring
"#;
        let f = write_temp_record(content);
        let record = parse_record(f.path()).unwrap();

        assert_eq!(record.id, "req-20260226-0001");
        assert_eq!(record.record_type, "request");
        assert_eq!(record.who, "U06CLS6E694");
        assert_eq!(record.where_field, "D06CVUV964C");
        assert_eq!(record.topics, vec!["authentication", "jwt"]);
        assert_eq!(record.facet_keys.len(), 2);
        assert_eq!(record.why_hypotheses, vec!["SRP violation in auth module"]);
        assert_eq!(record.how_steps, vec!["Extract JWT verifier"]);
    }

    #[test]
    fn test_parse_work_record() {
        let content = r#"---
id: work-20260226-req-20260226-0001-01
type: work
who: claude
topics:
  - jwt
facet_keys:
  - k/who/claude
why:
  kind: advance_step
  step_ref: "req-20260226-0001#s01"
  immediate_goal: "Extract JWT verifier module"
  causality: []
where:
  inputs:
    - src/auth/middleware.py
  outputs:
    - src/auth/jwt_verifier.py
what:
  - action: "extract_module"
    output: "Created jwt_verifier.py"
evidence:
  - "Tests pass after extraction"
created_at: "2026-02-26T23:00:00"
---

# Work record body
"#;
        let f = write_temp_record(content);
        let record = parse_record(f.path()).unwrap();

        assert_eq!(record.id, "work-20260226-req-20260226-0001-01");
        assert_eq!(record.record_type, "work");
        assert_eq!(
            record.immediate_goal.as_deref(),
            Some("Extract JWT verifier module")
        );
        assert_eq!(record.inputs, vec!["src/auth/middleware.py"]);
        assert_eq!(record.outputs, vec!["src/auth/jwt_verifier.py"]);
        assert_eq!(record.evidence, vec!["Tests pass after extraction"]);
    }

    #[test]
    fn test_search_text_generation() {
        let record = MemoryRecord {
            id: "req-test".into(),
            record_type: "request".into(),
            who: "user".into(),
            where_field: "channel".into(),
            topics: vec!["auth".into(), "jwt".into()],
            facet_keys: vec![],
            created_at: String::new(),
            body: String::new(),
            what: Some("Refactor authentication".into()),
            why_hypotheses: vec!["SRP violation".into()],
            how_steps: vec!["Extract JWT".into()],
            immediate_goal: None,
            actions: vec![],
            evidence: vec![],
            inputs: vec![],
            outputs: vec![],
            link_targets: vec![],
            causal_targets: vec![],
        };

        let text = record.to_search_text();
        assert!(text.contains("Refactor authentication"));
        assert!(text.contains("auth"));
        assert!(text.contains("SRP violation"));
        assert!(text.contains("Extract JWT"));
    }
}
