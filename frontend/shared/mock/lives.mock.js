/**
 * 演出 Live Mock（V4.4 /full /sync + 新 GET /lives/{id}）
 *
 * - GET /api/v1/lives/full   全量（城市感知、id keyset 分页）→ {data, scope, snapshot_cursor, has_more, next_token}
 * - GET /api/v1/lives/sync   增量 → {data, deletes, cursor, has_more}
 * - GET /api/v1/lives/{id}   详情（含 venue + setlist + poster）→ {live, venue, setlist, poster_image_url}
 *
 * 数据：Tokyo / Osaka / Beijing 各 5~8 条，其中 1~2 条 review_status!=='published'
 * （不出现在 /full）。模块级 LIVES 数组维持内存态；venues.mock.js 可 import 共享。
 */
import { delay } from './_state.js'

/** 相对今天的日期偏移（YYYY-MM-DD） */
function dayOffset(offset) {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + day
}

/** 当前业务日期（作为 scope 起点，V4.4：当天起 +90 天） */
export function todayStr() {
  return dayOffset(0)
}

let idSeed = 100
let VERSION = 100

function nextId() {
  idSeed += 1
  return idSeed
}

/** 数据变更时推进版本号，使 /sync 能感知变化（模拟 CDC） */
export function bumpLiveVersion() {
  VERSION += 1
  return VERSION
}

function makeLive(o) {
  idSeed = Math.max(idSeed, o.id)
  return {
    id: o.id,
    livehouse_id: o.venue.id,
    live_date: o.live_date,
    start_time: o.start_time,
    sort_start_time: o.start_time,
    title: o.title,
    ticket_price: o.ticket_price,
    ticket_url: 'https://example.com/tickets/' + o.id,
    poster_image_url: '/static/mock-cover.svg',
    city: o.city,
    band_names: o.band_names,
    status: o.status || 'announced',
    kind: o.kind || 'normal',
    review_status: o.review_status || 'published',
    updated_at: new Date().toISOString(),
    venue: o.venue,
    setlist: o.setlist
  }
}

/* 场地快照（详情页 venue 信息） */
const V_TOKYO_A = { id: 1, name: 'Live Garage 涩谷', address: '東京都渋谷区宇田川町13-8', phone: '03-1234-5678' }
const V_TOKYO_B = { id: 2, name: 'Blue Note 横滨', address: '神奈川県横浜市中区山下町200', phone: '045-222-3333' }
const V_OSAKA = { id: 3, name: 'Umeda Banana Hall', address: '大阪府大阪市北区梅田1-1', phone: '06-6666-7777' }
const V_BEIJING = { id: 4, name: 'Mao Livehouse 北京', address: '北京市朝阳区三里屯路19号', phone: '010-5555-6666' }

export const LIVES = [
  // ---- Tokyo ----
  makeLive({ id: 101, city: 'Tokyo', live_date: dayOffset(5), start_time: '19:30', title: '霓虹乐队《Neon Lights》首发巡演', ticket_price: 180, band_names: ['霓虹乐队'], venue: V_TOKYO_A, setlist: [{ song_title: '霓虹色' }, { song_title: '高速路' }, { song_title: '电波' }, { song_title: '夜航' }] }),
  makeLive({ id: 102, city: 'Tokyo', live_date: dayOffset(8), start_time: '20:00', title: '回声碎片 × 噪音花园 双专场', ticket_price: 150, band_names: ['回声碎片', '噪音花园'], venue: V_TOKYO_B, setlist: [{ song_title: '碎玻璃' }, { song_title: '无主之地' }, { song_title: '混凝土花园' }] }),
  makeLive({ id: 103, city: 'Tokyo', live_date: dayOffset(15), start_time: '19:00', title: '落日电台 新专辑试听会', ticket_price: 120, band_names: ['落日电台'], venue: V_TOKYO_A, setlist: [{ song_title: '黄昏信号' }, { song_title: '电台情歌' }, { song_title: '街灯' }] }),
  makeLive({ id: 104, city: 'Tokyo', live_date: dayOffset(22), start_time: '18:00', title: '夏日祭 金属拼盘', ticket_price: 160, band_names: ['深海鲸落', '噪音花园'], kind: 'coop', venue: V_TOKYO_B, setlist: [{ song_title: '鲸落' }, { song_title: '深水区' }, { song_title: '铁锈' }] }),
  makeLive({ id: 105, city: 'Tokyo', live_date: dayOffset(30), start_time: '19:30', title: '霓虹乐队 安可场（草稿）', ticket_price: 200, band_names: ['霓虹乐队'], review_status: 'draft', venue: V_TOKYO_A, setlist: [{ song_title: '返场' }, { song_title: '霓虹色(remix)' }] }),
  makeLive({ id: 106, city: 'Tokyo', live_date: dayOffset(3), start_time: '21:00', title: '翻唱致敬夜', ticket_price: 100, band_names: ['回声碎片'], venue: V_TOKYO_B, setlist: [{ song_title: '致敬曲1' }, { song_title: '致敬曲2' }] }),
  // ---- Osaka ----
  makeLive({ id: 201, city: 'Osaka', live_date: dayOffset(4), start_time: '19:00', title: '回声碎片 关西巡演', ticket_price: 140, band_names: ['回声碎片'], venue: V_OSAKA, setlist: [{ song_title: '碎片号' }, { song_title: '河内' }, { song_title: '归途' }] }),
  makeLive({ id: 202, city: 'Osaka', live_date: dayOffset(11), start_time: '20:30', title: '霓虹乐队 Osaka 限定', ticket_price: 160, band_names: ['霓虹乐队'], venue: V_OSAKA, setlist: [{ song_title: '港町' }, { song_title: '霓虹色' }, { song_title: '潮汐' }] }),
  makeLive({ id: 203, city: 'Osaka', live_date: dayOffset(18), start_time: '19:30', title: '爵士之夜', ticket_price: 180, band_names: ['落日电台', '噪音花园'], venue: V_OSAKA, setlist: [{ song_title: '月下漫步' }, { song_title: '蓝色变奏' }] }),
  makeLive({ id: 204, city: 'Osaka', live_date: dayOffset(25), start_time: '21:30', title: '深夜摇滚现场（草稿）', ticket_price: 120, band_names: ['深海鲸落'], review_status: 'draft', venue: V_OSAKA, setlist: [{ song_title: '深海' }, { song_title: '回声' }] }),
  makeLive({ id: 205, city: 'Osaka', live_date: dayOffset(2), start_time: '18:30', title: '独立音乐节 pre-party', ticket_price: 90, band_names: ['回声碎片', '噪音花园'], venue: V_OSAKA, setlist: [{ song_title: '开场' }, { song_title: '沸腾' }] }),
  // ---- Beijing ----
  makeLive({ id: 301, city: 'Beijing', live_date: dayOffset(6), start_time: '19:30', title: 'Mao 新春联欢演出', ticket_price: 130, band_names: ['霓虹乐队', '落日电台'], venue: V_BEIJING, setlist: [{ song_title: '新年钟声' }, { song_title: '霓虹色' }, { song_title: '电台情歌' }] }),
  makeLive({ id: 302, city: 'Beijing', live_date: dayOffset(13), start_time: '20:00', title: '后摇之夜', ticket_price: 110, band_names: ['深海鲸落'], venue: V_BEIJING, setlist: [{ song_title: '鲸落' }, { song_title: '深渊之眼' }] }),
  makeLive({ id: 303, city: 'Beijing', live_date: dayOffset(20), start_time: '19:00', title: '独立摇滚拼盘', ticket_price: 150, band_names: ['回声碎片', '噪音花园'], kind: 'coop', venue: V_BEIJING, setlist: [{ song_title: '鼓点' }, { song_title: '噪音花园' }, { song_title: '碎片' }] }),
  makeLive({ id: 304, city: 'Beijing', live_date: dayOffset(9), start_time: '19:30', title: '民谣星期三（草稿）', ticket_price: 80, band_names: ['落日电台'], review_status: 'draft', venue: V_BEIJING, setlist: [{ song_title: '吉他手' }, { song_title: '民谣' }] }),
  makeLive({ id: 305, city: 'Beijing', live_date: dayOffset(27), start_time: '20:30', title: '硬核现场', ticket_price: 170, band_names: ['噪音花园'], venue: V_BEIJING, setlist: [{ song_title: '噪音' }, { song_title: '硬核' }, { song_title: '暴走' }] })
]

/** 曾发布过（曾出现在 /full）的 live id 集合。用于 /sync 计算 deletes：
 *  仅统计「曾上线、后下线/回草稿」的 live，纯草稿（从未发布）不产生 delete。
 *  必须定义在 LIVES 之后（TDZ：不能在 LIVES 初始化前读取）。 */
export const publishedSeen = new Set(
  LIVES.filter((l) => l.review_status === 'published').map((l) => l.id)
)

/** 标记某个 live 已发布（band/coop/admin mock 在 publish 时调用） */
export function markLivePublished(live) {
  if (live && live.id != null) publishedSeen.add(live.id)
}

/** 序列化为 /full /sync 的 Live 投影（与后端 _SELECT_COLUMNS 一致，不含 venue/setlist） */
function serializeLive(l) {
  return {
    id: l.id,
    livehouse_id: l.livehouse_id,
    live_date: l.live_date,
    start_time: l.start_time,
    sort_start_time: l.sort_start_time,
    title: l.title,
    ticket_price: l.ticket_price,
    ticket_url: l.ticket_url,
    poster_image_url: l.poster_image_url,
    city: l.city,
    band_names: l.band_names,
    status: l.status,
    updated_at: l.updated_at
  }
}

function inScope(l, city, startDate, endDate) {
  if (l.review_status !== 'published') return false
  if (l.city !== city) return false
  if (startDate && l.live_date < startDate) return false
  if (endDate && l.live_date > endDate) return false
  return true
}

function sortedPublished(city, startDate, endDate) {
  return LIVES
    .filter((l) => inScope(l, city, startDate, endDate))
    .sort((a, b) => {
      if (a.live_date !== b.live_date) return a.live_date < b.live_date ? -1 : 1
      if (a.sort_start_time !== b.sort_start_time) return a.sort_start_time < b.sort_start_time ? -1 : 1
      return a.id - b.id
    })
}

export default {
  /* ---------------- /full 全量同步 ---------------- */
  'GET /api/v1/lives/full': async ({ data }) => {
    await delay()
    const city = String((data && data.city) || '').trim() || 'Tokyo'
    const pageSize = Math.max(1, Math.min(2000, Number((data && data.page_size) || 500) || 500))
    const pageToken = (data && data.page_token) || null
    const scopeStart = todayStr()
    // 90 天范围
    const end = new Date()
    end.setDate(end.getDate() + 90)
    const scopeEnd = end.getFullYear() + '-' + String(end.getMonth() + 1).padStart(2, '0') + '-' + String(end.getDate()).padStart(2, '0')

    let rows = sortedPublished(city, scopeStart, scopeEnd)
    // 简化 keyset：page_token 形如 mock-keyset-<lastId>
    if (pageToken) {
      const m = /mock-keyset-(\d+)/.exec(String(pageToken))
      if (m) {
        const lastId = Number(m[1])
        rows = rows.filter((l) => l.id > lastId)
      }
    }

    const hasMore = rows.length > pageSize
    const pageRows = hasMore ? rows.slice(0, pageSize) : rows
    const nextToken = hasMore
      ? 'mock-keyset-' + pageRows[pageRows.length - 1].id
      : null

    return {
      data: pageRows.map(serializeLive),
      scope: { city, scope_start_date: scopeStart, scope_end_date: scopeEnd },
      snapshot_cursor: String(VERSION),
      has_more: hasMore,
      next_token: nextToken
    }
  },

  /* ---------------- /sync 增量同步 ---------------- */
  'GET /api/v1/lives/sync': async ({ data }) => {
    await delay()
    const city = String((data && data.city) || '').trim() || 'Tokyo'
    const since = Number((data && data.since) != null ? data.since : 0)
    const limit = Math.max(1, Math.min(5000, Number((data && data.limit) || 1000) || 1000))
    const scopeStart = String((data && data.scope_start_date) || todayStr())
    const scopeEnd = String((data && data.scope_end_date) || scopeStart)

    // 已追平 → 空批次，has_more=false（防止无限循环）
    if (since >= VERSION) {
      return { data: [], deletes: [], cursor: since, has_more: false }
    }
    // 有变化（或首轮 catch-up）→ 返回当前已发布快照，cursor 推进到 high_water
    const rows = sortedPublished(city, scopeStart, scopeEnd).slice(0, limit)

    // deletes：本应出现在 scope、曾发布过、但当前已下线/回草稿的 live。
    // 与 /full 保持一致：仅「曾上线后下线」产生 delete，纯草稿（从未发布）不产生。
    const scopeIds = new Set(
      LIVES
        .filter((l) => l.city === city)
        .filter((l) => !scopeStart || l.live_date >= scopeStart)
        .filter((l) => !scopeEnd || l.live_date <= scopeEnd)
        .map((l) => l.id)
    )
    const publishedNow = new Set(
      LIVES.filter((l) => l.review_status === 'published').map((l) => l.id)
    )
    const deletes = Array.from(scopeIds).filter(
      (id) => publishedSeen.has(id) && !publishedNow.has(id)
    )

    return {
      data: rows.map(serializeLive),
      deletes,
      cursor: VERSION,
      has_more: false
    }
  },

  /* ---------------- 演出详情（公开，含场地+setlist+海报） ---------------- */
  'GET /api/v1/lives/:id': async ({ params }) => {
    await delay()
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    return {
      live: serializeLive(live),
      venue: live.venue || null,
      setlist: live.setlist || [],
      poster_image_url: live.poster_image_url
    }
  }
}
