<script>
import { applyTheme } from './common/theme.js'

export default {
  onLaunch() {
    // 应用已保存的主题（H5 打 data-theme；mp 安全降级）
    applyTheme()
    // 启动时不阻塞首屏；页面自行从 active_store 读取缓存并触发同步。
  }
}
</script>

<style>
/* 全局样式与设计 token（亮/暗）统一来自共享 theme.css（frontend/shared/theme.css）
   V4.4 §18：统一字体、间距、颜色，不引入复杂规范 */
@import './common/theme.css';
</style>
