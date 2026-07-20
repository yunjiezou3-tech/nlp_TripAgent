import axios from 'axios'

// Vaiage后端API配置
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30000,
  withCredentials: true // 支持会话cookie
})

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const message = error?.response?.data?.detail || error.message || 'Request failed'
    return Promise.reject(new Error(message))
  }
)

// 会话管理
let currentSessionId: string | null = null

export function getSessionId(): string | null {
  return currentSessionId
}

export function setSessionId(sessionId: string): void {
  currentSessionId = sessionId
}

export function clearSessionId(): void {
  currentSessionId = null
}

// 流式响应处理
export interface StreamChunk {
  type: 'chunk' | 'complete' | 'error'
  content?: string
  next_step?: string
  session_id?: string
  missing_fields?: string[]
  attractions?: any[]
  restaurants?: any[]
  hotels?: any[]
  place_errors?: Record<string, string>
  map_data?: any
  itinerary?: any
  budget?: any
  response?: string
  optimal_route?: any
  state?: any
  error?: string
  ai_recommendation_generated?: boolean
  user_input_processed?: boolean
  hotel_recommendations?: any[]
  booking_drafts?: Record<string, any>
  booking_missing_fields?: string[]
  booking_mode?: string | null
  booking_candidates?: Record<string, any>
}

export async function processTravelStep(params: {
  step: string
  user_input: string
  session_id?: string
  selected_attraction_ids?: string[]
  selected_restaurant_ids?: string[]
  selected_hotel_id?: string
  ai_recommendation_generated?: boolean
  user_input_processed?: boolean
}): Promise<StreamChunk[]> {
  const queryParams = new URLSearchParams({
    step: params.step,
    user_input: params.user_input,
    session_id: params.session_id || ''
  })

  if (params.selected_attraction_ids && params.selected_attraction_ids.length > 0) {
    queryParams.append('selected_attraction_ids', JSON.stringify(params.selected_attraction_ids))
  }

  if (params.selected_restaurant_ids) {
    queryParams.append('selected_restaurant_ids', JSON.stringify(params.selected_restaurant_ids))
  }

  if (params.selected_hotel_id) {
    queryParams.append('selected_hotel_id', params.selected_hotel_id)
  }

  if (params.ai_recommendation_generated !== undefined) {
    queryParams.append('ai_recommendation_generated', params.ai_recommendation_generated.toString())
  }

  if (params.user_input_processed !== undefined) {
    queryParams.append('user_input_processed', params.user_input_processed.toString())
  }

  return new Promise((resolve, reject) => {
    const chunks: StreamChunk[] = []
    const eventSource = new EventSource(`${apiBaseUrl}/api/stream?${queryParams.toString()}`)

    eventSource.onmessage = (event) => {
      try {
        const data: StreamChunk = JSON.parse(event.data)
        chunks.push(data)
        
        if (data.type === 'complete' || data.type === 'error') {
          eventSource.close()
          resolve(chunks)
        }
      } catch (error) {
        console.error('Error parsing stream data:', error)
        eventSource.close()
        reject(error)
      }
    }

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error)
      eventSource.close()
      reject(error)
    }

    // 设置超时
    setTimeout(() => {
      if (chunks.length === 0) {
        eventSource.close()
        reject(new Error('Stream timeout'))
      }
    }, 60000) // 60秒超时
  })
}
