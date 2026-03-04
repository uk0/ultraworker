//! Lightweight Qdrant client with local binary autostart + Docker fallback.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::process::Stdio;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};
use reqwest::blocking::Client;
use reqwest::StatusCode;
use serde_json::{json, Value};

const DEFAULT_QDRANT_ENDPOINT: &str = "http://127.0.0.1:6333";
const DEFAULT_QDRANT_PORT: u16 = 6333;
const DEFAULT_QDRANT_IMAGE: &str = "qdrant/qdrant:latest";
const DEFAULT_COLLECTION: &str = "memory_records_v1";
const DEFAULT_START_TIMEOUT_SECS: u64 = 45;

#[derive(Debug, Clone)]
pub struct DenseHit {
    pub id: String,
    pub score: f64,
    pub payload: Value,
}

#[derive(Debug, Clone)]
pub struct QdrantPoint {
    pub id: String,
    pub vector: Vec<f64>,
    pub payload: Value,
}

#[derive(Debug, Clone)]
struct QdrantConfig {
    endpoint: String,
    port: u16,
    image: String,
    autostart: bool,
    local_autostart: bool,
    docker_autostart: bool,
    start_timeout_secs: u64,
    storage_dir: PathBuf,
    grpc_port: u16,
    local_bin: String,
    local_args: Vec<String>,
    local_log_path: PathBuf,
    collection: String,
    container_name: String,
}

pub struct QdrantStore {
    client: Client,
    cfg: QdrantConfig,
}

impl QdrantStore {
    pub fn new(index_dir: &Path) -> Self {
        let storage_dir = std::env::var("MEMORY_SEARCH_QDRANT_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|_| index_dir.join("qdrant").join("storage"));
        let port = std::env::var("MEMORY_SEARCH_QDRANT_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(DEFAULT_QDRANT_PORT);
        let local_log_path = std::env::var("MEMORY_SEARCH_QDRANT_LOG_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|_| index_dir.join("qdrant.log"));
        let local_args = std::env::var("MEMORY_SEARCH_QDRANT_ARGS")
            .ok()
            .map(|v| v.split_whitespace().map(str::to_string).collect())
            .unwrap_or_default();

        let cfg = QdrantConfig {
            endpoint: std::env::var("MEMORY_SEARCH_QDRANT_ENDPOINT")
                .unwrap_or_else(|_| DEFAULT_QDRANT_ENDPOINT.to_string()),
            port,
            image: std::env::var("MEMORY_SEARCH_QDRANT_DOCKER_IMAGE")
                .unwrap_or_else(|_| DEFAULT_QDRANT_IMAGE.to_string()),
            autostart: env_bool("MEMORY_SEARCH_QDRANT_AUTOSTART", true),
            local_autostart: env_bool("MEMORY_SEARCH_QDRANT_LOCAL_AUTOSTART", true),
            docker_autostart: env_bool("MEMORY_SEARCH_QDRANT_DOCKER_AUTOSTART", true),
            start_timeout_secs: std::env::var("MEMORY_SEARCH_QDRANT_START_TIMEOUT_SECS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(DEFAULT_START_TIMEOUT_SECS),
            storage_dir: storage_dir.clone(),
            grpc_port: std::env::var("MEMORY_SEARCH_QDRANT_GRPC_PORT")
                .ok()
                .and_then(|v| v.parse::<u16>().ok())
                .unwrap_or(port.saturating_add(1)),
            local_bin: std::env::var("MEMORY_SEARCH_QDRANT_BIN")
                .unwrap_or_else(|_| "qdrant".to_string()),
            local_args,
            local_log_path,
            collection: std::env::var("MEMORY_SEARCH_QDRANT_COLLECTION")
                .unwrap_or_else(|_| DEFAULT_COLLECTION.to_string()),
            container_name: container_name_from_path("memory-search-qdrant", &storage_dir),
        };

        let client = Client::builder()
            .timeout(Duration::from_secs(20))
            .build()
            .expect("reqwest client must initialize");

        Self { client, cfg }
    }

    pub fn ensure_collection(&self, vector_size: usize) -> Result<()> {
        self.ensure_running()?;
        match self.collection_vector_size()? {
            Some(existing) if existing == vector_size => Ok(()),
            Some(_) => {
                self.recreate_collection(vector_size)?;
                Ok(())
            }
            None => {
                self.create_collection(vector_size)?;
                Ok(())
            }
        }
    }

    pub fn recreate_collection(&self, vector_size: usize) -> Result<()> {
        self.ensure_running()?;
        self.delete_collection().ok();
        self.create_collection(vector_size)
    }

    pub fn upsert_points(&self, points: &[QdrantPoint], vector_size: usize) -> Result<()> {
        if points.is_empty() {
            return Ok(());
        }
        self.ensure_collection(vector_size)?;
        let upsert_points: Vec<Value> = points
            .iter()
            .map(|p| {
                json!({
                    "id": qdrant_numeric_id(&p.id),
                    "vector": p.vector,
                    "payload": p.payload,
                })
            })
            .collect();

        let url = format!(
            "{}/collections/{}/points?wait=true",
            self.cfg.endpoint, self.cfg.collection
        );
        let resp = self
            .client
            .put(&url)
            .json(&json!({ "points": upsert_points }))
            .send()
            .context("qdrant upsert request failed")?;
        resp.error_for_status()
            .context("qdrant upsert returned error status")?;
        Ok(())
    }

    pub fn upsert_point(&self, point: &QdrantPoint) -> Result<()> {
        self.upsert_points(std::slice::from_ref(point), point.vector.len())
    }

    pub fn delete_point(&self, id: &str) -> Result<()> {
        self.ensure_running()?;
        let url = format!(
            "{}/collections/{}/points/delete?wait=true",
            self.cfg.endpoint, self.cfg.collection
        );
        let resp = self
            .client
            .post(&url)
            .json(&json!({ "points": [qdrant_numeric_id(id)] }))
            .send()
            .context("qdrant delete request failed")?;

        if resp.status() == StatusCode::NOT_FOUND {
            return Ok(());
        }
        resp.error_for_status()
            .context("qdrant delete returned error status")?;
        Ok(())
    }

    pub fn search(&self, vector: &[f64], limit: usize) -> Result<Vec<DenseHit>> {
        self.ensure_running()?;
        let url = format!(
            "{}/collections/{}/points/search",
            self.cfg.endpoint, self.cfg.collection
        );
        let resp = self
            .client
            .post(&url)
            .json(&json!({
                "vector": vector,
                "limit": limit,
                "with_payload": true,
            }))
            .send()
            .context("qdrant search request failed")?;

        if resp.status() == StatusCode::NOT_FOUND {
            return Ok(vec![]);
        }
        let value: Value = resp
            .error_for_status()
            .context("qdrant search returned error status")?
            .json()
            .context("qdrant search response parse failed")?;

        let mut hits = Vec::new();
        if let Some(items) = value.get("result").and_then(|v| v.as_array()) {
            for item in items {
                let payload = item.get("payload").cloned().unwrap_or_else(|| json!({}));
                let id = payload
                    .get("record_id")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
                    .filter(|s| !s.is_empty())
                    .or_else(|| point_id_to_string(item.get("id")))
                    .unwrap_or_default();
                if id.is_empty() {
                    continue;
                }
                let score = item.get("score").and_then(|s| s.as_f64()).unwrap_or(0.0);
                hits.push(DenseHit { id, score, payload });
            }
        }
        Ok(hits)
    }

    pub fn count_points(&self) -> Result<usize> {
        self.ensure_running()?;
        let url = format!(
            "{}/collections/{}/points/count",
            self.cfg.endpoint, self.cfg.collection
        );
        let resp = self
            .client
            .post(&url)
            .json(&json!({ "exact": false }))
            .send()
            .context("qdrant count request failed")?;

        if resp.status() == StatusCode::NOT_FOUND {
            return Ok(0);
        }
        let value: Value = resp
            .error_for_status()
            .context("qdrant count returned error status")?
            .json()
            .context("qdrant count response parse failed")?;
        Ok(value
            .pointer("/result/count")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as usize)
    }

    fn ensure_running(&self) -> Result<()> {
        if self.is_healthy() {
            return Ok(());
        }
        if !self.cfg.autostart {
            bail!(
                "Qdrant is not reachable at {} and autostart is disabled",
                self.cfg.endpoint
            );
        }

        let mut start_errors: Vec<String> = Vec::new();

        if self.cfg.local_autostart {
            match self.start_local_qdrant() {
                Ok(()) => {
                    if self.wait_until_healthy().is_ok() {
                        return Ok(());
                    }
                    start_errors.push(format!(
                        "local qdrant started but endpoint was not healthy within {}s",
                        self.cfg.start_timeout_secs
                    ));
                }
                Err(err) => start_errors.push(format!("local qdrant start failed: {err}")),
            }
        }

        if self.cfg.docker_autostart {
            match self.start_docker_qdrant() {
                Ok(()) => {
                    if self.wait_until_healthy().is_ok() {
                        return Ok(());
                    }
                    start_errors.push(format!(
                        "docker qdrant started but endpoint was not healthy within {}s",
                        self.cfg.start_timeout_secs
                    ));
                }
                Err(err) => start_errors.push(format!("docker qdrant start failed: {err}")),
            }
        }

        let hints = [
            "install local qdrant binary from GitHub releases (e.g. `qdrant-aarch64-apple-darwin.tar.gz`)".to_string(),
            format!(
                "run manually: `QDRANT__STORAGE__STORAGE_PATH={} QDRANT__SERVICE__HTTP_PORT={} qdrant`",
                self.cfg.storage_dir.display(),
                self.cfg.port
            ),
            "or enable Docker and keep `MEMORY_SEARCH_QDRANT_DOCKER_AUTOSTART=true`".to_string(),
        ]
        .join("; ");

        bail!(
            "Qdrant endpoint is still unavailable at {}. Attempts: {}. Hints: {}",
            self.cfg.endpoint,
            if start_errors.is_empty() {
                "none".to_string()
            } else {
                start_errors.join(" | ")
            },
            hints
        )
    }

    fn wait_until_healthy(&self) -> Result<()> {
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(self.cfg.start_timeout_secs) {
            if self.is_healthy() {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(1000));
        }
        bail!(
            "qdrant did not become healthy within {} seconds ({})",
            self.cfg.start_timeout_secs,
            self.cfg.endpoint
        )
    }

    fn start_local_qdrant(&self) -> Result<()> {
        let qdrant_bin = resolve_binary(&self.cfg.local_bin)
            .ok_or_else(|| anyhow!("qdrant binary '{}' not found in PATH", self.cfg.local_bin))?;

        std::fs::create_dir_all(&self.cfg.storage_dir)
            .with_context(|| format!("failed to create {}", self.cfg.storage_dir.display()))?;
        if let Some(parent) = self.cfg.local_log_path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }

        let log_file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.cfg.local_log_path)
            .with_context(|| {
                format!(
                    "failed to open qdrant log file {}",
                    self.cfg.local_log_path.display()
                )
            })?;
        let log_file_err = log_file
            .try_clone()
            .context("failed to clone qdrant log file")?;

        let mut cmd = Command::new(qdrant_bin);
        cmd.args(&self.cfg.local_args);
        cmd.env(
            "QDRANT__STORAGE__STORAGE_PATH",
            self.cfg.storage_dir.to_string_lossy().to_string(),
        );
        cmd.env("QDRANT__SERVICE__HTTP_PORT", self.cfg.port.to_string());
        cmd.env("QDRANT__SERVICE__GRPC_PORT", self.cfg.grpc_port.to_string());
        cmd.stdout(Stdio::from(log_file));
        cmd.stderr(Stdio::from(log_file_err));

        let child = cmd.spawn().context("failed to spawn local qdrant")?;
        eprintln!(
            "[memory-search] started local qdrant pid={} http_port={} storage={} log={}",
            child.id(),
            self.cfg.port,
            self.cfg.storage_dir.display(),
            self.cfg.local_log_path.display()
        );
        Ok(())
    }

    fn start_docker_qdrant(&self) -> Result<()> {
        if which("docker").is_none() {
            bail!("docker command not found");
        }

        std::fs::create_dir_all(&self.cfg.storage_dir)
            .with_context(|| format!("failed to create {}", self.cfg.storage_dir.display()))?;
        let _ = Command::new("docker")
            .args(["rm", "-f", &self.cfg.container_name])
            .status();

        let port_mapping = format!("127.0.0.1:{}:6333", self.cfg.port);
        let storage_mapping = format!("{}:/qdrant/storage", self.cfg.storage_dir.display());
        let output = Command::new("docker")
            .args([
                "run",
                "-d",
                "--rm",
                "--name",
                &self.cfg.container_name,
                "-p",
                &port_mapping,
                "-v",
                &storage_mapping,
                &self.cfg.image,
            ])
            .output()
            .context("failed to run qdrant docker container")?;

        if !output.status.success() {
            let err = String::from_utf8_lossy(&output.stderr);
            bail!("qdrant docker start failed: {err}");
        }
        Ok(())
    }

    fn is_healthy(&self) -> bool {
        for path in ["/healthz", "/readyz", "/"] {
            let url = format!("{}{}", self.cfg.endpoint, path);
            if let Ok(resp) = self.client.get(&url).send() {
                if resp.status().is_success() {
                    return true;
                }
            }
        }
        false
    }

    fn collection_vector_size(&self) -> Result<Option<usize>> {
        self.ensure_running()?;
        let url = format!("{}/collections/{}", self.cfg.endpoint, self.cfg.collection);
        let resp = self
            .client
            .get(&url)
            .send()
            .context("qdrant collection info request failed")?;

        if resp.status() == StatusCode::NOT_FOUND {
            return Ok(None);
        }
        let value: Value = resp
            .error_for_status()
            .context("qdrant collection info returned error status")?
            .json()
            .context("qdrant collection info parse failed")?;

        let size = value
            .pointer("/result/config/params/vectors/size")
            .and_then(|v| v.as_u64())
            .or_else(|| {
                value
                    .pointer("/result/config/params/vectors/default/size")
                    .and_then(|v| v.as_u64())
            });

        Ok(size.map(|v| v as usize))
    }

    fn delete_collection(&self) -> Result<()> {
        let url = format!("{}/collections/{}", self.cfg.endpoint, self.cfg.collection);
        let resp = self
            .client
            .delete(&url)
            .send()
            .context("qdrant delete collection request failed")?;
        if resp.status() == StatusCode::NOT_FOUND {
            return Ok(());
        }
        resp.error_for_status()
            .context("qdrant delete collection returned error status")?;
        Ok(())
    }

    fn create_collection(&self, vector_size: usize) -> Result<()> {
        let url = format!("{}/collections/{}", self.cfg.endpoint, self.cfg.collection);
        let resp = self
            .client
            .put(&url)
            .json(&json!({
                "vectors": {
                    "size": vector_size,
                    "distance": "Cosine"
                }
            }))
            .send()
            .context("qdrant create collection request failed")?;
        resp.error_for_status()
            .context("qdrant create collection returned error status")?;
        Ok(())
    }
}

fn env_bool(key: &str, default: bool) -> bool {
    match std::env::var(key) {
        Ok(v) => matches!(v.as_str(), "1" | "true" | "TRUE" | "yes" | "YES"),
        Err(_) => default,
    }
}

fn which(binary: &str) -> Option<PathBuf> {
    std::env::var_os("PATH").and_then(|paths| {
        std::env::split_paths(&paths)
            .map(|dir| dir.join(binary))
            .find(|path| path.is_file())
    })
}

fn resolve_binary(binary: &str) -> Option<PathBuf> {
    let path = PathBuf::from(binary);
    if path.components().count() > 1 {
        if path.is_file() {
            return Some(path);
        }
        return None;
    }
    which(binary)
}

fn container_name_from_path(prefix: &str, path: &Path) -> String {
    let mut hasher = DefaultHasher::new();
    path.to_string_lossy().hash(&mut hasher);
    format!("{prefix}-{:x}", hasher.finish())
}

fn qdrant_numeric_id(record_id: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    record_id.hash(&mut hasher);
    hasher.finish()
}

fn point_id_to_string(value: Option<&Value>) -> Option<String> {
    match value {
        Some(Value::String(s)) => Some(s.clone()),
        Some(Value::Number(n)) => Some(n.to_string()),
        Some(other) => Some(other.to_string()),
        None => None,
    }
}

pub fn qdrant_score_to_probability(score: f64) -> f64 {
    if score.is_nan() {
        return 0.0;
    }
    score.clamp(0.0, 1.0)
}

pub fn payload_for_record(record: &crate::types::MemoryRecord) -> Value {
    json!({
        "record_id": record.id,
        "record_type": record.record_type,
        "topics": record.topics,
        "facet_keys": record.facet_keys,
        "created_at": record.created_at,
    })
}

pub fn require_embedding_dimension(vectors: &[Vec<f64>]) -> Result<usize> {
    let first = vectors
        .first()
        .ok_or_else(|| anyhow!("embedding result is empty"))?;
    if first.is_empty() {
        bail!("embedding dimension is zero");
    }
    let dim = first.len();
    if vectors.iter().any(|v| v.len() != dim) {
        bail!("inconsistent embedding dimensions detected");
    }
    Ok(dim)
}
