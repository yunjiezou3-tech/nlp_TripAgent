import { defineStore } from 'pinia'

export interface TripRequest {
  origin: string
  destination: string
  days: number
  preferences?: string
}

export interface WeatherInfo {
  overview?: string
  dailyForecast?: Array<{
    date: string
    condition: string
    temp: string
  }>
  essentials?: string[]
  visa?: string
  recommendations?: string
}

export interface HotelInfo {
  name?: string
  address?: string
  price?: string
  rating?: string
  features?: string[]
  roomType?: string
  facilities?: string
  benefits?: string
  location?: string
}

export interface DailySchedule {
  day?: number
  date?: string
  title?: string
  weekday?: string
  activities?: string[]
  meals?: string[]
  morning?: string[]
  afternoon?: string[]
  evening?: string[]
}

export interface TransportationInfo {
  fromOrigin?: string
  local?: string
  betweenDestinations?: string
  subway?: string
  airport?: string[]
  taxi?: string
}

export interface FoodMap {
  breakfast?: string[]
  lunch?: string[]
  dinner?: string[]
  snacks?: string[]
  koreanBbq?: string
  koreanSetMeal?: string
  streetFood?: string
  dessert?: string
}

export interface Notes {
  packing?: string
  safety?: string
  communication?: string
  other?: string
  taxRefund?: string
  hanbokExperience?: string
}

export interface Budget {
  airfare?: string
  hotel?: string
  food?: string
  tickets?: string
  transportation?: string
  total?: string
}

export interface Itinerary {
  weather?: WeatherInfo
  hotels?: HotelInfo[]
  dailySchedule?: DailySchedule[]
  transportation?: TransportationInfo
  foodMap?: FoodMap
  notes?: Notes
  budget?: Budget
}

export interface TripResult {
  itinerary?: Itinerary
  mapPoints?: Array<{ lat: number; lng: number; label?: string }>
  raw?: unknown
}

export const useTripStore = defineStore('trip', {
  state: () => ({
    request: { origin: '', destination: '', days: 3, preferences: '' } as TripRequest,
    result: null as TripResult | null
  }),
  actions: {
    setRequest(payload: TripRequest) {
      this.request = { ...payload }
    },
    setResult(res: TripResult | null) {
      this.result = res
    }
  }
})


