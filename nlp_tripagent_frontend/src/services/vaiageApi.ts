import { apiClient } from './apiClient'

export interface TravelRequest {
  origin: string
  destination: string
  days: number
  preferences: string
}

export interface TravelResponse {
  response: string
  next_step?: string
  missing_fields?: string[]
  state?: any
  attractions?: any[]
  map_data?: any
  itinerary?: any
  budget?: any
  optimal_route?: any
  rental_post?: any
}

export interface ChatMessage {
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export class VaiageApiService {
  private sessionId: string | null = null

  // Initialize session
  async initializeSession(): Promise<string> {
    try {
      // Generate a new session ID - backend will handle session creation when needed
      this.sessionId = this.generateSessionId()
      return this.sessionId
    } catch (error) {
      console.error('Failed to initialize session:', error)
      this.sessionId = this.generateSessionId()
      return this.sessionId
    }
  }

  // Process chat message
  async processChatMessage(userInput: string): Promise<TravelResponse> {
    if (!this.sessionId) {
      await this.initializeSession()
    }

    try {
      const response = await apiClient.post('/api/process', {
        step: 'chat',
        user_input: userInput,
        session_id: this.sessionId
      })
      
      return response.data
    } catch (error) {
      console.error('Failed to process chat message:', error)
      throw new Error('Failed to process your message. Please try again.')
    }
  }

  // Stream chat message for real-time responses
  async streamChatMessage(
    userInput: string,
    onChunk: (chunk: any) => void,
    options?: {
      step?: string
      selectedAttractionIds?: string[]
      aiRecommendationGenerated?: boolean
      userInputProcessed?: boolean
    }
  ): Promise<TravelResponse> {
    if (!this.sessionId) {
      await this.initializeSession()
    }

    return new Promise((resolve, reject) => {
      const params = new URLSearchParams({
        step: options?.step || 'chat',
        user_input: userInput,
        session_id: this.sessionId || ''
      })

      if (options?.selectedAttractionIds && options.selectedAttractionIds.length > 0) {
        params.append('selected_attraction_ids', JSON.stringify(options.selectedAttractionIds))
      }

      if (options?.aiRecommendationGenerated !== undefined) {
        params.append('ai_recommendation_generated', String(options.aiRecommendationGenerated))
      }

      if (options?.userInputProcessed !== undefined) {
        params.append('user_input_processed', String(options.userInputProcessed))
      }

      const eventSource = new EventSource(`${apiClient.defaults.baseURL}/api/stream?${params.toString()}`)

      let completeData: TravelResponse | null = null

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (data.type === 'chunk') {
            onChunk(data.content)
          } else if (data.type === 'complete') {
            completeData = {
              response: data.response || '',
              next_step: data.next_step,
              missing_fields: data.missing_fields,
              state: data.state,
              attractions: data.attractions,
              map_data: data.map_data,
              itinerary: data.itinerary,
              budget: data.budget,
              optimal_route: data.optimal_route,
              rental_post: data.rental_post
            }
            eventSource.close()
            resolve(completeData)
          }
        } catch (error) {
          console.error('Error parsing stream data:', error)
          eventSource.close()
          reject(error)
        }
      }

      eventSource.onerror = (error) => {
        console.error('EventSource error:', error)
        completeData = null
        eventSource.close()
        reject(new Error('Connection to travel assistant failed'))
      }

      // Set timeout for safety
      setTimeout(() => {
        if (!completeData) {
          eventSource.close()
          reject(new Error('Request timeout'))
        }
      }, 60000) // 60 seconds timeout
    })
  }

  // Get attractions for a city
  async getAttractions(city: string): Promise<any[]> {
    if (!this.sessionId) {
      await this.initializeSession()
    }

    try {
      const response = await apiClient.get(`/api/attractions/${encodeURIComponent(city)}`)
      return response.data
    } catch (error) {
      console.error('Failed to get attractions:', error)
      return []
    }
  }

  // Reset session
  async resetSession(): Promise<void> {
    try {
      await apiClient.get('/api/reset')
      this.sessionId = null
    } catch (error) {
      console.error('Failed to reset session:', error)
    }
  }

  // Process travel planning request
  async planTrip(request: TravelRequest): Promise<TravelResponse> {
    if (!this.sessionId) {
      await this.initializeSession()
    }

    // Construct a comprehensive user input based on the form data
    const userInput = `I want to plan a trip from ${request.origin} to ${request.destination} for ${request.days} days. My preferences are: ${request.preferences}`

    return await this.processChatMessage(userInput)
  }

  // Get current session ID
  getSessionId(): string | null {
    return this.sessionId
  }

  // Set session ID (for restoring existing sessions)
  setSessionId(sessionId: string): void {
    this.sessionId = sessionId
  }

  private generateSessionId(): string {
    return 'vaiage_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
  }
}

export const vaiageApiService = new VaiageApiService()