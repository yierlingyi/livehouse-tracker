<script>
import { applyTheme } from './common/theme.js'
import { guardLaunch } from './common/guard.js'
import { setAuthRedirectEnabled } from './common/http.js'

export default {
  onLaunch() {
    // 主题恢复
    applyTheme()
    // band 端：开启 401 → 跳登录
    setAuthRedirectEnabled(true)
    // 登录态兜底（未登录且在受保护页 → 登录页；已登录在登录页 → 工作台）
    guardLaunch({ loginPage: '/pages/login/index', homePage: '/pages/dashboard/index' })
  }
}
</script>

<style>
/* 共享设计 token（亮/暗）统一来自 frontend/shared/theme.css */
@import './common/theme.css';
</style>
