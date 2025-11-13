<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, Location, MapLocation, Search, InfoFilled, CircleCheck, Star, LocationInformation, Sunny, ArrowDown, RefreshLeft } from '@element-plus/icons-vue'
import { useTripStore } from '../stores/trip'
import { planTrip } from '../services/tripService'
import ChatAssistant from '../components/ChatAssistant.vue'
import { useSessionStore } from '../stores/session'
import { vaiageApiService } from '../services/vaiageApi'

const store = useTripStore()
const router = useRouter()
const sessionStore = useSessionStore()

const form = ref({
  origin: store.request.origin || '',
  destination: store.request.destination || '',
  days: store.request.days || 3,
  preferences: store.request.preferences || ''
})

const loading = ref(false)
const formRef = ref()
const resetting = ref(false)

// Popular cities list
const popularCities = [
  {label: 'Shanghai', region: 'China' },
  {label: 'Beijing', region: 'China' },
  {label: 'Tokyo', region: 'Japan' },
  {label: 'Osaka', region: 'Japan' },
  {label: 'Seoul', region: 'South Korea' },
  {label: 'Singapore', region: 'Singapore' },
  {label: 'Bangkok', region: 'Thailand' },
  {label: 'Paris', region: 'France' },
  {label: 'London', region: 'UK' },
  {label: 'New York', region: 'USA' },
  {label: 'Los Angeles', region: 'USA' },
  {label: 'Sydney', region: 'Australia' },
  {label: 'Dubai', region: 'UAE' },
  {label: 'Hong Kong', region: 'China' },
  {label: 'Taipei', region: 'China' }
]

// Control popover visibility
const originPopoverVisible = ref(false)
const destinationPopoverVisible = ref(false)

// Select city
function selectCity(field: 'origin' | 'destination', city: string) {
  form.value[field] = city
  if (field === 'origin') {
    originPopoverVisible.value = false
  } else {
    destinationPopoverVisible.value = false
  }
}

const rules = {
  origin: [{ required: true, message: 'Please enter departure city', trigger: 'blur' }],
  destination: [{ required: true, message: 'Please enter destination city', trigger: 'blur' }],
  days: [
    { required: true, message: 'Please enter number of days', trigger: 'blur' },
    { type: 'number', min: 1, max: 30, message: 'Days should be between 1-30', trigger: 'blur' }
  ],
  preferences: [{ required: false, message: 'Please enter your travel preferences', trigger: 'blur' }]
}

async function submitForm() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    loading.value = true
    try {
      store.setRequest(form.value)
      const result = await planTrip(store.request)
      store.setResult(result)
      ElMessage.success('Itinerary planning successful!')
      router.push('/results')
    } catch (e: any) {
      ElMessage.error(e?.message || 'Request failed, please try again later')
    } finally {
      loading.value = false
    }
  })
}

async function resetConversation() {
  if (resetting.value) return
  resetting.value = true
  try {
    await vaiageApiService.resetSession()
    await sessionStore.resetSession()
    await sessionStore.initializeSession()
    ElMessage.success('Chat conversation has been reset.')
  } catch (error: any) {
    console.error('Failed to reset conversation:', error)
    ElMessage.error(error?.message || 'Failed to reset the conversation. Please try again.')
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <div class="form-page">
    <div class="welcome-section">
      <h1 class="welcome-title">Plan Your Perfect Trip</h1>
      <p class="welcome-desc">Chat with our AI assistant to create a personalized travel plan tailored to your preferences</p>
    </div>
    
    <el-row :gutter="80" class="form-row">
      <!-- 左侧：Travel Assistant 问答框 -->
      <el-col :xs="24" :sm="24" :md="12" :lg="12" :xl="12" class="chat-col">
        <ChatAssistant />
      </el-col>
      
      <!-- 右侧：Travel Planning Tips -->
      <el-col :xs="24" :sm="24" :md="12" :lg="12" :xl="12" class="form-col">
        <el-card class="tips-card" shadow="always">
          <template #header>
            <div class="card-header">
              <div class="header-icon">
                <el-icon :size="28"><InfoFilled /></el-icon>
              </div>
              <div class="header-text">
                <span class="header-title">Travel Planning Tips</span>
                <span class="header-subtitle">Get the most out of your trip</span>
              </div>
            </div>
          </template>
          <div class="tips-content">
            <ul class="tips-list">
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Destination:</strong> Where do you want to travel? (city, country, or region)</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Travel Dates:</strong> When are you planning to go? (start and end dates)</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Group Size:</strong> How many people are traveling together?</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Budget Range:</strong> Low ($500-1000), Medium ($1000-3000), or High ($3000+)</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Accommodation:</strong> Hotel preferences (budget, luxury, boutique, etc.)</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Travel Style:</strong> Relaxation, adventure, cultural, or mixed</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Activities:</strong> What do you enjoy? (sightseeing, hiking, shopping, etc.)</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Food Preferences:</strong> Dietary restrictions or favorite cuisines</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Transportation:</strong> Car rental preference or public transport</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Special Interests:</strong> Museums, nature, nightlife, family-friendly, etc.</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Accessibility:</strong> Any mobility or accessibility requirements</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Health Conditions:</strong> Medical needs or physical limitations</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Language Preferences:</strong> English-speaking guides or local experiences</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Pace of Travel:</strong> Fast-paced or relaxed itinerary</span>
              </li>
              <li>
                <el-icon><CircleCheck /></el-icon>
                <span><strong>Weather Preferences:</strong> Preferred climate or seasonal activities</span>
              </li>
            </ul>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="reset-section">
      <el-button
        type="danger"
        plain
        size="large"
        :loading="resetting"
        @click="resetConversation"
        class="reset-button"
      >
        <el-icon :size="18"><RefreshLeft /></el-icon>
        <span>Reset Conversation</span>
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.form-page {
  padding: 40px 0;
  max-width: 100%; /* 新增：移除宽度限制 */
  margin: 0 auto;
  min-height: 100vh; /* 确保页面有足够高度 */
}

.welcome-section {
  text-align: center;
  margin-bottom: 60px;
  padding: 40px 20px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(25px);
  -webkit-backdrop-filter: blur(25px);
  border-radius: 30px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 
    0 12px 40px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.4);
  margin: 0 auto 60px;
  max-width: 1000px;
}

.welcome-title {
  font-size: 40px;
  font-weight: 700;
  color: white;
  margin: 0 0 16px;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.welcome-desc {
  font-size: 20px;
  color: rgba(255, 255, 255, 0.9);
  margin: 0;
}

.form-row {
  margin-bottom: 40px;
  align-items: stretch;
  display: flex;
  justify-content: center; /* 确保内容居中 */
  min-height: 600px; /* 增加最小高度 */
  height: 100%; /* 确保容器有高度 */
}

.form-row :deep(.el-col) {
  display: flex;
  height: 100%;
}

.reset-section {
  margin: 40px auto 0;
  display: flex;
  justify-content: center;
}

.reset-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 240px;
}

.form-card {
  border-radius: 20px;
  border: none;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  width: 100%;
  display: flex;
  flex-direction: column;
  height: 100%; /* 让卡片填满容器高度 */
}

.card-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 0;
}

.header-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-icon .el-icon {
  font-size: 32px;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.header-title {
  font-size: 24px;
  font-weight: 600;
  color: #303133; /* 改为黑色 */
}

.header-subtitle {
  font-size: 16px;
  color: #606266; /* 改为深灰色 */
  font-weight: 400;
}

.trip-form {
  padding: 48px 0 36px;
}

:deep(.el-form-item) {
  margin-bottom: 40px;
}

:deep(.el-form-item__label) {
  font-size: 16px;
  font-weight: 500;
  color: white;
}

:deep(.el-input__inner) {
  font-size: 16px;
}

:deep(.el-textarea__inner) {
  font-size: 16px;
}

.input-with-popover {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.input-with-popover :deep(.el-input) {
  flex: 1;
}

.planning-btn :deep(.el-icon) {
  margin-right: 8px;
}

.city-selector-btn {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border: 1px solid #dcdfe6;
  background: #fff;
  transition: all 0.3s;
  font-size: 20px;
}

.city-selector-btn:hover {
  border-color: #409EFF;
  color: #409EFF;
}

.city-selector {
  padding: 8px 0;
}

.city-selector-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  font-weight: 600;
  font-size: 20px;
  color: #303133;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 12px;
}

.city-selector-header .el-icon {
  font-size: 22px;
}

.city-list {
  display: grid;
  grid-template-columns: 1fr 1fr; /* 明确使用fr单位确保等分 */
  gap: 10px;
  padding: 12px;
  max-height: 400px;
  overflow-y: auto;
}

.city-btn {
  width: 100%;
  height: 100px;
  padding: 16px;
  margin: 0; /* 确保没有外边距 */
  justify-content: flex-start;
  text-align: left;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.city-btn-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  margin: 0;
  padding: 0; 
}

/* 确保所有文本行数一致 */
.city-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
  height: 20px; /* 固定高度 */
  overflow: hidden;
}

.city-region {
  font-size: 14px;
  color: #909399;
  line-height: 1.2;
  height: 17px; /* 固定高度 */
  overflow: hidden;
}

.form-col {
  display: flex;
  height: 100%;
}

.form-card {
  width: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.tips-col {
  display: flex;
}

.chat-col {
  display: flex;
  height: 100%;
}

.tips-section {
  display: flex;
  flex-direction: column;
  gap: 40px;
  width: 100%;
  height: 100%;
}

.tips-card,
.features-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(15px);
  -webkit-backdrop-filter: blur(15px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
  height: 800px; /* 固定高度，与左侧保持一致 */
  overflow: hidden;
}

.tips-card :deep(.el-card__body),
.features-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.tips-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  max-height: 700px;
  padding-right: 8px;
}

.tips-content::-webkit-scrollbar {
  width: 6px;
}

.tips-content::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.tips-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 3px;
}

.tips-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}

.tips-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-weight: 600;
  font-size: 20px;
  color: #303133;
  padding-top: 2px;
}

.tips-header .el-icon {
  font-size: 24px;
}

.tips-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.tips-list li {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  color: white;
  font-size: 16px;
  line-height: 1.8;
  margin-top: 0;
  padding-left: 20px; /* 添加左侧缩进 */
}

.tips-list li .el-icon {
  font-size: 18px;
  color: #67C23A;
  margin-top: 0;
  flex-shrink: 0;
  margin-left: -20px; /* 图标向左偏移，与缩进对齐 */
}

.features-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.feature-icon {
  font-size: 28px;
  margin-top: 2px;
  flex-shrink: 0;
}

.feature-title {
  font-weight: 600;
  color: white;
  font-size: 18px;
  margin-bottom: 6px;
}

.feature-desc {
  font-size: 15px;
  color: white;
}

:deep(.el-card__header) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 20px 20px 0 0;
  padding: 24px 32px;
}

.tips-card :deep(.el-card__header),
.features-card :deep(.el-card__header) {
  background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
  color: #303133;
}

:deep(.el-card__body) {
  padding: 40px;
}

:deep(.el-button) {
  font-size: 16px;
}

:deep(.el-button--large) {
  font-size: 18px;
  padding: 14px 24px;
}

:deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #dcdfe6 inset;
  transition: all 0.3s;
}

:deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

:deep(.el-input.is-focus .el-input__wrapper) {
  box-shadow: 0 0 0 1px #409EFF inset;
}

@media (max-width: 768px) {
  .welcome-title {
    font-size: 24px;
  }
  
  .welcome-desc {
    font-size: 14px;
  }
  
  .form-row {
    margin-bottom: 0;
  }
  
  .tips-section {
    margin-top: 20px;
  }
}
</style>
