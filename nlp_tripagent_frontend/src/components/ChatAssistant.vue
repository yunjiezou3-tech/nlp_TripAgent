<template>
  <div class="chat-assistant">
    <!-- Chat Header -->
    <div class="chat-header">
      <el-icon><ChatDotRound /></el-icon>
      <span>Your Travel Assistant</span>
    </div>

    <!-- Chat Messages - 添加固定高度和滚动 -->
    <div class="chat-messages" ref="messagesContainer">
      <div 
        v-for="(message, index) in messages" 
        :key="index" 
        :class="['message', message.type]"
      >
        <div class="message-avatar">
          <el-icon v-if="message.type === 'assistant'">
            <UserFilled />
          </el-icon>
          <el-icon v-else>
            <User />
          </el-icon>
        </div>
        <div class="message-content">
          <div class="message-text" v-html="formatMessage(message.content)"></div>
          <div class="message-time">{{ formatTime(message.timestamp) }}</div>
        </div>
      </div>

      <!-- Loading Indicator -->
      <div v-if="loading" class="message assistant">
        <div class="message-avatar">
          <el-icon><UserFilled /></el-icon>
        </div>
        <div class="message-content">
          <div class="loading-indicator">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>Thinking...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Chat Input -->
    <div class="chat-input-container">
      <div class="input-group">
        <el-input
          v-model="userInput"
          placeholder="Start your dream journey from here..."
          :disabled="loading"
          @keyup.enter="sendMessage"
          size="large"
        >
          <template #append>
            <el-button 
              type="primary" 
              :loading="loading"
              @click="sendMessage"
              :disabled="!userInput.trim()"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>
      
      <div class="input-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>Be specific about your travel preferences to get better recommendations.</span>
      </div>

      <!-- Missing Fields Alert -->
      <div v-if="missingFields.length > 0" class="missing-fields-alert">
        <el-alert
          title="Missing Information"
          :description="`Please provide: ${missingFields.join(', ')}`"
          type="warning"
          show-icon
          :closable="false"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  ChatDotRound, 
  UserFilled, 
  User, 
  Loading, 
  Promotion, 
  InfoFilled 
} from '@element-plus/icons-vue'
import { vaiageApiService } from '../services/vaiageApi'
import type { TravelResponse } from '../services/vaiageApi'
import { useSessionStore } from '../stores/session'
import { useRouter, useRoute } from 'vue-router'

const sessionStore = useSessionStore()
const router = useRouter()
const route = useRoute()
const messages = ref(sessionStore.messages)
const userInput = ref('')
const loading = ref(false)
const missingFields = ref<string[]>([])
const messagesContainer = ref<HTMLElement>()

const handleCompletedResponse = async (response: TravelResponse, assistantAccumulated: string) => {
  if (response.response && response.response !== assistantAccumulated) {
    const lastMessageIndex = sessionStore.messages.length - 1
    if (lastMessageIndex >= 0 && sessionStore.messages[lastMessageIndex].type === 'assistant') {
      sessionStore.messages[lastMessageIndex].content = response.response
    } else {
      sessionStore.addAssistantMessage(response.response)
    }
  }

  if (response.missing_fields && response.missing_fields.length > 0) {
    missingFields.value = response.missing_fields
  } else {
    missingFields.value = []
  }

  if (response.next_step) {
    sessionStore.setStep(response.next_step)
  }

  if (response.state) {
    sessionStore.updateState({
      userInfo: response.state.user_info || {},
      attractions: response.state.attractions || [],
      selectedAttractions: response.state.selected_attractions || [],
      itinerary: response.state.itinerary || null,
      budget: response.state.budget || null
    })
  }

  if (response.itinerary) {
    sessionStore.itinerary = response.itinerary as any
  }
  if (response.budget) {
    sessionStore.budget = response.budget
  }
  if (response.ai_recommendation_generated !== undefined) {
    sessionStore.ai_recommendation_generated = response.ai_recommendation_generated
  }
  if (response.user_input_processed !== undefined) {
    sessionStore.user_input_processed = response.user_input_processed
  }

  if (response.session_id) {
    vaiageApiService.setSessionId(response.session_id)
    sessionStore.sessionId = response.session_id
  }

  const nextStep = response.next_step || sessionStore.step
  if (nextStep && ['strategy', 'route', 'complete'].includes(nextStep)) {
    if (route.path !== '/results') {
      await nextTick()
      router.push('/results')
    }
  }
}

// Format message content with markdown-like formatting
const formatMessage = (content: string) => {
  // Convert markdown-like formatting to HTML
  return content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

// Format timestamp
const formatTime = (timestamp: Date | string) => {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp)
  return date.toLocaleTimeString('en-US', { 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

// Scroll to bottom of messages
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// Send message to AI assistant
const sendMessage = async () => {
  const input = userInput.value.trim()
  if (!input || loading.value) return

  // Add user message using session store
  sessionStore.addUserMessage(input)
  userInput.value = ''
  loading.value = true
  missingFields.value = []

  await scrollToBottom()

  try {
    // Use streaming for real-time responses
    let assistantResponse = ''

    const stepOption = sessionStore.step || 'chat'
    const selectedIdsForStep =
      stepOption === 'recommend'
        ? sessionStore.selectedAttractions
            .map((item: any) => item?.id)
            .filter((id: string | null | undefined): id is string => !!id)
        : undefined
    
    const response = await vaiageApiService.streamChatMessage(input, (chunk) => {
      assistantResponse += chunk
      
      // Update the last message with streaming content using session store
      const lastMessageIndex = sessionStore.messages.length - 1
      if (lastMessageIndex >= 0 && sessionStore.messages[lastMessageIndex].type === 'assistant') {
        // Update existing assistant message
        sessionStore.messages[lastMessageIndex].content = assistantResponse
      } else {
        // Add new assistant message
        sessionStore.addAssistantMessage(assistantResponse)
      }
      
      scrollToBottom()
    }, {
      step: stepOption,
      selectedAttractionIds: selectedIdsForStep,
      aiRecommendationGenerated: sessionStore.ai_recommendation_generated,
      userInputProcessed: sessionStore.user_input_processed
    })

    await handleCompletedResponse(response, assistantResponse)

  } catch (error) {
    console.error('Failed to send message:', error)
    ElMessage.error('Failed to send message. Please try again.')
    
    // Add error message using session store
    sessionStore.addAssistantMessage('Sorry, I encountered an error. Please try again.')
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

// 监听消息变化，确保滚动到底部
watch(() => sessionStore.messages, (newMessages) => {
  messages.value = newMessages
  if (messagesContainer.value) {
    scrollToBottom()
  }
}, { deep: true })

// Initialize chat session
onMounted(async () => {
  try {
    // 如果会话不存在，初始化新会话
    if (!sessionStore.isActive) {
      await vaiageApiService.initializeSession()
      const sessionId = vaiageApiService.getSessionId()
      if (sessionId) {
        await sessionStore.initializeSession(sessionId)
      }
    } else {
      // 恢复现有会话
      await sessionStore.restoreSession()
    }
    
    // 确保消息列表与存储同步
    messages.value = sessionStore.messages
  } catch (error) {
    console.error('Failed to initialize chat session:', error)
    ElMessage.warning('Chat session initialization failed. Some features may not work properly.')
  }
})
</script>

<style scoped>
.chat-assistant {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 800px;
  min-height: 600px;
  background: white;
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 32px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 20px;
  font-weight: 600;
  flex-shrink: 0; /* 防止头部被压缩 */
}

.chat-header .el-icon {
  font-size: 24px;
}

.chat-messages {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  background: #f8f9fa;
  min-height: 200px; /* 确保最小高度 */
  max-height: calc(100% - 200px); /* 计算最大高度，减去头部和输入区域 */
}

.message {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.message.assistant {
  flex-direction: row;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 4px;
}

.message.assistant .message-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.message.user .message-avatar {
  background: #409EFF;
  color: white;
}

.message-content {
  max-width: 75%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message.user .message-content {
  align-items: flex-end;
}

.message-text {
  padding: 16px 20px;
  border-radius: 18px;
  line-height: 1.6;
  word-wrap: break-word;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.message.assistant .message-text {
  background: white;
  color: #333;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: 4px;
}

.message.user .message-text {
  background: #409EFF;
  color: white;
  border-bottom-right-radius: 4px;
}

.message-time {
  font-size: 12px;
  color: #909399;
  padding: 0 8px;
}

.message.user .message-time {
  text-align: right;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-style: italic;
  padding: 16px 20px;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.chat-input-container {
  padding: 24px 32px;
  background: white;
  border-top: 1px solid #e4e7ed;
  flex-shrink: 0; /* 防止输入区域被压缩 */
}

.input-group {
  margin-bottom: 16px;
}

.input-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
  margin-bottom: 16px;
  padding: 8px 0;
}

.missing-fields-alert {
  margin-top: 16px;
}

/* 美化滚动条 */
.chat-messages::-webkit-scrollbar {
  width: 8px;
}

.chat-messages::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chat-header {
    padding: 16px 20px;
    font-size: 18px;
  }
  
  .chat-messages {
    padding: 16px 20px;
  }
  
  .chat-input-container {
    padding: 16px 20px;
  }
  
  .message-content {
    max-width: 85%;
  }
  
  .message-text {
    padding: 12px 16px;
  }
}
</style>

<style>
/* 全局样式用于调整列表对齐 - 修复分点对齐问题 */
.message.assistant .message-text ul {
  margin: 12px 0;
  padding-left: 0;
  list-style: none;
}

.message.assistant .message-text li {
  margin-bottom: 8px;
  line-height: 1.5;
  position: relative;
  padding-left: 0;
}

/* 确保分点符号与主文本左对齐 */
.message.assistant .message-text li::before {
  content: "•";
  color: #667eea;
  font-weight: bold;
  display: inline-block;
  width: 1em;
  margin-left: 0;
  position: absolute;
  left: 0;
  top: 0;
}

/* 调整列表项内容的位置，确保分点符号与主文本对齐 */
.message.assistant .message-text li {
  padding-left: 1.2em;
  text-indent: 0;
}

/* 确保主文本和分点文本的对齐一致性 */
.message.assistant .message-text {
  text-align: left;
}

/* 确保整个消息内容的对齐一致性 */
.message.assistant .message-content {
  align-items: flex-start;
}
</style>