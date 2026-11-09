mod engine;

use engine::Engine;
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;

type SharedEngine = Arc<Engine>;

/// Runs a blocking engine request off the async runtime.
async fn call(engine: &State<'_, SharedEngine>, request: Value) -> Result<Value, String> {
    let engine = engine.inner().clone();
    tauri::async_runtime::spawn_blocking(move || engine.request(request))
        .await
        .map_err(|e| format!("engine task failed: {e}"))?
}

#[tauri::command]
async fn paraphrase(
    engine: State<'_, SharedEngine>,
    text: String,
    mode: String,
    strength: u8,
    seed: Option<u64>,
    engine_kind: Option<String>,
) -> Result<Value, String> {
    let kind = engine_kind.unwrap_or_else(|| "auto".into());
    call(
        &engine,
        json!({ "cmd": "paraphrase", "text": text, "mode": mode, "strength": strength, "seed": seed, "engine": kind }),
    )
    .await
}

/// Runs one of the engine's AI-model commands (status, download, cancel, remove, warm).
#[tauri::command]
async fn ai_command(engine: State<'_, SharedEngine>, action: String) -> Result<Value, String> {
    let cmd = match action.as_str() {
        "status" => "ai_status",
        "download" => "ai_download",
        "cancel" => "ai_cancel",
        "remove" => "ai_remove",
        "warm" => "ai_warm",
        other => return Err(format!("unknown AI action {other:?}")),
    };
    call(&engine, json!({ "cmd": cmd })).await
}

#[tauri::command]
async fn engine_status(engine: State<'_, SharedEngine>) -> Result<Value, String> {
    call(&engine, json!({ "cmd": "ping" })).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let engine: SharedEngine = Arc::new(Engine::new());

    // Start the Python engine in the background so the first request is fast.
    let warm = engine.clone();
    std::thread::spawn(move || {
        let _ = warm.request(json!({ "cmd": "ping" }));
    });

    tauri::Builder::default()
        .manage(engine)
        .invoke_handler(tauri::generate_handler![paraphrase, engine_status, ai_command])
        .run(tauri::generate_context!())
        .expect("error while running Mero Paraphraser");
}
