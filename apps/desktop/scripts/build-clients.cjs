#!/usr/bin/env node

const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const desktopRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(desktopRoot, '..', '..')
const appsDir = path.join(repoRoot, 'apps')
const releaseDir = path.join(desktopRoot, 'release')
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, 'package.json'), 'utf8'))
const version = packageJson.version

function run(command, args, options = {}) {
  console.log(`\n$ ${[command, ...args].join(' ')}`)
  execFileSync(command, args, {
    cwd: options.cwd || desktopRoot,
    env: {
      ...process.env,
      // Local packaging should not fail because this machine has no Apple
      // Developer ID certificate. Notarized distribution can opt in by
      // exporting CSC_* / APPLE_* env vars and removing this override.
      CSC_IDENTITY_AUTO_DISCOVERY: 'false',
      ...options.env
    },
    stdio: 'inherit'
  })
}

function npm(args, options) {
  run('npm', args, options)
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function copyArtifact(name) {
  const from = path.join(releaseDir, name)
  const to = path.join(appsDir, name)

  if (!fs.existsSync(from)) {
    throw new Error(`expected artifact missing: ${from}`)
  }

  ensureDir(appsDir)
  fs.copyFileSync(from, to)
  console.log(`[build-clients] copied ${path.relative(repoRoot, to)}`)

  return to
}

function verifyFile(file) {
  const stat = fs.statSync(file)

  if (!stat.isFile() || stat.size === 0) {
    throw new Error(`artifact is empty or not a file: ${file}`)
  }

  console.log(`[build-clients] verified ${path.basename(file)} (${Math.round(stat.size / 1024 / 1024)} MB)`)
}

function maybeVerifyDmg(file) {
  if (process.platform !== 'darwin') {
    return
  }

  run('hdiutil', ['verify', file], { cwd: repoRoot })
}

function removeMatchingArtifacts(pattern) {
  if (!fs.existsSync(releaseDir)) {
    return
  }

  for (const entry of fs.readdirSync(releaseDir)) {
    if (pattern.test(entry)) {
      fs.rmSync(path.join(releaseDir, entry), { force: true, recursive: true })
    }
  }
}

function main() {
  if (process.platform !== 'darwin') {
    throw new Error('this script currently builds the Mac DMG and cross-builds Windows from macOS; run it on Apple Mac')
  }

  const macArtifact = `AgentOS-${version}-mac-arm64.dmg`
  const winArtifact = `AgentOS-${version}-win-x64.exe`

  console.log(`[build-clients] building AgentOS desktop installers v${version}`)

  npm(['run', 'icons:rounded'])
  npm(['run', 'build'])

  removeMatchingArtifacts(/^AgentOS-.*-(mac-arm64|win-x64)\.(dmg|exe)$/)
  removeMatchingArtifacts(/^(mac-arm64|win-unpacked)$/)

  npm(['run', 'builder', '--', '--mac', 'dmg', '--arm64'])
  const macOut = copyArtifact(macArtifact)
  verifyFile(macOut)
  maybeVerifyDmg(macOut)

  // package.json points electronDist at this host's Electron build for fast
  // local dev packaging. Use a Windows-specific config that omits electronDist
  // so electron-builder downloads the correct win32 x64 Electron runtime
  // instead of trying to rename the macOS binary as AgentOS.exe. Do not pass
  // `-c.electronDist=`: electron-builder 26 treats the empty string as a hook
  // path and tries to import the project directory.
  npm(['run', 'builder', '--', '--win', 'nsis', '--x64', '--config', 'scripts/electron-builder-win.cjs'])
  const winOut = copyArtifact(winArtifact)
  verifyFile(winOut)

  console.log('\n[build-clients] done')
  console.log(`Mac:     ${macOut}`)
  console.log(`Windows: ${winOut}`)
}

try {
  main()
} catch (error) {
  console.error(`\n[build-clients] ${error.message}`)
  process.exit(1)
}
