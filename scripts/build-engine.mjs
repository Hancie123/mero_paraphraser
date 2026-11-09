// Bundles python-engine/app/main.py into a standalone executable with PyInstaller and
// places it where Tauri expects sidecars: src-tauri/binaries/<name>-<target-triple>[.exe]
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const name = "mero-paraphraser-engine";
const isWin = process.platform === "win32";
const python = process.env.MERO_PYTHON || (isWin ? "python" : "python3");
const ext = isWin ? ".exe" : "";

const rustInfo = execFileSync("rustc", ["-vV"], { encoding: "utf8" });
const triple = rustInfo.match(/^host:\s*(\S+)/m)?.[1];
if (!triple) throw new Error("Could not determine the Rust target triple from `rustc -vV`.");

const work = join(root, "build", "engine");
const run = (args) => execFileSync(python, args, { cwd: root, stdio: "inherit" });

try {
  execFileSync(python, ["-c", "import PyInstaller"], { stdio: "ignore" });
} catch {
  console.error(`PyInstaller is not installed. Run:  ${python} -m pip install -r python-engine/requirements.txt`);
  process.exit(1);
}

run([
  "-m", "PyInstaller",
  "--onefile", "--noconfirm", "--clean", "--console",
  "--name", name,
  "--paths", join(root, "python-engine"),
  // Prompt files are read at runtime from app/prompts.
  "--add-data", `${join(root, "python-engine", "app", "prompts")}${delimiter}app/prompts`,
  "--collect-submodules", "app",
  "--distpath", join(work, "dist"),
  "--workpath", join(work, "work"),
  "--specpath", work,
  join(root, "python-engine", "app", "main.py"),
]);

const outDir = join(root, "src-tauri", "binaries");
mkdirSync(outDir, { recursive: true });
const target = join(outDir, `${name}-${triple}${ext}`);
copyFileSync(join(work, "dist", `${name}${ext}`), target);
console.log(`Engine sidecar ready: ${target}`);
