/**
 * 共享常量 — 城市、平台枚举、状态字典（三端共用，单一事实源）
 */

/** 城市列表（从原 city-switch.vue 迁入） */
export const CITIES = ['Tokyo', 'Osaka', 'Shanghai', 'Beijing', 'Guangzhou', 'Shenzhen']

/** 同好群平台枚举 */
export const PLATFORMS = {
  wechat: '微信',
  qq: 'QQ'
}

/** 乐队账号状态 */
export const ACCOUNT_STATUS = {
  pending: '审核中',
  active: '正常',
  rejected: '已拒绝',
  disabled: '已禁用'
}

/** Live 发布状态（决策：提交即发布，只有 draft/published 两级，无 submitted） */
export const LIVE_STATUS = {
  draft: '草稿',
  published: '已发布'
}

/** 拼盘邀请状态 */
export const INVITE_STATUS = {
  invited: '待处理',
  agreed: '已同意',
  rejected: '已拒绝',
  exit_requested: '申请退出',
  removed: '已退出'
}

/** Admin Live 类型（kind） */
export const LIVE_KIND = {
  normal: '普通',
  coop: '拼盘'
}

/** Admin Live 列表过滤参数 */
export const ADMIN_LIVE_FILTERS = [
  { value: 'all', label: '全部' },
  { value: 'normal', label: '普通' },
  { value: 'coop', label: '拼盘' }
]

/** 演出业务状态（展示用，来自 /full /sync 投影的 status 字段） */
export const LIVE_BUSINESS_STATUS = {
  announced: '已公布',
  on_sale: '售票中',
  completed: '已结束',
  cancelled: '已取消'
}
