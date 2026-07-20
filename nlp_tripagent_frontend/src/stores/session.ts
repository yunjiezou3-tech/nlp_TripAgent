import { defineStore } from 'pinia'
import type { CandidateDelta, ChatMessage, PlaceCandidate, SessionState } from '../types/session'
import { vaiageApiService } from '../services/vaiageApi'

function appendUniqueCandidates(current: PlaceCandidate[], incoming: PlaceCandidate[] = []) {
  const merged = [...current]
  const seenIds = new Set(current.map((candidate) => String(candidate.id)))

  for (const candidate of incoming) {
    if (!candidate?.id) continue
    const id = String(candidate.id)
    if (seenIds.has(id)) continue
    seenIds.add(id)
    merged.push({ ...candidate, id })
  }

  return merged
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    sessionId: null,
    messages: [
      {
        type: 'assistant',
        content: `欢迎来到你的旅行规划助手！先告诉我一些基本信息，我就能帮你规划行程，后面也可以继续帮你生成机票和酒店的待确认订单草稿：
<ul>
  <li>想去哪个城市？玩几天？</li>
  <li>预算大概是多少？几个人出行？</li>
  <li>喜欢什么活动？有没有亲子、无障碍、饮食等特殊需求？</li>
  <li>住宿有什么偏好？比如地铁方便、带早餐、亲子友好、景点附近。</li>
</ul>`,
        timestamp: new Date()
      }
    ],
    step: 'chat',
    userInfo: {},
    attractions: [],
    selectedAttractions: [],
    restaurants: [],
    hotels: [],
    selectedRestaurants: [],
    selectedHotel: null,
    placeErrors: {},
    itinerary: null,
    budget: null,
    confirmation: '',
    hotelRecommendations: [],
    bookingDrafts: {},
    bookingMissingFields: [],
    bookingMode: null,
    bookingCandidates: {},
    candidateDelta: {},
    informationRefinement: null,
    informationMessage: null,
    candidateSearchState: {},
    candidatePriceContext: {},
    currentDate: null,
    tripDateStatus: null,
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
          content: `欢迎来到你的旅行规划助手！先告诉我一些基本信息，我就能帮你规划行程，后面也可以继续帮你生成机票和酒店的待确认订单草稿：
<ul>
  <li>想去哪个城市？玩几天？</li>
  <li>预算大概是多少？几个人出行？</li>
  <li>喜欢什么活动？有没有亲子、无障碍、饮食等特殊需求？</li>
  <li>住宿有什么偏好？比如地铁方便、带早餐、亲子友好、景点附近。</li>
</ul>`,
          timestamp: new Date()
        }
      ]
      
      this.step = 'chat'
      this.userInfo = {}
      this.attractions = []
      this.selectedAttractions = []
      this.restaurants = []
      this.hotels = []
      this.selectedRestaurants = []
      this.selectedHotel = null
      this.placeErrors = {}
      this.itinerary = null
      this.budget = null
      this.confirmation = ''
      this.hotelRecommendations = []
      this.bookingDrafts = {}
      this.bookingMissingFields = []
      this.bookingMode = null
      this.bookingCandidates = {}
      this.candidateDelta = {}
      this.informationRefinement = null
      this.informationMessage = null
      this.candidateSearchState = {}
      this.candidatePriceContext = {}
      this.currentDate = null
      this.tripDateStatus = null
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
          content: `欢迎来到你的旅行规划助手！先告诉我一些基本信息，我就能帮你规划行程，后面也可以继续帮你生成机票和酒店的待确认订单草稿：
<ul>
  <li>想去哪个城市？玩几天？</li>
  <li>预算大概是多少？几个人出行？</li>
  <li>喜欢什么活动？有没有亲子、无障碍、饮食等特殊需求？</li>
  <li>住宿有什么偏好？比如地铁方便、带早餐、亲子友好、景点附近。</li>
</ul>`,
          timestamp: new Date()
        }
      ]
      this.step = 'chat'
      this.userInfo = {}
      this.attractions = []
      this.selectedAttractions = []
      this.restaurants = []
      this.hotels = []
      this.selectedRestaurants = []
      this.selectedHotel = null
      this.placeErrors = {}
      this.itinerary = null
      this.budget = null
      this.confirmation = ''
      this.hotelRecommendations = []
      this.bookingDrafts = {}
      this.bookingMissingFields = []
      this.bookingMode = null
      this.bookingCandidates = {}
      this.candidateDelta = {}
      this.informationRefinement = null
      this.informationMessage = null
      this.candidateSearchState = {}
      this.candidatePriceContext = {}
      this.currentDate = null
      this.tripDateStatus = null
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
    setAttractions(attractions: PlaceCandidate[]) {
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
    },

    setRestaurants(restaurants: PlaceCandidate[]) {
      this.restaurants = restaurants
    },

    setHotels(hotels: PlaceCandidate[]) {
      this.hotels = hotels
    },

    mergeCandidateDelta(delta: CandidateDelta = {}) {
      this.attractions = appendUniqueCandidates(this.attractions, delta.attractions)
      this.restaurants = appendUniqueCandidates(this.restaurants, delta.restaurants)
      this.hotels = appendUniqueCandidates(this.hotels, delta.hotels)
      this.candidateDelta = delta
    },

    toggleSelectedRestaurant(restaurant: any) {
      if (!restaurant?.id) return
      if (this.selectedRestaurants.some(item => item.id === restaurant.id)) {
        this.selectedRestaurants = this.selectedRestaurants.filter(item => item.id !== restaurant.id)
      } else {
        this.selectedRestaurants.push(restaurant)
      }
    },

    isRestaurantSelected(restaurantId: string): boolean {
      return this.selectedRestaurants.some(item => item.id === restaurantId)
    },

    setSelectedHotel(hotel: any | null) {
      this.selectedHotel = hotel
    }
  },

  // 持久化配置
  persist: true
})
