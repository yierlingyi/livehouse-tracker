/**
 * sync-shared.js — 共享 → 三端同步脚本（Node 等价，可选兜底）
 *
 * 用法：node scripts/sync-shared.js
 * 作用：清空三端 common/ → 复制 shared/ → SHA256 哈希比对（drift 检测）
 */
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')

const root = path.resolve(__dirname, '..')
const shared = path.join(root, 'shared')
const targets = ['user-app', 'band-portal', 'admin-console']

if (!fs.existsSync(shared)) {
  console.error('shared 目录不存在:', shared)
  process.exit(1)
}

function clearDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true })
  fs.mkdirSync(dir, { recursive: true })
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

function hashMap(dir) {
  const map = {}
  ;(function walk(d, rel) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name)
      const r = rel ? rel + '/' + entry.name : entry.name
      if (entry.isDirectory()) walk(full, r)
      else {
        map[r] = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex')
      }
    }
  })(dir, '')
  return map
}

console.log('== 清空并复制 shared → 三端 common/ ==')
for (const t of targets) {
  const common = path.join(root, t, 'common')
  clearDir(common)
  copyDir(shared, common)
  console.log(`  [ok] ${t}/common/`)
}

console.log('== 哈希一致性校验（drift 检测）==')
const baseline = hashMap(shared)
let drift = 0

for (const t of targets) {
  const map = hashMap(path.join(root, t, 'common'))
  if (Object.keys(map).length !== Object.keys(baseline).length) {
    console.error(`  [FAIL] ${t}: 文件数不一致 (shared=${Object.keys(baseline).length}, ${t}=${Object.keys(map).length})`)
    drift++
    continue
  }
  for (const rel of Object.keys(baseline)) {
    if (!map[rel]) {
      console.error(`  [FAIL] ${t} 缺少 ${rel}`)
      drift++
    } else if (map[rel] !== baseline[rel]) {
      console.error(`  [FAIL] ${t} 内容不一致: ${rel}`)
      drift++
    }
  }
  if (drift === 0) console.log(`  [ok] ${t} common/ 与 shared/ 一致`)
}

if (drift > 0) {
  console.error(`\nsync-shared FAILED: drift = ${drift}`)
  process.exit(1)
}

console.log('\nsync-shared OK: 三端 common/ 与 shared/ 完全一致 (drift=0)')
