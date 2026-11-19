mod engine;

use engine::Engine;
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::{Manager, State};

type SharedEngine = Arc<Engine>;

/// Runs a blocking engine request off the async runtime.
async fn call(engine: &State<'_, SharedEngine>, request: Value) -> Result<Value, String> {
    let engine = engine.inner().clone();
    tauri::async_runtime::spawn_blocking(move || engine.request(request))
        .await
        .map_err(|e| format!("engine task failed: {e}"))?
}

/// A paraphrase-style engine request: the settings plus the user's word preferences.
fn rewrite_request(
    cmd: &str,
    text: String,
    mode: String,
    strength: u8,
    restructure: Option<u8>,
    seed: Option<u64>,
    prefs: Option<Value>,
) -> Value {
    let mut request =
        json!({ "cmd": cmd, "text": text, "mode": mode, "strength": strength, "seed": seed });
    // How much sentences are restructured; without it the engine uses `strength` for both.
    if let Some(restructure) = restructure {
        request["restructure"] = json!(restructure);
    }
    // The user's word preferences; the engine validates them.
    if let Some(Value::Object(prefs)) = prefs {
        for key in ["locked_terms", "preferred", "banned"] {
            if let Some(value) = prefs.get(key) {
                request[key] = value.clone();
            }
        }
    }
    request
}

#[tauri::command]
async fn paraphrase(
    engine: State<'_, SharedEngine>,
    text: String,
    mode: String,
    strength: u8,
    restructure: Option<u8>,
    seed: Option<u64>,
    prefs: Option<Value>,
) -> Result<Value, String> {
    let request = rewrite_request("paraphrase", text, mode, strength, restructure, seed, prefs);
    call(&engine, request).await
}

/// A few different rewrites of a selected sentence or phrase.
#[tauri::command]
async fn rephrase(
    engine: State<'_, SharedEngine>,
    text: String,
    mode: String,
    strength: u8,
    restructure: Option<u8>,
    seed: Option<u64>,
    prefs: Option<Value>,
) -> Result<Value, String> {
    let request = rewrite_request("rephrase", text, mode, strength, restructure, seed, prefs);
    call(&engine, request).await
}

/// Similar words for one word of the result, grouped by meaning.
#[tauri::command]
async fn suggest(
    engine: State<'_, SharedEngine>,
    word: String,
    context: String,
) -> Result<Value, String> {
    call(
        &engine,
        json!({ "cmd": "suggest", "word": word, "context": context }),
    )
    .await
}

/// Builds a .docx of `text` with no document properties (base64).
#[tauri::command]
async fn export_docx(engine: State<'_, SharedEngine>, text: String) -> Result<Value, String> {
    call(&engine, json!({ "cmd": "export_docx", "text": text })).await
}

/// Extracts the text of a base64 .docx.
#[tauri::command]
async fn read_docx(engine: State<'_, SharedEngine>, data: String) -> Result<Value, String> {
    call(&engine, json!({ "cmd": "read_docx", "data": data })).await
}

/// Removes personal metadata (authors, dates, revision IDs...) from a base64 .docx.
#[tauri::command]
async fn clean_docx(engine: State<'_, SharedEngine>, data: String) -> Result<Value, String> {
    call(&engine, json!({ "cmd": "clean_docx", "data": data })).await
}

/// Stops the request in flight (the engine is restarted for the next one).
#[tauri::command]
fn cancel_engine(engine: State<'_, SharedEngine>) {
    engine.cancel();
}

/// Where the engine log is written, if anywhere.
#[tauri::command]
fn log_path(engine: State<'_, SharedEngine>) -> Option<String> {
    engine.log_path().map(|p| p.display().to_string())
}

/// Opens the folder that holds the engine log in the system file manager.
#[tauri::command]
fn open_log_folder(engine: State<'_, SharedEngine>) -> Result<(), String> {
    let dir = engine
        .log_path()
        .and_then(|p| p.parent())
        .ok_or("no log folder is available")?;
    let opener = if cfg!(windows) {
        "explorer"
    } else if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    };
    std::process::Command::new(opener)
        .arg(dir)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("could not open {}: {e}", dir.display()))
}

#[tauri::command]
async fn engine_status(engine: State<'_, SharedEngine>) -> Result<Value, String> {
    call(&engine, json!({ "cmd": "ping" })).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let paths = app.path();
            let engine: SharedEngine = Arc::new(Engine::new(
                paths.resource_dir().ok().map(|d| d.join("engine")),
                paths.app_log_dir().ok(),
            ));

            // Release builds have no console, so record panics in the log too.
            let for_panics = engine.clone();
            let default_hook = std::panic::take_hook();
            std::panic::set_hook(Box::new(move |info| {
                for_panics.log(&format!("panic: {info}"));
                default_hook(info);
            }));

            // Start the Python engine in the background so the first request is fast.
            let warm = engine.clone();
            std::thread::spawn(move || {
                let _ = warm.request(json!({ "cmd": "ping" }));
            });

            app.manage(engine);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            paraphrase,
            rephrase,
            suggest,
            engine_status,
            export_docx,
            read_docx,
            clean_docx,
            cancel_engine,
            log_path,
            open_log_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running Mero Paraphraser");
}
