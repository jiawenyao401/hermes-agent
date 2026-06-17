#!/usr/bin/env node

const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { PNG } = require('pngjs')

const desktopRoot = path.resolve(__dirname, '..')
const sourceIcon = path.join(desktopRoot, 'build', 'agentos-icons', '1024.png')
const assetsDir = path.join(desktopRoot, 'assets')
const publicDir = path.join(desktopRoot, 'public')
const distDir = path.join(desktopRoot, 'dist')
const iconWorkDir = path.join(desktopRoot, 'build', 'agentos-icons')
const iconsetDir = path.join(iconWorkDir, 'icon.iconset')

const pngSizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
const icoSizes = [16, 24, 32, 48, 64, 256]
const iconsetEntries = [
  ['icon_16x16.png', 16],
  ['icon_16x16@2x.png', 32],
  ['icon_32x32.png', 32],
  ['icon_32x32@2x.png', 64],
  ['icon_128x128.png', 128],
  ['icon_128x128@2x.png', 256],
  ['icon_256x256.png', 256],
  ['icon_256x256@2x.png', 512],
  ['icon_512x512.png', 512],
  ['icon_512x512@2x.png', 1024]
]

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readPng(file) {
  return PNG.sync.read(fs.readFileSync(file))
}

function writePng(file, png) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, PNG.sync.write(png))
}

function pixelOffset(png, x, y) {
  return (y * png.width + x) * 4
}

function resizeBilinear(src, size) {
  const out = new PNG({ width: size, height: size })
  const scaleX = src.width / size
  const scaleY = src.height / size

  for (let y = 0; y < size; y += 1) {
    const srcY = (y + 0.5) * scaleY - 0.5
    const y0 = Math.max(0, Math.floor(srcY))
    const y1 = Math.min(src.height - 1, y0 + 1)
    const wy = srcY - y0

    for (let x = 0; x < size; x += 1) {
      const srcX = (x + 0.5) * scaleX - 0.5
      const x0 = Math.max(0, Math.floor(srcX))
      const x1 = Math.min(src.width - 1, x0 + 1)
      const wx = srcX - x0
      const outOffset = pixelOffset(out, x, y)
      const p00 = pixelOffset(src, x0, y0)
      const p10 = pixelOffset(src, x1, y0)
      const p01 = pixelOffset(src, x0, y1)
      const p11 = pixelOffset(src, x1, y1)

      for (let channel = 0; channel < 4; channel += 1) {
        const top = src.data[p00 + channel] * (1 - wx) + src.data[p10 + channel] * wx
        const bottom = src.data[p01 + channel] * (1 - wx) + src.data[p11 + channel] * wx
        out.data[outOffset + channel] = Math.round(top * (1 - wy) + bottom * wy)
      }
    }
  }

  return out
}

function roundedRectAlpha(x, y, size, radius) {
  const px = x + 0.5
  const py = y + 0.5
  const innerLeft = radius
  const innerRight = size - radius
  const innerTop = radius
  const innerBottom = size - radius
  const cx = px < innerLeft ? innerLeft : px > innerRight ? innerRight : px
  const cy = py < innerTop ? innerTop : py > innerBottom ? innerBottom : py
  const distance = Math.hypot(px - cx, py - cy)

  if (distance <= radius - 1) return 1
  if (distance >= radius) return 0
  return radius - distance
}

function applyRoundedMask(png) {
  const radius = png.width * 0.2237

  for (let y = 0; y < png.height; y += 1) {
    for (let x = 0; x < png.width; x += 1) {
      const alpha = roundedRectAlpha(x, y, png.width, radius)
      const offset = pixelOffset(png, x, y) + 3
      png.data[offset] = Math.round(png.data[offset] * alpha)
    }
  }

  return png
}

function roundedIcon(src, size) {
  return applyRoundedMask(resizeBilinear(src, size))
}

function writeIco(file, entries) {
  const headerSize = 6
  const dirSize = 16 * entries.length
  let offset = headerSize + dirSize
  const directory = []

  for (const entry of entries) {
    directory.push({ ...entry, offset })
    offset += entry.data.length
  }

  const out = Buffer.alloc(offset)
  out.writeUInt16LE(0, 0)
  out.writeUInt16LE(1, 2)
  out.writeUInt16LE(entries.length, 4)

  directory.forEach((entry, index) => {
    const base = headerSize + index * 16
    out.writeUInt8(entry.size >= 256 ? 0 : entry.size, base)
    out.writeUInt8(entry.size >= 256 ? 0 : entry.size, base + 1)
    out.writeUInt8(0, base + 2)
    out.writeUInt8(0, base + 3)
    out.writeUInt16LE(1, base + 4)
    out.writeUInt16LE(32, base + 6)
    out.writeUInt32LE(entry.data.length, base + 8)
    out.writeUInt32LE(entry.offset, base + 12)
    entry.data.copy(out, entry.offset)
  })

  ensureDir(path.dirname(file))
  fs.writeFileSync(file, out)
}

function main() {
  if (!fs.existsSync(sourceIcon)) {
    throw new Error(`source icon not found: ${sourceIcon}`)
  }

  ensureDir(iconWorkDir)
  ensureDir(iconsetDir)

  const src = readPng(sourceIcon)
  if (src.width !== src.height) {
    throw new Error(`source icon must be square: ${sourceIcon}`)
  }

  const generated = new Map()
  for (const size of pngSizes) {
    const icon = roundedIcon(src, size)
    generated.set(size, icon)
    writePng(path.join(iconWorkDir, `${size}.png`), icon)
  }

  for (const [name, size] of iconsetEntries) {
    writePng(path.join(iconsetDir, name), generated.get(size) || roundedIcon(src, size))
  }

  const runtimeIcon = generated.get(512)
  writePng(path.join(assetsDir, 'icon.png'), runtimeIcon)
  writePng(path.join(publicDir, 'apple-touch-icon.png'), runtimeIcon)
  if (fs.existsSync(distDir)) {
    writePng(path.join(distDir, 'apple-touch-icon.png'), runtimeIcon)
  }
  writeIco(
    path.join(assetsDir, 'icon.ico'),
    icoSizes.map(size => ({ size, data: PNG.sync.write(generated.get(size) || roundedIcon(src, size)) }))
  )

  execFileSync('iconutil', ['-c', 'icns', '-o', path.join(assetsDir, 'icon.icns'), iconsetDir], {
    stdio: 'inherit'
  })

  console.log('[generate-rounded-icons] rounded app icons written to apps/desktop/assets and public')
}

try {
  main()
} catch (error) {
  console.error(`[generate-rounded-icons] ${error.message}`)
  process.exit(1)
}
