/**
 * Dynamic electron-builder config.
 *
 * We keep the base config in package.json's "build" field and extend it here
 * only to populate `mac.binaries` — the list of extra Mach-O files that must
 * be signed with hardened runtime + entitlements.
 *
 * Why this is needed:
 * The Python backend is a PyInstaller onedir bundle shipped via extraResources
 * into Contents/Resources/backend/. electron-builder only hands the top-level
 * `.app` to codesign, which does NOT deep-sign the ~180 nested .so/.dylib
 * files under Resources/. Left unsigned (or without hardened runtime), Apple
 * notarization rejects the whole app.
 *
 * `mac.binaries` is the officially supported way to sign extra binaries: they
 * are signed inside electron-builder's own signing pass, AFTER it has created
 * the temporary keychain and imported the Developer ID cert (from CSC_LINK).
 * A previous afterPack approach failed because afterPack runs BEFORE that
 * keychain exists, so `codesign` couldn't find the identity.
 *
 * Paths are resolved relative to the `.app` at signing time. We enumerate the
 * pre-build backend source dir (build/dist/cowagent-backend, produced by
 * PyInstaller before packaging) — its layout mirrors the in-app copy — and map
 * each Mach-O to its in-app relative path.
 *
 * Never pin `arch` on mac.target in package.json: an arch listed there wins over
 * the --arm64/--x64 CLI flag, so every runner would build every arch and pair a
 * foreign shell with the backend PyInstaller just built for the host. The arch
 * has to come from the CLI, one per CI job.
 */
const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const config = require('./package.json').build

// PyInstaller output that gets copied into the app at
// Contents/Resources/backend/cowagent-backend (see extraResources).
const backendSrc = path.join(__dirname, 'build', 'dist', 'cowagent-backend')
const inAppPrefix = path.join('Contents', 'Resources', 'backend', 'cowagent-backend')

function isMachO(file) {
  try {
    return execFileSync('file', ['-b', file], { encoding: 'utf8' }).includes('Mach-O')
  } catch {
    return false
  }
}

function collectBackendBinaries() {
  if (!fs.existsSync(backendSrc)) {
    console.warn(`[electron-builder.js] backend not found at ${backendSrc}; mac.binaries left empty`)
    return []
  }
  const rels = []
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir)) {
      const full = path.join(dir, name)
      const st = fs.lstatSync(full)
      if (st.isSymbolicLink()) continue
      if (st.isDirectory()) {
        walk(full)
        continue
      }
      if (isMachO(full)) {
        // Map source path -> in-app relative path (resolved against the .app).
        const rel = path.relative(backendSrc, full)
        rels.push(path.join(inAppPrefix, rel))
      }
    }
  }
  walk(backendSrc)
  return rels
}

if (process.platform === 'darwin') {
  const binaries = collectBackendBinaries()
  console.log(`[electron-builder.js] injecting ${binaries.length} backend binaries into mac.binaries`)
  // Sign the backend binaries here, but do NOT notarize in CI: Apple's notary
  // service routinely keeps this large PyInstaller bundle "In Progress" for
  // hours, which no CI job can afford to block on. Notarization is decoupled
  // into a manual local step (build/notarize-dmg.sh) run after the CI produces
  // the signed dmg. The dmg is code-signed and hardened-runtime enabled here,
  // so it only needs the notarization ticket stapled afterwards.
  config.mac = { ...config.mac, binaries, notarize: false }
}

module.exports = config
