<template>
  <div class="results-page">
    <div class="welcome-section">
      <h1 class="welcome-title">Your Travel Plan</h1>
      <p class="welcome-desc">Your personalized itinerary is ready!</p>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">Travel Dates</span>
          <span class="summary-value">{{ tripSummary.startDate || 'TBD' }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Duration</span>
          <span class="summary-value">{{ tripSummary.days }} days</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Attractions Planned</span>
          <span class="summary-value">{{ tripSummary.totalAttractions }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Estimated Budget</span>
          <span class="summary-value">{{ budget ? `$${budget.total}` : '$0' }}</span>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="main-content">
      <el-row :gutter="24" class="layout-row">
        <!-- 左侧：行程信息 -->
        <el-col :xs="24" :sm="24" :md="16" :lg="16" :xl="16">
          <!-- 行程概览 -->
          <el-card class="itinerary-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon :size="24"><Calendar /></el-icon>
                <span>Your Itinerary</span>
              </div>
            </template>
            
            <div class="itinerary-content">
              <div v-if="hasItinerary" class="days-section">
                <h3>{{ tripSummary.days }} Days in {{ tripSummary.destination }}</h3>
                
                <el-timeline>
                  <el-timeline-item 
                    v-for="day in itinerary" 
                    :key="day.day"
                    :timestamp="`Day ${day.day}`"
                    placement="top"
                  >
                    <el-card shadow="never">
                      <h4>Day {{ day.day }} · {{ day.date }}</h4>
                      
                      <div v-if="day.spots && day.spots.length" class="activities-list">
                        <div 
                          v-for="(spot, activityIndex) in day.spots" 
                          :key="`${day.day}-${activityIndex}`"
                          class="activity-item"
                        >
                          <el-icon><Location /></el-icon>
                          <span>{{ spot.name || 'Activity' }}</span>
                          <span class="activity-time">{{ spot.start_time || '' }} - {{ spot.end_time || '' }}</span>
                        </div>
                      </div>
                      <el-empty v-else description="No activities planned" :image-size="60" />
                    </el-card>
                  </el-timeline-item>
                </el-timeline>
              </div>
              
              <el-empty v-else description="No itinerary data available" :image-size="100" />
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：预算和确认 -->
        <el-col :xs="24" :sm="24" :md="8" :lg="8" :xl="8" class="right-column">
          <!-- 预算估算 -->
          <el-card class="budget-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon :size="24"><Money /></el-icon>
                <span>Budget Estimate</span>
              </div>
            </template>
            
            <div class="budget-content">
              <div v-if="budget" class="budget-items">
                <div class="budget-item">
                  <span class="budget-label">Airfare:</span>
                  <span class="budget-value">{{ budget.airfare ? `$${budget.airfare}` : '$0' }}</span>
                </div>
                <div class="budget-item">
                  <span class="budget-label">Hotel:</span>
                  <span class="budget-value">{{ budget.accommodation ? `$${budget.accommodation}` : '$0' }}</span>
                </div>
                <div class="budget-item">
                  <span class="budget-label">Food:</span>
                  <span class="budget-value">{{ budget.food ? `$${budget.food}` : '$0' }}</span>
                </div>
                <div class="budget-item">
                  <span class="budget-label">Tickets:</span>
                  <span class="budget-value">{{ budget.attractions ? `$${budget.attractions}` : '$0' }}</span>
                </div>
                <div class="budget-item">
                  <span class="budget-label">Transportation:</span>
                  <span class="budget-value">{{ budget.transport ? `$${budget.transport}` : '$0' }}</span>
                </div>
                <div v-if="budget.car_rental" class="budget-item">
                  <span class="budget-label">Car Rental:</span>
                  <span class="budget-value">{{ `$${budget.car_rental}` }}</span>
                </div>
                <div v-if="budget.fuel_cost" class="budget-item">
                  <span class="budget-label">Fuel:</span>
                  <span class="budget-value">{{ `$${budget.fuel_cost}` }}</span>
                </div>
                <el-divider />
                <div class="budget-total">
                  <span class="budget-label">Total:</span>
                  <span class="budget-value total">{{ budget.total ? `$${budget.total}` : '$0' }}</span>
                </div>
              </div>
              
              <el-empty v-else description="No budget data available" :image-size="80" />
            </div>
          </el-card>

          <!-- 行程确认 -->
          <el-card class="confirmation-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon :size="24"><CircleCheck /></el-icon>
                <span>Trip Confirmation</span>
              </div>
            </template>
            
            <div class="confirmation-content">
              <el-descriptions :column="1" border>
                <el-descriptions-item label="Departure">
                  <el-tag type="info" size="large">{{ request?.origin || '-' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Destination">
                  <el-tag type="success" size="large">{{ request?.destination || '-' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Travel Days">
                  <el-tag size="large">{{ tripSummary.days }} days</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Start Date">
                  <el-tag type="warning" size="large">{{ tripSummary.startDate || '-' }}</el-tag>
                </el-descriptions-item>
              </el-descriptions>
              
              <div class="confirmation-actions">
                <el-button type="primary" size="large" @click="router.push('/')" class="action-button">
                  <el-icon><Edit /></el-icon>
                  Replan
                </el-button>
                <el-button type="success" size="large" class="action-button">
                  <el-icon><CircleCheck /></el-icon>
                  Confirm Trip
                </el-button>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'

// 图标导入
import {
  Calendar,
  Money,
  CircleCheck,
  Edit
} from '@element-plus/icons-vue'

const router = useRouter()
const sessionStore = useSessionStore()

const itinerary = computed(() => {
  const value = sessionStore.itinerary
  return Array.isArray(value) ? value : []
})

const hasItinerary = computed(() => itinerary.value.length > 0)

const budget = computed(() => sessionStore.budget || null)

const request = computed(() => sessionStore.userInfo || {})

const tripSummary = computed(() => ({
  days: request.value?.days || itinerary.value.length || 0,
  destination: request.value?.destination || 'Destination',
  totalAttractions: itinerary.value.reduce((count, day) => count + (Array.isArray(day?.spots) ? day.spots.length : 0), 0),
  startDate: request.value?.start_date || itinerary.value[0]?.date || ''
}))
</script>

<style scoped>
.results-page {
  min-height: 100vh;
  background: transparent;
  padding: 20px;
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-top: 24px;
}

.summary-item {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.summary-label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: white;
}

.main-content {
  max-width: 1400px;
  margin: 0 auto;
}

.layout-row {
  margin: 0 !important;
  align-items: stretch;
}

.layout-row :deep(.el-col) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.itinerary-card {
  margin-bottom: 24px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许flex项目收缩 */
}

.itinerary-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.itinerary-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.days-section {
  flex: 1;
  min-height: 0;
}

/* 右侧列容器 */
.right-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 右侧卡片容器 */
.right-column > .budget-card,
.right-column > .confirmation-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.right-column > .budget-card {
  margin-bottom: 0;
}

.right-column > .confirmation-card {
  margin-top: 24px;
  margin-bottom: 0;
}

.budget-card :deep(.el-card__body),
.confirmation-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.el-card) {
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

:deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.2);
  border-radius: 20px 20px 0 0;
  padding: 20px;
}

:deep(.el-card__body) {
  background: transparent;
  border-radius: 0 0 20px 20px;
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  color: #2c3e50;
}

.card-header .el-icon {
  color: #409EFF;
}

.budget-card {
  margin-bottom: 0;
}

.confirmation-card {
  margin-top: 24px;
  margin-bottom: 0;
}

.itinerary-content h3 {
  color: #2c3e50;
  margin-bottom: 20px;
  font-size: 1.5rem;
}

.activities-list {
  margin-top: 15px;
}

.activity-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-item .el-icon {
  color: #409EFF;
}

.activity-time {
  margin-left: auto;
  color: #909399;
  font-size: 0.9rem;
}

.budget-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.budget-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.budget-label {
  color: #5a6c7d;
  font-weight: 500;
}

.budget-value {
  color: #2c3e50;
  font-weight: 600;
}

.budget-total {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 2px solid rgba(0, 0, 0, 0.1);
}

.budget-total .budget-value {
  font-size: 1.2rem;
  color: #409EFF;
}

.confirmation-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.confirmation-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
}

.action-button {
  flex: 1;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .results-page {
    padding: 10px;
  }
  
  .title-container {
    padding: 20px;
    max-width: 100%;
  }
  
  .page-title {
    font-size: 2rem;
  }
  
  .page-subtitle {
    font-size: 1rem;
  }
  
  .confirmation-actions {
    flex-direction: column;
  }
}
</style>