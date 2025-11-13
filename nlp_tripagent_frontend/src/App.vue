<template>
  <el-container class="layout">
    <div class="background-decoration"></div>
    <el-header class="header">
      <div class="header-content">
        <div class="logo">
          <div class="logo-icon-wrapper">
            <el-icon :size="32" color="#409EFF"><Location /></el-icon>
          </div>
          <div class="logo-text">
            <h1>Trip Agent</h1>
            <p class="logo-subtitle">Intelligent Trip Planning Assistant</p>
          </div>
        </div>
        <el-menu
          mode="horizontal"
          :default-active="activeIndex"
          class="nav-menu"
          router
        >
          <el-menu-item index="/">
            <el-icon><Document /></el-icon>
            <span>Itinerary Planning</span>
          </el-menu-item>
          <el-menu-item index="/results">
            <el-icon><View /></el-icon>
            <span>Results Display</span>
          </el-menu-item>
          <el-menu-item index="/map">
            <el-icon><MapLocation /></el-icon>
            <span>Map Visualization</span>
          </el-menu-item>
        </el-menu>
      </div>
    </el-header>
    <el-main class="content">
      <div class="content-wrapper">
        <router-view />
      </div>
    </el-main>
    <el-footer class="footer">
      <div class="footer-content">
        <p>© 2024 Trip Agent. Make every trip full of surprises</p>
      </div>
    </el-footer>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Location, Document, View, MapLocation } from '@element-plus/icons-vue'

const route = useRoute()
const activeIndex = computed(() => route.path)
</script>

<style scoped>
.layout {
  min-height: 100vh;
  position: relative;
  background: 
    linear-gradient(135deg, rgba(102, 126, 234, 0.85) 0%, rgba(118, 75, 162, 0.85) 100%),
    url('https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1920&q=80') center/cover no-repeat;
  overflow: hidden;
}

.background-decoration {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    radial-gradient(circle at 20% 50%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 40% 20%, rgba(255, 255, 255, 0.05) 0%, transparent 50%);
  pointer-events: none;
  z-index: 0;
}

.header {
  position: relative;
  z-index: 10;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(20px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 0;
  height: 80px !important; /* 降低高度以节省空间 */
  border-bottom: 1px solid rgba(102, 126, 234, 0.1);
  overflow: hidden;
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px; /* 减少左右内边距 */
  height: 100%;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px; /* 减少logo内部间距 */
  flex-shrink: 0; /* 防止logo被压缩 */
}

.logo-icon-wrapper {
  width: 48px; /* 减小图标容器 */
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  flex-shrink: 0;
}

.logo-icon-wrapper .el-icon {
  color: white !important;
  font-size: 28px; /* 减小图标大小 */
}

.logo-text h1 {
  margin: 0;
  font-size: 28px; /* 减小标题字体大小 */
  font-weight: 700;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
  white-space: nowrap; /* 防止文字换行 */
}

.logo-subtitle {
  margin: 2px 0 0;
  font-size: 12px; /* 减小副标题字体大小 */
  color: #909399;
  font-weight: 400;
  white-space: nowrap;
}

.nav-menu {
  border-bottom: none;
  background: transparent;
  flex: 1; /* 让导航菜单占据剩余空间 */
  display: flex;
  justify-content: flex-end;
}

.nav-menu :deep(.el-menu-item) {
  font-size: 14px; /* 减小菜单项字体大小 */
  font-weight: 500;
  padding: 0 16px !important; /* 减少内边距 */
  height: 80px !important; /* 匹配header高度 */
  line-height: 80px !important;
  transition: all 0.3s ease;
  border-bottom: none;
  margin: 0 2px; /* 减少菜单项间距 */
  position: relative;
  white-space: nowrap; /* 防止文字换行 */
}

.nav-menu :deep(.el-menu-item .el-icon) {
  font-size: 16px; /* 减小图标大小 */
  margin-right: 6px; /* 减少图标右边距 */
  transition: all 0.3s ease;
}

.nav-menu :deep(.el-menu-item::after) {
  content: '';
  position: absolute;
  bottom: 1px;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 32px); /* 调整下划线宽度 */
  height: 3px;
  background-color: transparent;
  transition: all 0.3s ease;
  border-radius: 2px 2px 0 0;
}

.nav-menu :deep(.el-menu-item:hover) {
  background-color: rgba(64, 158, 255, 0.08);
  color: #409EFF;
}

.nav-menu :deep(.el-menu-item:hover::after) {
  background-color: rgba(64, 158, 255, 0.3);
}

.nav-menu :deep(.el-menu-item.is-active) {
  font-weight: 600;
  color: #409EFF;
  background-color: rgba(64, 158, 255, 0.1);
}

.nav-menu :deep(.el-menu-item.is-active::after) {
  background-color: #409EFF;
}

.nav-menu :deep(.el-menu-item.is-active .el-icon) {
  color: #409EFF;
}

/* 隐藏更多菜单（如果存在） */
.nav-menu :deep(.el-sub-menu) {
  display: none !important;
}

.content {
  position: relative;
  z-index: 1;
  padding: 40px 20px; /* 减少内容区域内边距 */
  min-height: calc(100vh - 80px - 60px); /* 调整最小高度 */
}

.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
}

.footer {
  position: relative;
  z-index: 10;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(102, 126, 234, 0.1);
  height: 60px !important;
  display: flex;
  align-items: center;
  justify-content: center;
}

.footer-content {
  max-width: 1400px;
  width: 100%;
  text-align: center;
  color: #909399;
  font-size: 14px; /* 减小页脚字体大小 */
}

:deep(.el-main) {
  padding: 0;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .logo-text h1 {
    font-size: 24px;
  }
  
  .logo-subtitle {
    font-size: 11px;
  }
  
  .nav-menu :deep(.el-menu-item) {
    font-size: 13px;
    padding: 0 12px !important;
  }
}

@media (max-width: 992px) {
  .logo-text h1 {
    font-size: 20px;
  }
  
  .logo-subtitle {
    display: none; /* 在小屏幕上隐藏副标题 */
  }
  
  .nav-menu :deep(.el-menu-item) {
    font-size: 12px;
    padding: 0 10px !important;
  }
  
  .nav-menu :deep(.el-menu-item .el-icon) {
    display: none; /* 在小屏幕上隐藏图标 */
  }
}
</style>