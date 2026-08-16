#!/usr/bin/env node
// Stage or clear a flavor into resources/ before packaging.
//
// A flavor lives in flavors/<name>/ and may contain:
//   app-config.json    → copied to resources/app-config.json
//   themes/<id>/...     → copied to resources/themes/<id>/...
//
// Usage:
//   node scripts/apply-flavor.mjs <name>   # stage flavors/<name> into resources/
//   node scripts/apply-flavor.mjs --clear  # remove staged app-config.json + themes/
//
// The standard build ships neither app-config.json nor resources/themes, so it
// keeps the default theme and free switching. Always --clear after a flavored
// build so the repo's resources/ stays clean.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const resourcesDir = path.join(root, 'resources')
const configFile = path.join(resourcesDir, 'app-config.json')
const resThemesDir = path.join(resourcesDir, 'themes')

function rimraf(target) {
  fs.rmSync(target, { recursive: true, force: true })
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true })
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name)
    const d = path.join(dest, entry.name)
    if (entry.isDirectory()) copyDir(s, d)
    else fs.copyFileSync(s, d)
  }
}

function clear() {
  rimraf(configFile)
  rimraf(resThemesDir)
  console.log('[flavor] cleared resources/app-config.json and resources/themes')
}

function apply(name) {
  const flavorDir = path.join(root, 'flavors', name)
  if (!fs.existsSync(flavorDir)) {
    console.error(`[flavor] no such flavor: flavors/${name}`)
    process.exit(1)
  }
  clear()
  const srcConfig = path.join(flavorDir, 'app-config.json')
  if (fs.existsSync(srcConfig)) {
    fs.mkdirSync(resourcesDir, { recursive: true })
    fs.copyFileSync(srcConfig, configFile)
    console.log(`[flavor] staged app-config.json from flavors/${name}`)
  }
  const srcThemes = path.join(flavorDir, 'themes')
  if (fs.existsSync(srcThemes)) {
    copyDir(srcThemes, resThemesDir)
    console.log(`[flavor] staged themes from flavors/${name}`)
  }
}

const arg = process.argv[2]
if (!arg || arg === '--clear') clear()
else apply(arg)
