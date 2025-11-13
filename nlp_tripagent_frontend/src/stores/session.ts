import { defineStore } from 'pinia'
import { ChatMessage, SessionState } from '../types/session'
import { vaiageApiService } from '../services/vaiageApi'

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    sessionId: null,
    messages: [
      {
        type: 'assistant',
        content: `Welcome to your Travel AI Assistant! Tell me your name, and I'll help you plan your perfect trip. Let's start by gathering some information:
<ul>
  <li>Which city would you like to visit?</li>
  <li>How many days will you stay?</li>
  <li>What's your budget (low, medium, high)?</li>
  <li>How many people are traveling?</li>
  <li>Are you traveling with children, pets, or have any special requirements?</li>
  <li>What type of activities do you enjoy (e.g., adventure, relaxation, culture)?</li>
  <li>What's your health condition?</li>
</ul>`,
        timestamp: new Date()
      }
    ],
    step: 'chat',
    userInfo: {},
    attractions: [],
    selectedAttractions: [],
    itinerary: null,
    budget: null,
    confirmation: '',
    ai_recommendation_generated: false,
    user_input_processed: false
  }),

  getters: {
    // 检查会话是否活跃
    isActive: (state) => state.sessionId !== null,
    
    // 获取最后一条消息
    lastMessage: (state) => state.messages.length > 0 ? state.messages[state.messages.length - 1] : null,
    
    // 获取用户消息数量
    userMessageCount: (state) => state.messages.filter(msg => msg.type === 'user').length
  },

  actions: {
    // 初始化新会话
    async initializeSession(sessionId?: string) {
      this.sessionId = sessionId || this.generateSessionId()
      
      // 保留欢迎消息，清空其他消息
      this.messages = [
        {
          type: 'assistant',
          content: `Welcome to your Travel AI Assistant! Tell me your name, and I'll help you plan your perfect trip. Let's start by gathering some information:
<ul>
  <li>Which city would you like to visit?</li>
  <li>How many days will you stay?</li>
  <li>What's your budget (low, medium, high)?</li>
  <li>How many people are traveling?</li>
  <li>Are you traveling with children, pets, or have any special requirements?</li>
  <li>What type of activities do you enjoy (e.g., adventure, relaxation, culture)?</li>
  <li>What's your health condition?</li>
</ul>`,
          timestamp: new Date()
        }
      ]
      
      this.step = 'chat'
      this.userInfo = {}
      this.attractions = []
      this.selectedAttractions = []
      this.itinerary = null
      this.budget = null
      this.confirmation = ''
      this.confirmation = ''
      this.ai_recommendation_generated = false
      this.user_input_processed = false
      
      // 同步到API服务
       if (this.sessionId) {
         vaiageApiService.setSessionId(this.sessionId)
       }
    },

    // 恢复现有会话
     async restoreSession() {
       if (this.sessionId && this.isActive) {
         // 同步到API服务
         vaiageApiService.setSessionId(this.sessionId)
         return true
       }
       return false
     },

    // 添加消息
    addMessage(message: ChatMessage) {
      this.messages.push(message)
    },

    // 添加用户消息
    addUserMessage(content: string) {
      this.addMessage({
        type: 'user',
        content,
        timestamp: new Date()
      })
    },

    // 添加助手消息
    addAssistantMessage(content: string) {
      this.addMessage({
        type: 'assistant',
        content,
        timestamp: new Date()
      })
    },

    // 更新会话状态
    updateState(updates: Partial<Omit<SessionState, 'sessionId' | 'messages'>>) {
      Object.assign(this, updates)
    },

    // 更新步骤
    setStep(step: string) {
      this.step = step
    },

    // 更新用户信息
    updateUserInfo(info: Record<string, any>) {
      this.userInfo = { ...this.userInfo, ...info }
    },

    // 重置会话（完全清空）
    async resetSession() {
      this.sessionId = null
      this.messages = [
        {
          type: 'assistant',
          content: `Welcome to your Travel AI Assistant! Tell me your name, and I'll help you plan your perfect trip. Let's start by gathering some information:
<ul>
  <li>Which city would you like to visit?</li>
  <li>How many days will you stay?</li>
  <li>What's your budget (low, medium, high)?</li>
  <li>How many people are traveling?</li>
  <li>Are you traveling with children, pets, or have any special requirements?</li>
  <li>What type of activities do you enjoy (e.g., adventure, relaxation, culture)?</li>
  <li>What's your health condition?</li>
</ul>`,
          timestamp: new Date()
        }
      ]
      this.step = 'chat'
      this.userInfo = {}
      this.attractions = []
      this.selectedAttractions = []
      this.itinerary = null
      this.budget = null
      this.confirmation = ''
      this.ai_recommendation_generated = false
      this.user_input_processed = false
      
      // 同步到API服务
       vaiageApiService.setSessionId(null)
    },

    // 生成会话ID
    generateSessionId(): string {
      return 'vaiage_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
    },

    // 添加景点到推荐列表
    setAttractions(attractions: any[]) {
      this.attractions = attractions
    },

    // 添加景点到已选列表
    addSelectedAttraction(attraction: any) {
      if (!this.selectedAttractions.some(a => a.id === attraction.id)) {
        this.selectedAttractions.push(attraction)
      }
    },

    // 从已选列表移除景点
    removeSelectedAttraction(attractionId: string) {
      this.selectedAttractions = this.selectedAttractions.filter(a => a.id !== attractionId)
    },

    // 清空已选景点列表
    clearSelectedAttractions() {
      this.selectedAttractions = []
    },

    // 检查景点是否已选
    isAttractionSelected(attractionId: string): boolean {
      return this.selectedAttractions.some(a => a.id === attractionId)
    }
  },

  // 持久化配置
  persist: true
})