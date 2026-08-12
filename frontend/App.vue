<script>
export default {
  onLaunch() {
    // 启动时不阻塞首屏；页面自行从 active_store 读取缓存并触发同步。
  }
}
</script>

<style>
/* 全局样式与 CSS 变量（V4.4 §18：统一字体、间距、颜色，不引入复杂规范） */
page {
  --color-bg: #f5f6f8;
  --color-surface: #ffffff;
  --color-text: #1f2329;
  --color-text-secondary: #6b7280;
  --color-text-muted: #9ca3af;
  --color-primary: #e5484d;
  --color-border: #e5e7eb;
  --color-success: #16a34a;
  --color-warning: #f59e0b;

  --radius: 16rpx;

  --font-size-xs: 22rpx;
  --font-size-sm: 26rpx;
  --font-size-base: 28rpx;
  --font-size-lg: 32rpx;
  --font-size-xl: 36rpx;

  background-color: var(--color-bg);
  color: var(--color-text);
  font-size: var(--font-size-base);
  font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

view,
text,
button,
image {
  box-sizing: border-box;
}

button::after {
  border: none;
}
</style>
