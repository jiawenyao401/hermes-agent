'use strict'

const pkg = require('../package.json')

const config = { ...(pkg.build || {}) }

// The package-level electronDist points at the host Electron runtime for fast
// local unpacked builds. Cross-building Windows from macOS must let
// electron-builder download the win32 Electron zip instead. Passing
// `-c.electronDist=` is not equivalent: electron-builder 26 treats the empty
// string as a hook path, resolves it to the project directory, then tries to
// import apps/desktop as an ES module.
delete config.electronDist
config.electronDownload = {
  ...(config.electronDownload || {}),
  mirror: process.env.ELECTRON_MIRROR || 'https://npmmirror.com/mirrors/electron/'
}

module.exports = config
