import { apiClient, processTravelStep, setSessionId, getSessionId, clearSessionId, type StreamChunk } from './apiClient'
import type { TripRequest, TripResult } from '../stores/trip'
import type { TravelResponse } from './vaiageApi'
import { generateMockTripResult } from '../utils/mockData'

// Whether to use mock data (default true, unless explicitly set to 'false')
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA !== 'false'

// Whether to use Vaiage backend (default true, unless explicitly set to 'false')
const USE_VAIAGE_BACKEND = import.meta.env.VITE_USE_VAIAGE_BACKEND !== 'false'

// 旅行规划状态管理
interface TravelState {
  step: string
  userInfo: Record<string, any>
  attractions: any[]
  selectedAttractions: any[]
  itinerary: any
  budget: any
  ai_recommendation_generated: boolean
  user_input_processed: boolean
}

let currentState: TravelState = {
  step: 'chat',
  userInfo: {},
  attractions: [],
  selectedAttractions: [],
  itinerary: null,
  budget: null,
  ai_recommendation_generated: false,
  user_input_processed: false
}

export async function planTrip(payload: TripRequest): Promise<TripResult> {
  if (USE_MOCK_DATA && !USE_VAIAGE_BACKEND) {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 1000))
    return generateMockTripResult(payload)
  }
  
  try {
    if (USE_VAIAGE_BACKEND) {
      // 使用Vaiage后端的流式API
      const userInput = `I want to travel from ${payload.origin} to ${payload.destination} for ${payload.days} days. My preferences: ${payload.preferences || 'general travel'}`
      
      const chunks = await processTravelStep({
        step: currentState.step,
        user_input: userInput,
        session_id: getSessionId() || undefined,
        ai_recommendation_generated: currentState.ai_recommendation_generated,
        user_input_processed: currentState.user_input_processed
      })
      
      return processStreamChunks(chunks, payload)
    } else {
      // Use original backend API
      const { data } = await apiClient.post('/api/trip/plan', payload)
      return data as TripResult
    }
  } catch (error) {
    // If backend request fails, fallback to mock data
    console.warn('Backend request failed, using mock data:', error)
    return generateMockTripResult(payload)
  }
}

// 处理流式响应数据
function processStreamChunks(chunks: StreamChunk[], request: TripRequest): TripResult {
  let fullResponse = ''
  let result: TripResult = {
    itinerary: { dailySchedule: [] },
    mapPoints: [],
    recommendations: [],
    budget: null,
    optimalRoute: null,
    response: ''
  }
  
  for (const chunk of chunks) {
    if (chunk.type === 'chunk' && chunk.content) {
      fullResponse += chunk.content
    } else if (chunk.type === 'complete') {
      // 更新会话ID
      if (chunk.session_id) {
        setSessionId(chunk.session_id)
      }
      
      // 更新状态
      if (chunk.next_step) {
        currentState.step = chunk.next_step
      }
      
      if (chunk.state) {
        currentState = { ...currentState, ...chunk.state }
      }
      
      // 构建结果
      result.response = fullResponse
      
      if (chunk.attractions) {
        result.recommendations = chunk.attractions.map((attraction: any) => ({
          name: attraction.name || 'Unknown',
          type: attraction.category || 'attraction',
          rating: attraction.rating || 4.0,
          description: attraction.description || 'Popular tourist attraction'
        }))
      }
      
      if (chunk.map_data) {
        result.mapPoints = chunk.map_data.markers || []
      }
      
      if (chunk.itinerary) {
        result.itinerary = chunk.itinerary
      }
      
      if (chunk.budget) {
        result.budget = chunk.budget
      }
      
      if (chunk.optimal_route) {
        result.optimalRoute = chunk.optimal_route
      }
      
      break
    }
  }
  
  return result
}

function convertVaiageResponseToTripResult(response: TravelResponse, request: TripRequest): TripResult {
  // Extract itinerary from response
  const itinerary = response.itinerary || {
    dailySchedule: Array.from({ length: request.days }, (_, i) => ({
      day: i + 1,
      activities: [
        {
          time: '09:00',
          title: 'Visit local attractions',
          description: 'Explore the city\'s famous landmarks',
          location: request.destination
        }
      ]
    }))
  }

  // Extract map data from response
  const mapData = response.map_data || {
    center: { lat: 35.6762, lng: 139.6503 },
    markers: []
  }

  // Extract recommendations from response
  const recommendations = response.attractions ? response.attractions.map(attraction => ({
    name: attraction.name || 'Unknown',
    type: attraction.category || 'attraction',
    rating: attraction.rating || 4.0,
    description: attraction.description || 'Popular tourist attraction'
  })) : []

  return {
    itinerary,
    mapPoints: mapData.markers || [],
    recommendations,
    budget: response.budget,
    optimalRoute: response.optimal_route,
    response: response.response
  }
}

export async function fetchWeather(destination: string) {
  const { data } = await apiClient.get('/api/weather', { params: { destination } })
  return data
}

export async function searchScenicSpots(keyword: string) {
  const { data } = await apiClient.get('/api/scenic-spots', { params: { q: keyword } })
  return data
}

export async function recommendHotels(destination: string) {
  const { data } = await apiClient.get('/api/hotels/recommend', { params: { destination } })
  return data
}

