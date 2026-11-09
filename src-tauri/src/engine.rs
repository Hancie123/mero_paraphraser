//! Manages the Python paraphrasing engine as a long-lived child process.
//!
//! Requests and responses are single JSON lines over stdin/stdout (see
//! `python-engine/app/main.py`). The engine exits on its own when stdin closes, so it
//! never outlives the app.
//!
//! Lookup order for the engine:
//! 1. The bundled PyInstaller sidecar next to the app executable (release).
//! 2. `python-engine/app/main.py` run with the system Python (development). Set
//!    `MERO_PYTHON` to choose a specific interpreter.

use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

const SIDECAR_NAME: &str = "mero-paraphraser-engine";

pub struct Engine {
    process: Mutex<Option<EngineProcess>>,
}

impl Engine {
    pub fn new() -> Self {
        Self { process: Mutex::new(None) }
    }

    /// Sends a request and returns its `result`. Starts the engine on demand
    /// and restarts it once if it has died.
    pub fn request(&self, payload: Value) -> Result<Value, String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "engine lock poisoned".to_string())?;
        let mut last_err = String::new();
        for _ in 0..2 {
            if guard.is_none() {
                *guard = Some(EngineProcess::spawn()?);
            }
            let process = guard.as_mut().expect("engine was just spawned");
            match process.call(payload.clone()) {
                Ok(resp) => {
                    return if resp.get("ok").and_then(Value::as_bool) == Some(true) {
                        Ok(resp.get("result").cloned().unwrap_or(Value::Null))
                    } else {
                        Err(resp
                            .get("error")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown engine error")
                            .to_string())
                    };
                }
                Err(e) => {
                    *guard = None; // drop (and kill) the broken process, then retry
                    last_err = e;
                }
            }
        }
        Err(last_err)
    }
}

struct EngineProcess {
    child: Child,
    /// `None` only while shutting down.
    stdin: Option<ChildStdin>,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl EngineProcess {
    fn spawn() -> Result<Self, String> {
        let mut cmd = engine_command()?;
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(if cfg!(debug_assertions) { Stdio::inherit() } else { Stdio::null() })
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1");
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = cmd
            .spawn()
            .map_err(|e| format!("could not start the paraphrasing engine: {e}"))?;
        let stdin = child.stdin.take().ok_or("engine stdin unavailable")?;
        let stdout = child.stdout.take().ok_or("engine stdout unavailable")?;
        Ok(Self { child, stdin: Some(stdin), stdout: BufReader::new(stdout), next_id: 1 })
    }

    /// Returns the raw response on a successful round trip; `Err` means the
    /// pipe broke and the process should be restarted.
    fn call(&mut self, mut payload: Value) -> Result<Value, String> {
        let id = self.next_id;
        self.next_id += 1;
        payload["id"] = Value::from(id);

        let mut line = serde_json::to_string(&payload).map_err(|e| e.to_string())?;
        line.push('\n');
        let stdin = self.stdin.as_mut().ok_or("engine is shutting down")?;
        stdin
            .write_all(line.as_bytes())
            .and_then(|_| stdin.flush())
            .map_err(|e| format!("engine write failed: {e}"))?;

        loop {
            let mut buf = String::new();
            let n = self
                .stdout
                .read_line(&mut buf)
                .map_err(|e| format!("engine read failed: {e}"))?;
            if n == 0 {
                return Err("the paraphrasing engine stopped unexpectedly".into());
            }
            // Skip anything that isn't the response to this request (stray prints).
            let Ok(resp) = serde_json::from_str::<Value>(buf.trim()) else { continue };
            if resp.get("id").and_then(Value::as_u64) == Some(id) {
                return Ok(resp);
            }
        }
    }
}

impl Drop for EngineProcess {
    /// Closes stdin so the engine can shut down its AI model cleanly, then
    /// kills it if it hasn't exited after a short grace period.
    fn drop(&mut self) {
        drop(self.stdin.take());
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if let Ok(Some(_)) = self.child.try_wait() {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn round_trip_through_python_engine() {
        let engine = Engine::new();
        let ping = engine.request(json!({ "cmd": "ping" })).expect("ping");
        assert!(ping["version"].is_string());

        let out = engine
            .request(json!({ "cmd": "paraphrase", "text": "I don't know.", "mode": "formal", "strength": 50, "seed": 1 }))
            .expect("paraphrase");
        assert_eq!(out["text"], "I do not know.");

        let err = engine.request(json!({ "cmd": "paraphrase", "text": "x", "mode": "bogus" }));
        assert!(err.unwrap_err().contains("unknown mode"));
    }
}

fn engine_command() -> Result<Command, String> {
    if let Some(dir) = std::env::current_exe().ok().and_then(|p| p.parent().map(PathBuf::from)) {
        let sidecar = dir.join(format!("{SIDECAR_NAME}{}", std::env::consts::EXE_SUFFIX));
        if sidecar.is_file() {
            return Ok(Command::new(sidecar));
        }
    }

    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("python-engine")
        .join("app")
        .join("main.py");
    if !script.is_file() {
        return Err(format!(
            "paraphrasing engine not found: expected the {SIDECAR_NAME} sidecar next to the app or {}",
            script.display()
        ));
    }
    let python = std::env::var("MERO_PYTHON")
        .unwrap_or_else(|_| if cfg!(windows) { "python" } else { "python3" }.to_string());
    let mut cmd = Command::new(python);
    cmd.arg(script);
    Ok(cmd)
}
