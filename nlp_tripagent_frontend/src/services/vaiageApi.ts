import { apiClient } from './apiClient'
import type {
  CandidateDelta,
  CandidatePriceContext,
  CandidateSearchState,
  InformationRefinement,
  PlaceCandidate,
  TripDateStatus
} from '../types/session'

export interface TravelRequest {
  origin: string
  destination: string
  days: number
  preferences: string
}

export interface TravelResponse {
  response: string
  next_step?: string
  session_id?: string
  missing_fields?: string[]
  state?: any
  attractions?: PlaceCandidate[]
  restaurants?: PlaceCandidate[]
  hotels?: PlaceCandidate[]
  place_errors?: Record<string, string>
  map_data?: any
  itinerary?: any
  budget?: any
  optimal_route?: any
  rental_post?: any
  ai_recommendation_generated?: boolean
  user_input_processed?: boolean
  hotel_recommendations?: any[]
  booking_drafts?: Record<string, any>
  booking_missing_fields?: string[]
  booking_mode?: string | null
  booking_candidates?: Record<string, any>
  candidate_delta?: CandidateDelta
  information_refinement?: InformationRefinement | null
  information_message?: string | null
  candidate_search_state?: CandidateSearchState
  candidate_price_context?: CandidatePriceContext
  current_date?: string
  trip_date_status?: TripDateStatus
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
      selectedRestaurantIds?: string[]
      selectedHotelId?: string
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

      if (options?.selectedRestaurantIds) {
        params.append('selected_restaurant_ids', JSON.stringify(options.selectedRestaurantIds))
      }

      if (options?.selectedHotelId) {
        params.append('selected_hotel_id', options.selectedHotelId)
      }

      if (options?.aiRecommendationGenerated !== undefined) {
        params.append('ai_recommendation_generated', String(options.aiRecommendationGenerated))
      }

      if (options?.userInputProcessed !== undefined) {
        params.append('user_input_processed', String(options.userInputProcessed))
      }

      const eventSource = new EventSource(`${apiClient.defaults.baseURL}/api/stream?${params.toString()}`)

      let completeData: TravelResponse | null = null
      const requestTimeout = window.setTimeout(() => {
        eventSource.close()
        reject(new Error('Request timeout'))
      }, 180000)

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (data.type === 'chunk') {
            onChunk(data.content)
          } else if (data.type === 'complete') {
            completeData = {
              response: data.response || '',
              next_step: data.next_step,
              session_id: data.session_id,
              missing_fields: data.missing_fields,
              state: data.state,
              attractions: data.attractions,
              restaurants: data.restaurants,
              hotels: data.hotels,
              place_errors: data.place_errors,
              map_data: data.map_data,
              itinerary: data.itinerary,
              budget: data.budget,
              optimal_route: data.optimal_route,
              rental_post: data.rental_post,
              ai_recommendation_generated: data.ai_recommendation_generated,
              user_input_processed: data.user_input_processed,
              hotel_recommendations: data.hotel_recommendations,
              booking_drafts: data.booking_drafts,
              booking_missing_fields: data.booking_missing_fields,
              booking_mode: data.booking_mode,
              booking_candidates: data.booking_candidates,
              candidate_delta: data.candidate_delta,
              information_refinement: data.information_refinement,
              information_message: data.information_message,
              candidate_search_state: data.candidate_search_state,
              candidate_price_context: data.candidate_price_context,
              current_date: data.current_date,
              trip_date_status: data.trip_date_status
            }
            window.clearTimeout(requestTimeout)
            eventSource.close()
            resolve(completeData)
          }
        } catch (error) {
          console.error('Error parsing stream data:', error)
          window.clearTimeout(requestTimeout)
          eventSource.close()
          reject(error)
        }
      }

      eventSource.onerror = (error) => {
        console.error('EventSource error:', error)
        completeData = null
        window.clearTimeout(requestTimeout)
        eventSource.close()
        reject(new Error('Connection to travel assistant failed'))
      }
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
  setSessionId(sessionId: string | null): void {
    this.sessionId = sessionId
  }

  private generateSessionId(): string {
    return 'vaiage_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
  }
}

export const vaiageApiService = new VaiageApiService()
