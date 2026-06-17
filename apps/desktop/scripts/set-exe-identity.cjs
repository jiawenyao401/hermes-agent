#!/usr/bin/env node
// set-exe-identity.cjs — stamp the Hermes icon + version metadata onto the
// built Hermes.exe using rcedit, completely decoupled from electron-builder's
// signing path.
//
// WHY THIS EXISTS
// ---------------
// apps/desktop/package.json sets build.win.signAndEditExecutable=false. That
// flag is load-bearing: turning electron-builder's own exe-editing ON also
// re-enables its signtool step, which fetches winCodeSign-2.6.0.7z, whose
// macOS symlinks crash 7-Zip on non-admin Windows (no Developer Mode = no
// SeCreateSymbolicLinkPrivilege). That is an unfixable dead end — we do NOT
// try to extract winCodeSign.
//
// The cost of disabling signAndEditExecutable is that electron-builder also
// skips rcedit, so the unpacked Hermes.exe keeps the stock Electron icon and
// "Electron" taskbar name. This script restores the icon + identity by calling
// rcedit DIRECTLY. rcedit is a pure PE resource editor: no signing, no certs,
// no winCodeSign, no symlinks.
//
// HOW IT RUNS
// -----------
// Primarily as an electron-builder `afterPack` hook (scripts/after-pack.cjs),
// so EVERY packed build — first install, `hermes desktop`, the installer's
// --update rebuild, or a dev's manual `npm run pack` — gets a branded exe from
// one place. Previously this stamp lived only in install.ps1, so the update
// path (which rebuilds via `hermes desktop --build-only`, never install.ps1)
// shipped a stock "Electron" exe. Keeping it in afterPack closes that gap.
//
// Also runnable standalone for ad-hoc re-stamping:
//   node scripts/set-exe-identity.cjs <path-to-Hermes.exe>
//
// Exits 0 on success, non-zero on failure when run as a CLI. As a hook,
// stampExeIdentity() resolves on success and rejects on failure; the caller
// (after-pack.cjs) swallows the rejection so a stamp failure never fails an
// otherwise-good build (worst case: stock icon, not a broken app).

const path = require('node:path')
const fs = require('node:fs')

function normalizedVersion(version) {
  const parts = String(version || '0.0.0')
    .split('.')
    .map(part => Number.parseInt(part, 10))
    .filter(part => Number.isFinite(part))

  while (parts.length < 4) parts.push(0)
  return parts.slice(0, 4).join('.')
}

function stampExeIdentityWithResEdit(exe, icon, desktopRoot) {
  const ResEdit = require('resedit')
  const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, 'package.json'), 'utf8'))
  const version = normalizedVersion(packageJson.version)
  const lang = 1033
  const codepage = 1200
  const data = fs.readFileSync(exe)
  const nt = ResEdit.NtExecutable.from(data, { ignoreCert: true })
  const res = ResEdit.NtExecutableResource.from(nt)
  const iconFile = ResEdit.Data.IconFile.from(fs.readFileSync(icon))
  const iconGroups = ResEdit.Resource.IconGroupEntry.fromEntries(res.entries)
  const iconGroupIds = iconGroups.length > 0 ? iconGroups.map(group => group.id) : [1]

  for (const iconGroupId of iconGroupIds) {
    ResEdit.Resource.IconGroupEntry.replaceIconsForResource(
      res.entries,
      iconGroupId,
      lang,
      iconFile.icons.map(item => item.data)
    )
  }

  const versionInfos = ResEdit.Resource.VersionInfo.fromEntries(res.entries)
  const versionInfo =
    versionInfos[0] ||
    ResEdit.Resource.VersionInfo.create(lang, {}, [
      {
        lang,
        codepage,
        values: {}
      }
    ])

  versionInfo.setFileVersion(version, lang)
  versionInfo.setProductVersion(version, lang)
  versionInfo.setStringValues(
    { lang, codepage },
    {
      CompanyName: 'Huaqing',
      FileDescription: 'AgentOS',
      FileVersion: version,
      InternalName: 'AgentOS',
      LegalCopyright: 'Copyright (c) 2026 Huaqing',
      OriginalFilename: 'AgentOS.exe',
      ProductName: 'AgentOS',
      ProductVersion: version
    }
  )
  versionInfo.outputToResourceEntries(res.entries)

  res.outputResource(nt)
  fs.writeFileSync(exe, Buffer.from(nt.generate()))
}

// Stamp the Hermes icon + identity onto `exe`. Resolves on success, throws on
// failure. `desktopRoot` defaults to this script's package root so the icon and
// the rcedit dependency resolve regardless of cwd.
async function stampExeIdentity(exe, desktopRoot = path.resolve(__dirname, '..')) {
  if (!exe || !fs.existsSync(exe)) {
    throw new Error(`target exe not found: ${exe}`)
  }

  // Icon lives at apps/desktop/assets/icon.ico
  const icon = path.join(desktopRoot, 'assets', 'icon.ico')
  if (!fs.existsSync(icon)) {
    throw new Error(`icon not found: ${icon}`)
  }

  console.log(`[set-exe-identity] stamping ${exe}`)
  console.log(`[set-exe-identity] icon: ${icon}`)

  try {
    // rcedit uses Wine when run on macOS/Linux. Prefer it when available, but
    // fall back to resedit so cross-built Windows installers still get the
    // AgentOS icon and version resources on machines without Wine.
    const mod = require('rcedit')
    const rcedit = typeof mod === 'function' ? mod : mod.rcedit
    if (typeof rcedit !== 'function') {
      throw new Error(`unexpected rcedit export shape: ${typeof mod} keys=${Object.keys(mod)}`)
    }

    await rcedit(exe, {
      icon,
      'version-string': {
        ProductName: 'AgentOS',
        FileDescription: 'AgentOS',
        CompanyName: 'Huaqing',
        LegalCopyright: 'Copyright (c) 2026 Huaqing'
      }
    })
  } catch (error) {
    console.warn(`[set-exe-identity] rcedit unavailable (${error.message}); falling back to resedit`)
    stampExeIdentityWithResEdit(exe, icon, desktopRoot)
  }

  console.log('[set-exe-identity] done — AgentOS icon + identity stamped')
}

module.exports = { stampExeIdentity }

// CLI entry point: `node scripts/set-exe-identity.cjs <exe>`.
if (require.main === module) {
  const exe = process.argv[2]
  if (!exe) {
    console.error('[set-exe-identity] usage: set-exe-identity.cjs <path-to-exe>')
    process.exit(2)
  }
  stampExeIdentity(exe).catch(err => {
    console.error(`[set-exe-identity] ${err.message}`)
    process.exit(1)
  })
}
