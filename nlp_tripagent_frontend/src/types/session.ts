export interface ChatMessage {
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface PlacePhoto {
  url: string
  width?: number
  height?: number
  attributions?: string[]
}

export interface HotelStay {
  check_in?: string
  check_out?: string
}

export interface HotelRoomOffer {
  offer_id: string
  hotel_id?: string
  hotel_name?: string
  room_type: string
  bed_type?: string
  breakfast?: string
  nightly_rate: number
  currency?: string
  room_subtotal?: number
  taxes_and_fees?: number
  total_price?: number
  cancellation_policy?: string
  check_in?: string
  check_out?: string
  rooms?: number
  guests?: number
  inventory_status?: string
  source_provider?: string
  is_mock?: boolean
}

export interface PlaceCandidate {
  id: string
  kind: 'attraction' | 'restaurant' | 'hotel'
  name: string
  address?: string
  rating?: number
  price_level?: number
  location?: { lat: number; lng: number }
  match_reasons?: string[]
  recommendation_reasons?: string[]
  recommendation_rank?: number
  ranking_source?: 'llm' | 'rules'
  description?: string
  summary?: string
  category?: string
  estimated_duration?: number
  user_ratings_total?: number
  image_url?: string
  photos?: PlacePhoto[]
  amenities?: string[]
  source?: string
  price_display?: string
  price_source?: 'google_price_range' | 'price_level_estimate' | 'ctrip_mock' | 'unavailable' | string
  price_tier?: string | null
  stay?: HotelStay
  room_offers?: HotelRoomOffer[]
  selected_room_offer?: HotelRoomOffer
  room_type?: string
  nightly_rate?: number
  cancellation_policy?: string
  hotel_quotes_are_mock?: boolean
  room_offer_status?: string
  room_offer_error?: string | null
  [key: string]: unknown
}

export interface CandidateDelta {
  attractions?: PlaceCandidate[]
  restaurants?: PlaceCandidate[]
  hotels?: PlaceCandidate[]
}

export interface InformationRefinement {
  intent?: string
  categories?: Array<'attractions' | 'restaurants' | 'hotels'>
  transient_filters?: Record<string, unknown>
  raw_query?: string
  clarification_message?: string | null
}

export interface CandidateCategorySearchState {
  next_page_token?: string | null
  seen_ids?: string[]
  exhausted?: boolean
  last_query?: string | null
  last_error?: string | null
}

export interface CandidateSearchState {
  attractions?: CandidateCategorySearchState
  restaurants?: CandidateCategorySearchState
  hotels?: CandidateCategorySearchState
}

export interface CandidatePriceContext {
  currency?: string
  stay_dates?: HotelStay
  hotel_quotes_are_mock?: boolean
}

export interface TripDateStatus {
  status?: string
  value?: string | null
  source_text?: string | null
  error?: string | null
}

export interface SessionState {
  sessionId: string | null
  messages: ChatMessage[]
  step: string
  userInfo: Record<string, any>
  attractions: PlaceCandidate[]
  selectedAttractions: PlaceCandidate[]
  restaurants: PlaceCandidate[]
  hotels: PlaceCandidate[]
  selectedRestaurants: PlaceCandidate[]
  selectedHotel: PlaceCandidate | null
  placeErrors: Record<string, string>
  itinerary: any
  budget: any
  hotelRecommendations: any[]
  bookingDrafts: Record<string, any>
  bookingMissingFields: string[]
  bookingMode: string | null
  bookingCandidates: Record<string, any>
  candidateDelta: CandidateDelta
  informationRefinement: InformationRefinement | null
  informationMessage: string | null
  candidateSearchState: CandidateSearchState
  candidatePriceContext: CandidatePriceContext
  currentDate: string | null
  tripDateStatus: TripDateStatus | null
  ai_recommendation_generated: boolean
  user_input_processed: boolean
  confirmation?: string
}
