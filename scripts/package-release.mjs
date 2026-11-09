// Assembles a release folder: the NSIS installer plus the offline AI model.
//
//   release/Mero Paraphraser <version>/
//     Mero Paraphraser_<version>_x64-setup.exe
//     ai/runtime/...   (llama.cpp)
//     ai/models/...    (the .gguf model)
//
// The installer's post-install hook (src-tauri/windows/hooks.nsh) copies "ai"
// into the app data folder. The model (2.5 GB) can't go inside the installer
// itself: NSIS installers are limited to 2 GB.
//
// Run after `tauri build`; `pnpm tauri:build` does both.
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const python = process.env.MERO_PYTHON || (process.platform === "win32" ? "python" : "python3");
const conf = JSON.parse(readFileSync(join(root, "src-tauri", "tauri.conf.json"), "utf8"));
const { productName, version } = conf;

// 1. The installer from the last `tauri build`.
const nsisDir = join(root, "src-tauri", "target", "release", "bundle", "nsis");
const installers = existsSync(nsisDir)
  ? readdirSync(nsisDir).filter((f) => f.endsWith("-setup.exe") && f.includes(`_${version}_`))
  : [];
if (!installers.length) {
  console.error(`No NSIS installer for version ${version} in ${nsisDir}. Run \`pnpm tauri:build\` first.`);
  process.exit(1);
}
const installer = installers.sort((a, b) => statSync(join(nsisDir, b)).mtimeMs - statSync(join(nsisDir, a)).mtimeMs)[0];

// 2. Download (if needed) and verify the model; prints the folder that holds it.
console.log("Preparing the offline AI model (downloads 2.5 GB the first time)...");
const aiHome = execFileSync(python, [join(root, "python-engine", "app", "main.py"), "--prepare-ai"], {
  cwd: root,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "inherit"],
}).trim();

// The installer hook looks for this exact file name.
const hook = readFileSync(join(root, "src-tauri", "windows", "hooks.nsh"), "utf8");
const modelFile = readdirSync(join(aiHome, "models")).find((f) => f.endsWith(".gguf"));
if (!modelFile || !hook.includes(`"${modelFile}"`)) {
  console.error(`src-tauri/windows/hooks.nsh must name the model file (${modelFile}). Update MERO_AI_MODEL_FILE.`);
  process.exit(1);
}

// 3. Assemble the folder.
const out = join(root, "release", `${productName} ${version}`);
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(join(nsisDir, installer), join(out, installer));
const skip = /\.(log|part|zip)$/i;
cpSync(join(aiHome, "runtime"), join(out, "ai", "runtime"), { recursive: true, filter: (src) => !skip.test(src) });
mkdirSync(join(out, "ai", "models"), { recursive: true });
cpSync(join(aiHome, "models", modelFile), join(out, "ai", "models", modelFile));
writeFileSync(
  join(out, "README.txt"),
  [
    `${productName} ${version}`,
    "",
    `1. Keep the "ai" folder next to ${installer}.`,
    `2. Run ${installer}.`,
    "",
    "The installer copies the offline AI model from the \"ai\" folder, so no internet connection is needed.",
    "If the \"ai\" folder is missing, the app downloads the model (2.5 GB) the first time it starts.",
    "",
    "Powered by Mero Vision Pvt. Ltd",
    "",
  ].join("\r\n"),
);

console.log(`Release folder ready: ${out}`);
console.log("Zip this whole folder to distribute it.");
