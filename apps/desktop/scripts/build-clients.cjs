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
const electronVersion = packageJson.build?.electronVersion
const electronMirror = process.env.ELECTRON_MIRROR || 'https://npmmirror.com/mirrors/electron/'

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

function ensureWindowsElectronDist() {
  if (!electronVersion) {
    throw new Error('package.json build.electronVersion is required for Windows client packaging')
  }

  const fileName = `electron-v${electronVersion}-win32-x64.zip`
  const cacheDir = path.join(desktopRoot, 'build', 'electron-cache')
  const zipPath = path.join(cacheDir, fileName)
  const distDir = path.join(desktopRoot, 'build', 'electron', 'win32-x64')
  const electronExe = path.join(distDir, 'electron.exe')

  if (fs.existsSync(electronExe)) {
    console.log(`[build-clients] using cached Windows Electron runtime: ${path.relative(repoRoot, distDir)}`)

    return distDir
  }

  ensureDir(cacheDir)
  ensureDir(path.dirname(distDir))

  const mirrorBase = electronMirror.endsWith('/') ? electronMirror : `${electronMirror}/`
  const url = `${mirrorBase}v${electronVersion}/${fileName}`

  console.log(`[build-clients] downloading Windows Electron runtime: ${url}`)
  run('curl', ['-L', '--fail', '--retry', '3', '--connect-timeout', '20', '-o', zipPath, url], { cwd: repoRoot })

  fs.rmSync(distDir, { force: true, recursive: true })
  ensureDir(distDir)
  run('ditto', ['-x', '-k', zipPath, distDir], { cwd: repoRoot })

  if (!fs.existsSync(electronExe)) {
    throw new Error(`Windows Electron runtime did not contain electron.exe: ${distDir}`)
  }

  console.log(`[build-clients] prepared Windows Electron runtime: ${path.relative(repoRoot, distDir)}`)

  return distDir
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
  // local dev packaging. Cross-building Windows from macOS needs a win32 x64
  // runtime instead; prepare it explicitly and point electron-builder there so
  // it can rename electron.exe to AgentOS.exe.
  const winElectronDist = ensureWindowsElectronDist()
  npm([
    'run',
    'builder',
    '--',
    '--win',
    'nsis',
    '--x64',
    '--config',
    'scripts/electron-builder-win.cjs',
    `-c.electronDist=${winElectronDist}`
  ], {
    env: {
      ELECTRON_MIRROR: electronMirror,
      HERMES_ELECTRON_BUILDER_SKIP_LOCAL_DIST: '1'
    }
  })
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
