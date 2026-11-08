//! Official Swades / Phone Whisper Server Rust Client SDK
use reqwest::Client as HttpClient;
use serde::{Deserialize, Serialize};
use std::error::Error;

#[derive(Clone, Debug)]
pub struct SwadesClient {
    endpoint: String,
    api_key: Option<String>,
    project_id: String,
    client: HttpClient,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Serialize, Debug)]
struct ChatRequest<'a> {
    model: &'a str,
    messages: &'a [ChatMessage],
}

impl SwadesClient {
    pub fn new(endpoint: Option<&str>, api_key: Option<&str>) -> Self {
        let ep = endpoint
            .unwrap_or("https://phone-whisper-server.pages.dev")
            .trim_end_matches('/')
            .to_string();
        Self {
            endpoint: ep,
            api_key: api_key.map(|s| s.to_string()),
            project_id: "default".to_string(),
            client: HttpClient::new(),
        }
    }

    pub fn with_project(mut self, project_id: &str) -> Self {
        self.project_id = project_id.to_string();
        self
    }

    pub async fn chat(&self, messages: &[ChatMessage]) -> Result<serde_json::Value, Box<dyn Error + Send + Sync>> {
        let url = format!("{}/v1/chat/completions", self.endpoint);
        let req_payload = ChatRequest {
            model: "qwen2.5-0.5b-instruct",
            messages,
        };
        let mut builder = self.client.post(&url).json(&req_payload);
        if let Some(ref key) = self.api_key {
            builder = builder.header("Authorization", format!("Bearer {}", key));
        }
        let res = builder.send().await?.json::<serde_json::Value>().await?;
        Ok(res)
    }

    pub async fn synthesize_speech(&self, text: &str, voice: Option<&str>) -> Result<Vec<u8>, Box<dyn Error + Send + Sync>> {
        let url = format!("{}/v1/audio/speech", self.endpoint);
        let payload = serde_json::json!({
            "model": "piper",
            "input": text,
            "voice": voice.unwrap_or("amy")
        });
        let mut builder = self.client.post(&url).json(&payload);
        if let Some(ref key) = self.api_key {
            builder = builder.header("Authorization", format!("Bearer {}", key));
        }
        let bytes = builder.send().await?.bytes().await?;
        Ok(bytes.to_vec())
    }

    pub async fn telemetry(&self) -> Result<serde_json::Value, Box<dyn Error + Send + Sync>> {
        let url = format!("{}/telemetry", self.endpoint);
        let res = self.client.get(&url).send().await?.json::<serde_json::Value>().await?;
        Ok(res)
    }

    pub async fn health(&self) -> Result<serde_json::Value, Box<dyn Error + Send + Sync>> {
        let url = format!("{}/v1/health", self.endpoint);
        let res = self.client.get(&url).send().await?.json::<serde_json::Value>().await?;
        Ok(res)
    }
}
