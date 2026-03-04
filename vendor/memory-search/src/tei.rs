//! text-embedding-inference (TEI) client with optional Docker autostart.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::process::Stdio;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};
use reqwest::blocking::Client;
use serde_json::{json, Value};

const DEFAULT_ENDPOINT: &str = "http://127.0.0.1:8080";
const DEFAULT_PORT: u16 = 8080;
const DEFAULT_MODEL: &str = "BAAI/bge-m3";
const DEFAULT_IMAGE: &str = "ghcr.io/huggingface/text-embeddings-inference:cpu-latest";
const DEFAULT_START_TIMEOUT_SECS: u64 = 180;
const DEFAULT_REQUEST_TIMEOUT_SECS: u64 = 30;

#[derive(Debug, Clone)]
struct TeiConfig {
    endpoint: String,
    port: u16,
    model: String,
    image: String,
    autostart: bool,
    local_autostart: bool,
    docker_autostart: bool,
    start_timeout_secs: u64,
    cache_dir: PathBuf,
    router_bin: String,
    router_args: Vec<String>,
    router_log_path: PathBuf,
    container_name: String,
}

pub struct TeiClient {
    client: Client,
    cfg: TeiConfig,
}

impl TeiClient {
    pub fn new(index_dir: &Path) -> Self {
        let cache_dir = std::env::var("MEMORY_SEARCH_TEI_CACHE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| index_dir.join("tei-cache"));
        let router_log_path = std::env::var("MEMORY_SEARCH_TEI_LOG_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|_| index_dir.join("tei-router.log"));
        let router_args = std::env::var("MEMORY_SEARCH_TEI_ARGS")
            .ok()
            .map(|v| v.split_whitespace().map(str::to_string).collect())
            .unwrap_or_default();
        let cfg = TeiConfig {
            endpoint: std::env::var("MEMORY_SEARCH_TEI_ENDPOINT")
                .unwrap_or_else(|_| DEFAULT_ENDPOINT.to_string()),
            port: std::env::var("MEMORY_SEARCH_TEI_PORT")
                .ok()
                .and_then(|v| v.parse::<u16>().ok())
                .unwrap_or(DEFAULT_PORT),
            model: std::env::var("MEMORY_SEARCH_TEI_MODEL")
                .unwrap_or_else(|_| DEFAULT_MODEL.to_string()),
            image: std::env::var("MEMORY_SEARCH_TEI_DOCKER_IMAGE")
                .unwrap_or_else(|_| DEFAULT_IMAGE.to_string()),
            autostart: env_bool("MEMORY_SEARCH_TEI_AUTOSTART", true),
            local_autostart: env_bool("MEMORY_SEARCH_TEI_LOCAL_AUTOSTART", true),
            docker_autostart: env_bool("MEMORY_SEARCH_TEI_DOCKER_AUTOSTART", true),
            start_timeout_secs: std::env::var("MEMORY_SEARCH_TEI_START_TIMEOUT_SECS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(DEFAULT_START_TIMEOUT_SECS),
            cache_dir: cache_dir.clone(),
            router_bin: std::env::var("MEMORY_SEARCH_TEI_BIN")
                .unwrap_or_else(|_| "text-embeddings-router".to_string()),
            router_args,
            router_log_path,
            container_name: container_name_from_path("memory-search-tei", &cache_dir),
        };
        let request_timeout = std::env::var("MEMORY_SEARCH_TEI_REQUEST_TIMEOUT_SECS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(DEFAULT_REQUEST_TIMEOUT_SECS);

        let client = Client::builder()
            .timeout(Duration::from_secs(request_timeout))
            .build()
            .expect("reqwest client must initialize");

        Self { client, cfg }
    }

    pub fn model_name(&self) -> &str {
        &self.cfg.model
    }

    pub fn embed(&self, input: &str) -> Result<Vec<f64>> {
        let embeddings = self.embed_batch(&[input.to_string()])?;
        embeddings
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("embedding response is empty"))
    }

    pub fn embed_batch(&self, inputs: &[String]) -> Result<Vec<Vec<f64>>> {
        if inputs.is_empty() {
            return Ok(vec![]);
        }
        self.ensure_running()?;
        match self.embed_via_embed_route(inputs) {
            Ok(v) => Ok(v),
            Err(primary_err) => {
                // Some TEI versions reject array payloads on /embed.
                // Fallback: single /embed calls, then OpenAI-compatible route.
                match self.embed_via_embed_single_loop(inputs) {
                    Ok(v) => Ok(v),
                    Err(_) => self.embed_via_openai_route(inputs).map_err(|_| primary_err),
                }
            }
        }
    }

    fn embed_via_embed_route(&self, inputs: &[String]) -> Result<Vec<Vec<f64>>> {
        let url = format!("{}/embed", self.cfg.endpoint);
        let body = if inputs.len() == 1 {
            json!({ "inputs": inputs[0] })
        } else {
            json!({ "inputs": inputs })
        };

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .context("TEI /embed request failed")?
            .error_for_status()
            .context("TEI /embed returned error status")?;
        let value: Value = resp.json().context("TEI /embed response parse failed")?;
        parse_embed_route_response(&value)
    }

    fn embed_via_openai_route(&self, inputs: &[String]) -> Result<Vec<Vec<f64>>> {
        let url = format!("{}/v1/embeddings", self.cfg.endpoint);
        let resp = self
            .client
            .post(&url)
            .json(&json!({
                "model": self.cfg.model,
                "input": inputs,
            }))
            .send()
            .context("TEI /v1/embeddings request failed")?
            .error_for_status()
            .context("TEI /v1/embeddings returned error status")?;
        let value: Value = resp
            .json()
            .context("TEI /v1/embeddings response parse failed")?;
        let mut vectors = Vec::new();
        if let Some(data) = value.get("data").and_then(|v| v.as_array()) {
            for item in data {
                let embedding = item
                    .get("embedding")
                    .ok_or_else(|| anyhow!("missing embedding in /v1/embeddings data item"))?;
                vectors.push(parse_vector(embedding)?);
            }
        }
        if vectors.is_empty() {
            bail!("TEI /v1/embeddings returned empty data");
        }
        Ok(vectors)
    }

    fn embed_via_embed_single_loop(&self, inputs: &[String]) -> Result<Vec<Vec<f64>>> {
        let mut vectors = Vec::with_capacity(inputs.len());
        for text in inputs {
            vectors.push(self.embed_via_embed_single(text)?);
        }
        Ok(vectors)
    }

    fn embed_via_embed_single(&self, input: &str) -> Result<Vec<f64>> {
        let url = format!("{}/embed", self.cfg.endpoint);
        let resp = self
            .client
            .post(&url)
            .json(&json!({ "inputs": input }))
            .send()
            .context("TEI /embed(single) request failed")?
            .error_for_status()
            .context("TEI /embed(single) returned error status")?;
        let value: Value = resp
            .json()
            .context("TEI /embed(single) response parse failed")?;
        let vectors = parse_embed_route_response(&value)?;
        vectors
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("TEI /embed(single) returned empty embedding"))
    }

    fn ensure_running(&self) -> Result<()> {
        if self.is_ready() {
            return Ok(());
        }
        if !self.cfg.autostart {
            bail!(
                "TEI endpoint is not reachable at {} and autostart is disabled",
                self.cfg.endpoint
            );
        }

        let mut start_errors: Vec<String> = Vec::new();

        if self.cfg.local_autostart {
            match self.start_local_router() {
                Ok(()) => {
                    if self.wait_until_ready().is_ok() {
                        return Ok(());
                    }
                    start_errors.push(format!(
                        "local router started but TEI did not become ready within {}s",
                        self.cfg.start_timeout_secs
                    ));
                }
                Err(err) => start_errors.push(format!("local router start failed: {err}")),
            }
        }

        if self.cfg.docker_autostart {
            match self.start_docker_router() {
                Ok(()) => {
                    if self.wait_until_ready().is_ok() {
                        return Ok(());
                    }
                    start_errors.push(format!(
                        "docker router started but TEI did not become ready within {}s",
                        self.cfg.start_timeout_secs
                    ));
                }
                Err(err) => start_errors.push(format!("docker start failed: {err}")),
            }
        }

        let hints = [
            format!("install local TEI (Apple Silicon): `brew install text-embeddings-inference`"),
            format!(
                "run TEI manually: `text-embeddings-router --model-id {} --port {}`",
                self.cfg.model, self.cfg.port
            ),
            format!("or enable Docker and keep `MEMORY_SEARCH_TEI_DOCKER_AUTOSTART=true`"),
        ]
        .join("; ");

        bail!(
            "TEI endpoint is still unavailable at {}. Attempts: {}. Hints: {}",
            self.cfg.endpoint,
            if start_errors.is_empty() {
                "none".to_string()
            } else {
                start_errors.join(" | ")
            },
            hints
        )
    }

    fn wait_until_ready(&self) -> Result<()> {
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(self.cfg.start_timeout_secs) {
            if self.is_ready() {
                return Ok(());
            }
            thread::sleep(Duration::from_secs(1));
        }
        bail!(
            "TEI did not become ready within {} seconds ({})",
            self.cfg.start_timeout_secs,
            self.cfg.endpoint
        )
    }

    fn start_local_router(&self) -> Result<()> {
        let router_bin = resolve_binary(&self.cfg.router_bin)
            .ok_or_else(|| anyhow!("router binary '{}' not found in PATH", self.cfg.router_bin))?;

        if let Some(parent) = self.cfg.router_log_path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }

        let log_file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.cfg.router_log_path)
            .with_context(|| {
                format!(
                    "failed to open TEI log file {}",
                    self.cfg.router_log_path.display()
                )
            })?;
        let log_file_err = log_file
            .try_clone()
            .context("failed to clone TEI log file")?;

        let mut cmd = Command::new(router_bin);
        cmd.args(["--model-id", &self.cfg.model]);
        cmd.args(["--port", &self.cfg.port.to_string()]);
        cmd.args(&self.cfg.router_args);
        cmd.stdout(Stdio::from(log_file));
        cmd.stderr(Stdio::from(log_file_err));

        if let Ok(token) = std::env::var("HUGGING_FACE_HUB_TOKEN") {
            cmd.env("HUGGING_FACE_HUB_TOKEN", token);
        }

        let child = cmd
            .spawn()
            .context("failed to spawn local text-embeddings-router")?;
        eprintln!(
            "[memory-search] started local TEI router pid={} model={} port={} log={}",
            child.id(),
            self.cfg.model,
            self.cfg.port,
            self.cfg.router_log_path.display()
        );
        Ok(())
    }

    fn start_docker_router(&self) -> Result<()> {
        if which("docker").is_none() {
            bail!("docker command not found");
        }

        std::fs::create_dir_all(&self.cfg.cache_dir)
            .with_context(|| format!("failed to create {}", self.cfg.cache_dir.display()))?;

        let _ = Command::new("docker")
            .args(["rm", "-f", &self.cfg.container_name])
            .status();

        let port_mapping = format!("127.0.0.1:{}:80", self.cfg.port);
        let cache_mapping = format!("{}:/data", self.cfg.cache_dir.display());
        let mut cmd = Command::new("docker");
        cmd.args([
            "run",
            "-d",
            "--rm",
            "--name",
            &self.cfg.container_name,
            "-p",
            &port_mapping,
            "-v",
            &cache_mapping,
        ]);

        if let Ok(token) = std::env::var("HUGGING_FACE_HUB_TOKEN") {
            cmd.args(["-e", &format!("HUGGING_FACE_HUB_TOKEN={token}")]);
        }

        cmd.arg(&self.cfg.image);
        cmd.args(["--model-id", &self.cfg.model]);

        let output = cmd.output().context("failed to run TEI docker container")?;
        if !output.status.success() {
            let err = String::from_utf8_lossy(&output.stderr);
            bail!("TEI docker start failed: {err}");
        }
        Ok(())
    }

    fn is_ready(&self) -> bool {
        for path in ["/health", "/healthz", "/"] {
            let url = format!("{}{}", self.cfg.endpoint, path);
            if let Ok(resp) = self.client.get(&url).send() {
                if resp.status().is_success() {
                    return true;
                }
            }
        }
        false
    }
}

fn parse_embed_route_response(value: &Value) -> Result<Vec<Vec<f64>>> {
    // Single vector: [0.1, ...]
    if let Some(arr) = value.as_array() {
        if arr.first().is_some_and(|x| x.is_number()) {
            return Ok(vec![parse_vector(value)?]);
        }
        if arr.first().is_some_and(|x| x.is_array()) {
            let mut vectors = Vec::new();
            for item in arr {
                vectors.push(parse_vector(item)?);
            }
            return Ok(vectors);
        }
    }

    // Some servers respond as {"embeddings": [[...], ...]}
    if let Some(embs) = value.get("embeddings").and_then(|v| v.as_array()) {
        let mut vectors = Vec::new();
        for item in embs {
            vectors.push(parse_vector(item)?);
        }
        return Ok(vectors);
    }

    // Some servers respond as {"embedding": [...]}
    if let Some(emb) = value.get("embedding") {
        return Ok(vec![parse_vector(emb)?]);
    }

    bail!("unsupported TEI /embed response format")
}

fn parse_vector(value: &Value) -> Result<Vec<f64>> {
    let arr = value
        .as_array()
        .ok_or_else(|| anyhow!("embedding value is not an array"))?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        out.push(
            item.as_f64()
                .ok_or_else(|| anyhow!("embedding element is not a number"))?,
        );
    }
    if out.is_empty() {
        bail!("embedding vector is empty");
    }
    Ok(out)
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
