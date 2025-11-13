export interface ChatMessage {
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface SessionState {
  sessionId: string | null
  messages: ChatMessage[]
  step: string
  userInfo: Record<string, any>
  attractions: any[]
  selectedAttractions: any[]
  itinerary: any
  budget: any
  ai_recommendation_generated: boolean
  user_input_processed: boolean
}