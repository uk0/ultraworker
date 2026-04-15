//! memory-search: Hybrid search MCP server for agent long-term memory.
//!
//! Modes:
//!   serve   — Run as MCP server (stdio JSON-RPC)
//!   search  — CLI search
//!   index   — Index a single record
//!   remove  — Remove a record from index
//!   rebuild — Rebuild entire index
//!   stats   — Show index statistics

mod facet;
mod index;
mod qdrant;
mod record;
mod search;
mod tei;
mod types;

use std::io::{BufRead, Write};
use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use crate::search::HybridEngine;

#[derive(Parser)]
#[command(name = "memory-search", version, about = "Hybrid search for agent LTM")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run as MCP server (stdio JSON-RPC)
    Serve {
        #[arg(long)]
        data_dir: PathBuf,
    },
    /// Search memory records
    Search {
        /// Search query
        query: String,
        #[arg(long)]
        data_dir: PathBuf,
        #[arg(long, default_value = "10")]
        top_k: usize,
        #[arg(long, default_value = "recall")]
        mode: String,
        /// Output as JSON
        #[arg(long)]
        json: bool,
    },
    /// Index a single record
    Index {
        /// Record ID (e.g., req-20260226-0001)
        record_id: String,
        #[arg(long)]
        data_dir: PathBuf,
    },
    /// Remove a record from the index
    Remove {
        /// Record ID
        record_id: String,
        #[arg(long)]
        data_dir: PathBuf,
    },
    /// Rebuild the entire index
    Rebuild {
        #[arg(long)]
        data_dir: PathBuf,
    },
    /// Show index statistics
    Stats {
        #[arg(long)]
        data_dir: PathBuf,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Serve { data_dir } => run_mcp_server(&data_dir),
        Commands::Search {
            query,
            data_dir,
            top_k,
            mode,
            json,
        } => cmd_search(&query, &data_dir, top_k, &mode, json),
        Commands::Index {
            record_id,
            data_dir,
        } => cmd_index(&record_id, &data_dir),
        Commands::Remove {
            record_id,
            data_dir,
        } => cmd_remove(&record_id, &data_dir),
        Commands::Rebuild { data_dir } => cmd_rebuild(&data_dir),
        Commands::Stats { data_dir } => cmd_stats(&data_dir),
    }
}

// --- CLI Commands ---

fn cmd_search(
    query: &str,
    data_dir: &PathBuf,
    top_k: usize,
    mode: &str,
    json_output: bool,
) -> Result<()> {
    let index_dir = data_dir.join("memory").join("index");
    let mut engine = HybridEngine::load(&index_dir);
    engine.ensure_engine_current(data_dir)?;

    // Load records for keyword/facet search
    let records = record::load_all_records(data_dir)?;
    for r in &records {
        engine.facet_index.add(&r.id, &r.facet_keys);
        engine.records.insert(r.id.clone(), r.clone());
    }

    let results = engine.search(query, top_k, mode);

    if json_output {
        println!("{}", serde_json::to_string_pretty(&results)?);
    } else {
        if results.is_empty() {
            println!("No results found.");
        } else {
            for (i, r) in results.iter().enumerate() {
                println!(
                    "{}. {} [{}] score={:.4} (vec={:.4} facet={:.1} kw={:.1})",
                    i + 1,
                    r.record_id,
                    r.record_type,
                    r.score,
                    r.vector_score,
                    r.facet_score,
                    r.keyword_score,
                );
                if !r.matched_facets.is_empty() {
                    println!("   facets: {}", r.matched_facets.join(", "));
                }
                if !r.snippet.is_empty() {
                    println!("   {}", r.snippet.chars().take(120).collect::<String>());
                }
            }
        }
    }
    Ok(())
}

fn cmd_index(record_id: &str, data_dir: &PathBuf) -> Result<()> {
    let index_dir = data_dir.join("memory").join("index");
    let mut engine = HybridEngine::load(&index_dir);
    engine.ensure_engine_current(data_dir)?;

    // Load all records to have proper facet context
    let records = record::load_all_records(data_dir)?;
    for r in &records {
        engine.facet_index.add(&r.id, &r.facet_keys);
    }

    let rec = record::find_record(data_dir, record_id)?;
    engine.index_record(&rec)?;

    let output = serde_json::json!({
        "success": true,
        "record_id": record_id,
        "facets_extracted": rec.facet_keys.len(),
        "vector_indexed": true,
    });
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn cmd_remove(record_id: &str, data_dir: &PathBuf) -> Result<()> {
    let index_dir = data_dir.join("memory").join("index");
    let mut engine = HybridEngine::load(&index_dir);
    engine.ensure_engine_current(data_dir)?;
    engine.remove_record(record_id)?;

    let output = serde_json::json!({
        "success": true,
        "record_id": record_id,
    });
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn cmd_rebuild(data_dir: &PathBuf) -> Result<()> {
    let index_dir = data_dir.join("memory").join("index");
    let start = std::time::Instant::now();

    let mut engine = HybridEngine::load(&index_dir);
    let count = engine.rebuild(data_dir)?;
    engine.save(&index_dir)?;

    let duration = start.elapsed();
    let output = serde_json::json!({
        "records_indexed": count,
        "vocabulary_size": engine.vocabulary_size(),
        "facets_count": engine.facet_index.facet_count(),
        "vector_points": engine.vector_count(),
        "duration_ms": duration.as_millis(),
    });
    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}

fn cmd_stats(data_dir: &PathBuf) -> Result<()> {
    let index_dir = data_dir.join("memory").join("index");

    let meta_path = index_dir.join("rust_index_meta.json");
    if meta_path.exists() {
        let meta_str = std::fs::read_to_string(&meta_path)?;
        let meta: types::IndexMeta = serde_json::from_str(&meta_str)?;

        let req_count = count_files(&data_dir.join("memory").join("requests"), "req-");
        let work_count = count_files(&data_dir.join("memory").join("works"), "work-");

        let output = serde_json::json!({
            "request_count": req_count,
            "work_count": work_count,
            "vocabulary_size": meta.vocabulary_size,
            "facet_count": meta.facet_count,
            "records_indexed": meta.record_count,
            "vector_points": meta.vector_points,
            "engine_version": meta.engine_version,
            "embedding_model": meta.embedding_model,
            "index_built_at": meta.built_at,
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        let req_count = count_files(&data_dir.join("memory").join("requests"), "req-");
        let work_count = count_files(&data_dir.join("memory").join("works"), "work-");

        let output = serde_json::json!({
            "request_count": req_count,
            "work_count": work_count,
            "index_built": false,
            "message": "No index found. Run `memory-search rebuild` first.",
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
    }
    Ok(())
}

fn count_files(dir: &std::path::Path, prefix: &str) -> usize {
    if !dir.exists() {
        return 0;
    }
    std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .filter_map(|e| e.ok())
                .filter(|e| e.file_name().to_string_lossy().starts_with(prefix))
                .count()
        })
        .unwrap_or(0)
}

// --- MCP Server (JSON-RPC over stdio) ---

fn run_mcp_server(data_dir: &std::path::Path) -> Result<()> {
    eprintln!(
        "[memory-search] Starting MCP server, data_dir={}",
        data_dir.display()
    );

    let index_dir = data_dir.join("memory").join("index");
    let mut engine = HybridEngine::load(&index_dir);
    if let Err(e) = engine.ensure_engine_current(data_dir) {
        eprintln!("[memory-search] Warning: auto-migration failed: {e}");
    }

    // Load records
    match record::load_all_records(data_dir) {
        Ok(records) => {
            for r in &records {
                engine.facet_index.add(&r.id, &r.facet_keys);
                engine.records.insert(r.id.clone(), r.clone());
            }
            eprintln!("[memory-search] Loaded {} records", engine.records.len());
        }
        Err(e) => {
            eprintln!("[memory-search] Warning: failed to load records: {e}");
        }
    }

    let stdin = std::io::stdin();
    let stdout = std::io::stdout();

    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }

        let request: serde_json::Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("[memory-search] Invalid JSON: {e}");
                continue;
            }
        };

        let response = handle_jsonrpc(&request, &mut engine, data_dir, &index_dir);

        // Don't send response for notifications (no id)
        if response.is_null() {
            continue;
        }

        let mut out = stdout.lock();
        serde_json::to_writer(&mut out, &response)?;
        out.write_all(b"\n")?;
        out.flush()?;
    }

    Ok(())
}

fn handle_jsonrpc(
    request: &serde_json::Value,
    engine: &mut HybridEngine,
    data_dir: &std::path::Path,
    index_dir: &std::path::Path,
) -> serde_json::Value {
    let id = request
        .get("id")
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    let method = request.get("method").and_then(|m| m.as_str()).unwrap_or("");

    match method {
        "initialize" => {
            serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": { "listChanged": false }
                    },
                    "serverInfo": {
                        "name": "memory-search",
                        "version": env!("CARGO_PKG_VERSION")
                    }
                }
            })
        }
        "notifications/initialized" | "notifications/cancelled" => serde_json::Value::Null,
        "tools/list" => {
            serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {
                    "tools": tool_definitions()
                }
            })
        }
        "tools/call" => {
            let params = request.get("params").cloned().unwrap_or_default();
            let tool_name = params.get("name").and_then(|n| n.as_str()).unwrap_or("");
            let args = params.get("arguments").cloned().unwrap_or_default();

            let result = handle_tool_call(tool_name, &args, engine, data_dir, index_dir);

            match result {
                Ok(text) => serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": {
                        "content": [{ "type": "text", "text": text }],
                        "isError": false
                    }
                }),
                Err(e) => serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": {
                        "content": [{ "type": "text", "text": format!("Error: {e}") }],
                        "isError": true
                    }
                }),
            }
        }
        _ => {
            // For unknown methods, only send error if it has an id (not a notification)
            if id.is_null() {
                serde_json::Value::Null
            } else {
                serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "error": {
                        "code": -32601,
                        "message": format!("Method not found: {method}")
                    }
                })
            }
        }
    }
}

fn tool_definitions() -> serde_json::Value {
    serde_json::json!([
        {
            "name": "memory_search",
            "description": "Search long-term memory records using hybrid search (facet + bb25 sparse + BGE-M3 dense via Qdrant). Returns ranked results with scores.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language, topics, person IDs, or facet keys like k/what/auth)"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 10)",
                        "default": 10
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["recall", "insight"],
                        "description": "recall: compact results. insight: expanded with graph traversal",
                        "default": "recall"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "memory_index_record",
            "description": "Add or update a record in the search index. Reads the record file from data/memory/ and indexes it.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "record_id": {
                        "type": "string",
                        "description": "Record ID (e.g., req-20260226-0001 or work-20260226-req-20260226-0001-01)"
                    }
                },
                "required": ["record_id"]
            }
        },
        {
            "name": "memory_remove_record",
            "description": "Remove a record from the search index.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "record_id": {
                        "type": "string",
                        "description": "Record ID to remove"
                    }
                },
                "required": ["record_id"]
            }
        },
        {
            "name": "memory_rebuild",
            "description": "Rebuild the entire search index from all record files. Use after bulk changes or when index is corrupted.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "memory_stats",
            "description": "Get search index statistics: record counts, vocabulary size, facet counts.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ])
}

fn handle_tool_call(
    tool_name: &str,
    args: &serde_json::Value,
    engine: &mut HybridEngine,
    data_dir: &std::path::Path,
    index_dir: &std::path::Path,
) -> Result<String> {
    match tool_name {
        "memory_search" => {
            engine.ensure_engine_current(data_dir)?;
            let query = args.get("query").and_then(|q| q.as_str()).unwrap_or("");
            let top_k = args.get("top_k").and_then(|t| t.as_u64()).unwrap_or(10) as usize;
            let mode = args
                .get("mode")
                .and_then(|m| m.as_str())
                .unwrap_or("recall");

            let results = engine.search(query, top_k, mode);
            Ok(serde_json::to_string_pretty(&results)?)
        }
        "memory_index_record" => {
            engine.ensure_engine_current(data_dir)?;
            let record_id = args.get("record_id").and_then(|r| r.as_str()).unwrap_or("");

            let rec = record::find_record(data_dir, record_id)?;
            engine.index_record(&rec)?;

            Ok(serde_json::to_string(&serde_json::json!({
                "success": true,
                "record_id": record_id,
                "facets_extracted": rec.facet_keys.len(),
                "vector_indexed": true,
            }))?)
        }
        "memory_remove_record" => {
            engine.ensure_engine_current(data_dir)?;
            let record_id = args.get("record_id").and_then(|r| r.as_str()).unwrap_or("");

            engine.remove_record(record_id)?;

            Ok(serde_json::to_string(&serde_json::json!({
                "success": true,
                "record_id": record_id,
            }))?)
        }
        "memory_rebuild" => {
            let start = std::time::Instant::now();
            let count = engine.rebuild(data_dir)?;
            engine.save(index_dir)?;
            let duration = start.elapsed();

            Ok(serde_json::to_string_pretty(&serde_json::json!({
                "records_indexed": count,
                "vocabulary_size": engine.vocabulary_size(),
                "facets_count": engine.facet_index.facet_count(),
                "vector_points": engine.vector_count(),
                "duration_ms": duration.as_millis(),
            }))?)
        }
        "memory_stats" => {
            engine.ensure_engine_current(data_dir)?;
            let req_count = count_files(&data_dir.join("memory").join("requests"), "req-");
            let work_count = count_files(&data_dir.join("memory").join("works"), "work-");

            Ok(serde_json::to_string_pretty(&serde_json::json!({
                "request_count": req_count,
                "work_count": work_count,
                "indexed_records": engine.vector_count(),
                "vocabulary_size": engine.vocabulary_size(),
                "facet_count": engine.facet_index.facet_count(),
            }))?)
        }
        _ => anyhow::bail!("Unknown tool: {tool_name}"),
    }
}
