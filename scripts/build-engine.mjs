// Bundles python-engine/app/main.py with PyInstaller (--onedir) and places the
// folder where the installer picks it up: src-tauri/binaries/engine/ (bundled as
// the "engine" resource by src-tauri/tauri.bundle.json).
//
// --onedir instead of --onefile: a one-file build unpacks itself to a temp folder on
// every launch, which slows startup and often trips antivirus software.
//
// Also checks that the version numbers match package.json, the single source of
// truth (tauri.conf.json reads it directly; the UI asks Tauri for it).
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, readFileSync, rmSync } from "node:fs";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const name = "mero-paraphraser-engine";
const isWin = process.platform === "win32";
const python = process.env.MERO_PYTHON || (isWin ? "python" : "python3");
const ext = isWin ? ".exe" : "";

checkVersions();

const work = join(root, "build", "engine");
const run = (args) => execFileSync(python, args, { cwd: root, stdio: "inherit" });

try {
  execFileSync(python, ["-c", "import PyInstaller"], { stdio: "ignore" });
} catch {
  console.error(`PyInstaller is not installed. Run:  ${python} -m pip install -r python-engine/requirements.txt`);
  process.exit(1);
}

run([
  "-m",
  "PyInstaller",
  "--onedir",
  "--noconfirm",
  "--clean",
  "--console",
  "--name",
  name,
  "--paths",
  join(root, "python-engine"),
  // Generated synonyms (tools/build_lexicon.py), read by app/core/lexicon.py.
  "--add-data",
  `${join(root, "python-engine", "app", "data")}${delimiter}app/data`,
  "--collect-submodules",
  "app",
  "--distpath",
  join(work, "dist"),
  "--workpath",
  join(work, "work"),
  "--specpath",
  work,
  join(root, "python-engine", "app", "main.py"),
]);

const built = join(work, "dist", name);
if (!existsSync(join(built, `${name}${ext}`))) throw new Error(`PyInstaller output not found in ${built}`);
const binaries = join(root, "src-tauri", "binaries");
const target = join(binaries, "engine");
rmSync(target, { recursive: true, force: true });
// Leftover from the old --onefile sidecar build.
rmSync(join(binaries, `${name}-${hostTriple()}${ext}`), { force: true });
cpSync(built, target, { recursive: true });
console.log(`Engine ready: ${target}`);

function hostTriple() {
  return execFileSync("rustc", ["-vV"], { encoding: "utf8" }).match(/^host:\s*(\S+)/m)?.[1] ?? "unknown";
}

function checkVersions() {
  const read = (p) => readFileSync(join(root, p), "utf8");
  const expected = JSON.parse(read("package.json")).version;
  const found = {
    "python-engine/app/core/config.py (VERSION)": read("python-engine/app/core/config.py").match(
      /^VERSION\s*=\s*["']([^"']+)["']/m,
    )?.[1],
    "src-tauri/Cargo.toml ([package] version)": read("src-tauri/Cargo.toml").match(
      /^\[package\][^[]*?^version\s*=\s*"([^"]+)"/ms,
    )?.[1],
  };
  const wrong = Object.entries(found).filter(([, v]) => v !== expected);
  if (wrong.length) {
    console.error(`Version mismatch: package.json says ${expected}, but`);
    for (const [where, v] of wrong) console.error(`  ${where} says ${v ?? "(not found)"}`);
    process.exit(1);
  }
}
