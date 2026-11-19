//! Manages the Python paraphrasing engine as a long-lived child process.
//!
//! Requests and responses are single JSON lines over stdin/stdout (see
//! `python-engine/app/main.py`). The engine exits on its own when stdin closes, so it
//! never outlives the app.
//!
//! A reader thread forwards stdout lines over a channel, so a request can give up
//! after [`REQUEST_TIMEOUT`] or when [`Engine::cancel`] is called. Either way the
//! process is killed (Python is single-threaded, so that is the only way to stop it)
//! and the next request starts a fresh one.
//!
//! Lookup order for the engine:
//! 1. The bundled PyInstaller build in `<resources>/engine/` (release).
//! 2. `python-engine/app/main.py` run with the system Python (development). Set
//!    `MERO_PYTHON` to choose a specific interpreter.
//!
//! In release builds the engine's stderr, plus this module's own error events, go to
//! `engine.log` in the app log folder.

use serde_json::Value;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const ENGINE_NAME: &str = "mero-paraphraser-engine";
/// A full 20,000-character paraphrase takes well under a second; this also covers a
/// cold start on a slow machine.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(90);
/// How often a waiting request checks for cancellation.
const POLL: Duration = Duration::from_millis(100);
/// `engine.log` is moved to `engine.old.log` once it grows past this.
const MAX_LOG_BYTES: u64 = 1024 * 1024;

pub const CANCELLED: &str = "Cancelled.";

pub struct Engine {
    process: Mutex<Option<EngineProcess>>,
    /// Set by [`Engine::cancel`]; cleared when a request starts.
    cancel: AtomicBool,
    /// Bundled engine folder (release); `None` or missing means use the dev script.
    engine_dir: Option<PathBuf>,
    log: Option<PathBuf>,
}

enum CallError {
    /// The pipe broke or the process died: worth one restart and retry.
    Broken(String),
    /// Timed out or cancelled: the process was killed and the request is abandoned.
    Abandoned(String),
}

impl Engine {
    pub fn new(engine_dir: Option<PathBuf>, log_dir: Option<PathBuf>) -> Self {
        let log = log_dir.and_then(|dir| {
            fs::create_dir_all(&dir).ok()?;
            let path = dir.join("engine.log");
            if fs::metadata(&path)
                .map(|m| m.len() > MAX_LOG_BYTES)
                .unwrap_or(false)
            {
                let _ = fs::rename(&path, dir.join("engine.old.log"));
            }
            Some(path)
        });
        Self {
            process: Mutex::new(None),
            cancel: AtomicBool::new(false),
            engine_dir,
            log,
        }
    }

    pub fn log_path(&self) -> Option<&Path> {
        self.log.as_deref()
    }

    /// Appends a timestamped line to the log file (and stderr in debug builds).
    pub fn log(&self, msg: &str) {
        if cfg!(debug_assertions) {
            eprintln!("[engine] {msg}");
        }
        if let Some(mut f) = self.log.as_ref().and_then(|p| open_append(p)) {
            let secs = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let _ = writeln!(f, "[{secs}] {msg}");
        }
    }

    /// Stops the request in flight, if any. Callable while a request holds the lock.
    pub fn cancel(&self) {
        self.cancel.store(true, Ordering::SeqCst);
    }

    /// Sends a request and returns its `result`. Starts the engine on demand
    /// and restarts it once if it has died.
    pub fn request(&self, payload: Value) -> Result<Value, String> {
        let mut guard = self
            .process
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        // A cancel pressed before this request started doesn't apply to it.
        self.cancel.store(false, Ordering::SeqCst);
        let mut last_err = String::new();
        for _ in 0..2 {
            if guard.is_none() {
                let process = EngineProcess::spawn(self.engine_command()?, self.log.as_deref())
                    .inspect_err(|e| self.log(e))?;
                *guard = Some(process);
            }
            let process = guard.as_mut().expect("engine was just spawned");
            match process.call(payload.clone(), &self.cancel) {
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
                Err(CallError::Broken(e)) => {
                    self.log(&format!("{e}; restarting the engine"));
                    *guard = None; // drop (and kill) the broken process, then retry
                    last_err = e;
                }
                Err(CallError::Abandoned(e)) => {
                    if e != CANCELLED {
                        self.log(&e);
                    }
                    if let Some(mut p) = guard.take() {
                        p.kill();
                    }
                    return Err(e);
                }
            }
        }
        Err(last_err)
    }

    fn engine_command(&self) -> Result<Command, String> {
        if let Some(dir) = &self.engine_dir {
            let exe = dir.join(format!("{ENGINE_NAME}{}", std::env::consts::EXE_SUFFIX));
            if exe.is_file() {
                return Ok(Command::new(exe));
            }
        }

        let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("python-engine")
            .join("app")
            .join("main.py");
        if !script.is_file() {
            return Err(format!(
                "paraphrasing engine not found: expected {ENGINE_NAME} in the app's engine folder or {}",
                script.display()
            ));
        }
        let python = std::env::var("MERO_PYTHON")
            .unwrap_or_else(|_| if cfg!(windows) { "python" } else { "python3" }.to_string());
        let mut cmd = Command::new(python);
        cmd.arg(script);
        Ok(cmd)
    }
}

fn open_append(path: &Path) -> Option<File> {
    OpenOptions::new().create(true).append(true).open(path).ok()
}

struct EngineProcess {
    child: Child,
    /// `None` only while shutting down.
    stdin: Option<ChildStdin>,
    /// Lines from stdout, sent by the reader thread. Disconnects when stdout closes.
    lines: Receiver<std::io::Result<String>>,
    next_id: u64,
}

impl EngineProcess {
    fn spawn(mut cmd: Command, log: Option<&Path>) -> Result<Self, String> {
        // Debug: show engine errors in the terminal. Release: there is no console,
        // so append them to the log file.
        let stderr = if cfg!(debug_assertions) {
            Stdio::inherit()
        } else {
            log.and_then(open_append)
                .map(Stdio::from)
                .unwrap_or_else(Stdio::null)
        };
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr)
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

        let (tx, lines) = mpsc::channel();
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut buf = String::new();
                match reader.read_line(&mut buf) {
                    Ok(0) => return, // EOF: dropping `tx` tells the waiter
                    Ok(_) => {
                        if tx.send(Ok(buf)).is_err() {
                            return;
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(Err(e));
                        return;
                    }
                }
            }
        });

        Ok(Self {
            child,
            stdin: Some(stdin),
            lines,
            next_id: 1,
        })
    }

    /// Returns the raw response on a successful round trip.
    fn call(&mut self, mut payload: Value, cancel: &AtomicBool) -> Result<Value, CallError> {
        let id = self.next_id;
        self.next_id += 1;
        payload["id"] = Value::from(id);

        let mut line =
            serde_json::to_string(&payload).map_err(|e| CallError::Abandoned(e.to_string()))?;
        line.push('\n');
        let stdin = self
            .stdin
            .as_mut()
            .ok_or(CallError::Broken("engine is shutting down".into()))?;
        stdin
            .write_all(line.as_bytes())
            .and_then(|_| stdin.flush())
            .map_err(|e| CallError::Broken(format!("engine write failed: {e}")))?;

        let deadline = Instant::now() + REQUEST_TIMEOUT;
        loop {
            if cancel.load(Ordering::SeqCst) {
                return Err(CallError::Abandoned(CANCELLED.into()));
            }
            let now = Instant::now();
            if now >= deadline {
                return Err(CallError::Abandoned(format!(
                    "The paraphrasing engine did not respond within {} seconds and was restarted.",
                    REQUEST_TIMEOUT.as_secs()
                )));
            }
            let buf = match self.lines.recv_timeout(POLL.min(deadline - now)) {
                Ok(Ok(buf)) => buf,
                Ok(Err(e)) => return Err(CallError::Broken(format!("engine read failed: {e}"))),
                Err(RecvTimeoutError::Timeout) => continue,
                Err(RecvTimeoutError::Disconnected) => {
                    let status = self.child.try_wait().ok().flatten();
                    return Err(CallError::Broken(match status {
                        Some(s) => format!("the paraphrasing engine stopped unexpectedly ({s})"),
                        None => "the paraphrasing engine stopped unexpectedly".into(),
                    }));
                }
            };
            // Skip anything that isn't the response to this request (stray prints).
            let Ok(resp) = serde_json::from_str::<Value>(buf.trim()) else {
                continue;
            };
            if resp.get("id").and_then(Value::as_u64) == Some(id) {
                return Ok(resp);
            }
        }
    }

    /// Kills the process immediately (used when it is stuck).
    fn kill(&mut self) {
        drop(self.stdin.take());
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for EngineProcess {
    /// Closes stdin so the engine can exit cleanly, then kills it if it
    /// hasn't exited after a short grace period.
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
    use std::sync::Arc;

    #[test]
    fn round_trip_through_python_engine() {
        let engine = Engine::new(None, None);
        let ping = engine.request(json!({ "cmd": "ping" })).expect("ping");
        assert!(ping["version"].is_string());

        let out = engine
            .request(json!({ "cmd": "paraphrase", "text": "I do not know.", "mode": "humanize", "strength": 50, "seed": 1 }))
            .expect("paraphrase");
        assert!(out["text"].is_string());

        let err = engine.request(json!({ "cmd": "paraphrase", "text": "x", "mode": "bogus" }));
        assert!(err.unwrap_err().contains("unknown mode"));
    }

    #[test]
    fn cancel_kills_a_stuck_request_and_the_engine_recovers() {
        // Enables the engine's test-only `sleep` command (inherited by the child).
        std::env::set_var("MERO_ENGINE_TESTING", "1");
        let engine = Arc::new(Engine::new(None, None));
        engine.request(json!({ "cmd": "ping" })).expect("ping");

        // `sleep` is a test-only command that makes the engine hang.
        let e = engine.clone();
        let stuck = std::thread::spawn(move || e.request(json!({ "cmd": "sleep", "seconds": 60 })));
        std::thread::sleep(Duration::from_millis(500));
        let started = Instant::now();
        engine.cancel();
        assert_eq!(stuck.join().unwrap().unwrap_err(), CANCELLED);
        assert!(started.elapsed() < Duration::from_secs(5));

        // The next request starts a fresh engine.
        engine
            .request(json!({ "cmd": "ping" }))
            .expect("ping after cancel");
    }
}
