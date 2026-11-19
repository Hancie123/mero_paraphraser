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
) -> Result<Value, String> {
    call(
        &engine,
        json!({ "cmd": "paraphrase", "text": text, "mode": mode, "strength": strength, "seed": seed }),
    )
    .await
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
        .invoke_handler(tauri::generate_handler![paraphrase, engine_status])
        .run(tauri::generate_context!())
        .expect("error while running Mero Paraphraser");
}
