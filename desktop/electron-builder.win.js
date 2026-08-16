/**
 * Dynamic electron-builder config for WINDOWS code signing.
 *
 * Mirrors electron-builder.js (which handles mac.binaries) but for Windows.
 * It wires a signing CLI into electron-builder so that every .exe is signed,
 * with the private key kept in hardware per the post-2023 code-signing rules.
 *
 * A SINGLE sign hook (win.signtoolOptions.sign) covers everything: electron-
 * builder calls it for EVERY .exe it processes, which includes the app
 * launcher, the packaged PyInstaller backend (extraResources/backend/
 * cowagent-backend.exe) and the NSIS installer. We deliberately do NOT add an
 * afterPack pass — that would sign the backend a second time and waste a paid
 * signing call on every release.
 *
 * PRIVACY: the CLI path and all credentials come from env vars only. Nothing in
 * this file (or the public workflow) is hardcoded, so a public repo never leaks
 * any signing configuration.
 *
 * DRY-RUN / SKIP: when SIGNTOOL_CERT_CODE is absent we skip signing entirely
 * (unsigned dev/dry builds keep working). When COW_SIGN_DRY_RUN=1 we pass
 * --dry-run so the WHOLE pipeline can be validated in CI with a self-signed
 * cert, WITHOUT a real certificate and WITHOUT consuming any signing quota.
 */
const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const config = require('./package.json').build

// Absolute path to the signing CLI on the runner. Injected by CI so this file
// never hardcodes a download URL. e.g. C:\signtool\signtool.exe
const SIGNTOOL = process.env.SIGNTOOL_PATH || ''
// Dry-run validates the pipeline with a self-signed cert (no quota, no real
// cert needed). Any truthy value enables it.
const DRY_RUN = !!process.env.COW_SIGN_DRY_RUN

// In dry-run the CLI still requires these flags to be NON-EMPTY (it validates
// presence, not the value, and signs with a self-signed cert). So when no real
// credentials are provided during a dry-run, fall back to harmless placeholders
// to satisfy the CLI's arg check. Real runs pass the actual secrets through.
const PLACEHOLDER = DRY_RUN ? 'dry-run' : ''
const ACCESS_KEY = process.env.SIGNTOOL_ACCESS_KEY || PLACEHOLDER
const ACCESS_SECRET = process.env.SIGNTOOL_ACCESS_SECRET || PLACEHOLDER
const CERT_CODE = process.env.SIGNTOOL_CERT_CODE || PLACEHOLDER

// RFC3161 timestamp server for SHA256. Microsoft's is reliable from CI runners
// worldwide; overridable via env if needed.
const TIMESTAMP = process.env.SIGNTOOL_TIMESTAMP || 'http://timestamp.acs.microsoft.com'

// Signing is possible when we have the CLI plus either a real cert code or
// explicit dry-run mode (dry-run accepts placeholder credentials).
function canSign() {
  if (!SIGNTOOL || !fs.existsSync(SIGNTOOL)) return false
  if (DRY_RUN) return true
  return !!(ACCESS_KEY && ACCESS_SECRET && CERT_CODE)
}

/**
 * Sign a single file in place using the signing CLI. The CLI writes to a
 * separate --out path (it refuses to overwrite an existing file), so we sign to
 * a temp file and atomically move it back over the original.
 */
function signFile(filePath) {
  const tmpOut = `${filePath}.signed`
  // Remove a stale temp from a previous failed run (CLI errors if --out exists).
  try {
    if (fs.existsSync(tmpOut)) fs.rmSync(tmpOut)
  } catch {
    /* ignore */
  }

  const args = [
    'sign',
    ...(DRY_RUN ? ['--dry-run'] : []),
    `--access-key=${ACCESS_KEY}`,
    `--access-secret=${ACCESS_SECRET}`,
    `--cert-code=${CERT_CODE}`,
    `--file=${filePath}`,
    `--out=${tmpOut}`,
    '--sha1=false',
    '--sha2=true',
    '--timestamp-rfc3161',
    TIMESTAMP,
  ]

  // Never print credentials: log only the file being signed.
  console.log(`[win-sign] signing ${path.basename(filePath)}${DRY_RUN ? ' (dry-run)' : ''}`)
  execFileSync(SIGNTOOL, args, { stdio: ['ignore', 'inherit', 'inherit'] })

  if (!fs.existsSync(tmpOut)) {
    throw new Error(`[win-sign] signed output not produced for ${filePath}`)
  }
  // Replace the original with the signed copy.
  fs.rmSync(filePath)
  fs.renameSync(tmpOut, filePath)
}

// electron-builder calls this for each artifact it generates (app exe, NSIS
// installer, uninstaller). Signature: (configuration) => void, where
// configuration.path is the file to sign.
async function customSign(configuration) {
  if (!canSign()) {
    console.warn('[win-sign] signing skipped (no signtool/credentials)')
    return
  }
  signFile(configuration.path)
}

// Extend the base config: attach the sign hook. Only meaningful on Windows
// builds (this config is only passed via --config on the win matrix leg).
//
// electron-builder invokes customSign for EVERY .exe it touches — that already
// includes the packaged backend (extraResources/backend/cowagent-backend.exe)
// and the NSIS installer, not just the app launcher. So there's no separate
// afterPack pass: adding one would sign the backend twice (wasting a paid
// signing call per release). Nested PyInstaller .dll/.pyd files are left
// unsigned, which Windows Authenticode tolerates (unlike macOS, it doesn't
// require deep-signing every nested lib — a signed top-level exe is enough for
// SmartScreen/Defender to attribute the publisher).
config.win = { ...config.win, signtoolOptions: { sign: customSign, signingHashAlgorithms: ['sha256'] } }

// Bundle ripgrep — Windows only. The "Bundle ripgrep binary" CI step downloads
// rg.exe to resources/bin; ship it under <resources>/bin so python-manager can
// put it on the backend's PATH (shutil.which("rg") -> fast rg backend instead
// of the slow PowerShell fallback). Declared here, not in package.json, so the
// macOS build (which never creates resources/bin) never references it.
config.extraResources = [
  ...(config.extraResources || []),
  { from: 'resources/bin', to: 'bin', filter: ['rg.exe'] },
]

module.exports = config
