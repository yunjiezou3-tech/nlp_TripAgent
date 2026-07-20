<template>
  <div class="map-view">
    <div class="welcome-section">
      <h1 class="welcome-title">选择你的旅行地点</h1>
      <p class="welcome-desc">景点至少选择一项，餐厅和酒店可按需选择</p>
      <button class="edit-preferences-button" :disabled="confirming" @click="returnToChatForEdits">
        修改旅行偏好
      </button>
    </div>

    <div class="map-section">
      <div class="card">
        <div class="card-header">
          <i class="fas fa-map-marked-alt me-2"></i> Map View
        </div>
        <div class="card-body p-0">
          <div id="map" style="height: 300px;"></div>
        </div>
      </div>
    </div>

    <div class="recommendations-section">
      <div class="card">
        <div class="card-header">
          <i class="fas fa-star me-2"></i> 分组地点推荐
        </div>
        <div class="card-body recommendation-body">
          <section v-if="hasAttractions" class="refinement-panel" aria-labelledby="refinement-title">
            <div class="refinement-copy">
              <h3 id="refinement-title">想换一批或补充条件？</h3>
              <p>可以说“再推荐 3 家亲子酒店”“更多本地餐厅”或“多一些室内景点”。临时条件只影响本次补充推荐。</p>
            </div>
            <form class="refinement-form" @submit.prevent="requestMoreCandidates">
              <input
                v-model="refinementQuery"
                class="refinement-input"
                type="text"
                placeholder="输入你想补充的景点、餐厅或住宿"
                :disabled="refining || confirming"
              />
              <button
                class="refinement-button"
                type="submit"
                :disabled="!refinementQuery.trim() || refining || confirming"
              >
                {{ refining ? '正在补充...' : '补充推荐' }}
              </button>
            </form>
            <p v-if="informationMessage" class="information-message" aria-live="polite">
              {{ informationMessage }}
            </p>
          </section>

          <div v-if="!hasAttractions" class="placeholder">
            <p class="text-muted">
              Recommendations will appear here once they are ready. Keep the conversation going with the assistant to receive curated attractions.
            </p>
          </div>

          <div v-else class="recommendation-content">
            <div class="recommendation-nav">
              <button
                class="nav-button"
                :disabled="currentIndex === 0"
                @click="goPrev"
              >
                ← Previous
              </button>
              <span class="nav-info">
                Attraction {{ currentIndex + 1 }} of {{ attractions.length }}
              </span>
              <button
                class="nav-button"
                :disabled="currentIndex === attractions.length - 1"
                @click="goNext"
              >
                Next →
              </button>
            </div>

            <section v-if="planningStage" class="planning-progress" aria-live="polite">
              <span class="planning-spinner" aria-hidden="true"></span>
              <div>
                <strong>{{ planningLabel }}</strong>
                <p>生成完成后将自动进入行程结果页，请稍候。</p>
              </div>
            </section>

            <div v-if="currentAttraction" ref="attractionGroup" class="attraction-display">
              <div class="attraction-media">
                <img
                  v-if="currentImage && !isImageFailed(currentAttraction.id)"
                  :src="currentImage"
                  :alt="currentAttraction?.name || 'Attraction image'"
                  class="attraction-image"
                  @error="markImageFailed(currentAttraction.id)"
                />
                <div v-else class="candidate-image-fallback attraction-image-fallback">暂无图片</div>
                <small v-if="getPhotoAttribution(currentAttraction)" class="photo-attribution">
                  {{ getPhotoAttribution(currentAttraction) }}
                </small>
                <h3 class="attraction-name">{{ currentAttraction?.name || 'Unknown Attraction' }}</h3>
                <p class="attraction-address">{{ currentAttraction?.address || 'Address not provided' }}</p>
              </div>

              <div class="attraction-info">
                <div class="meta-item">
                  <span class="meta-label">Category</span>
                  <span class="meta-value">{{ currentAttraction?.category || 'N/A' }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Price</span>
                  <span class="meta-value">{{ formatPriceLevel(currentAttraction?.price_level) }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Rating</span>
                  <span class="meta-value">{{ formatRating(currentAttraction) }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Duration</span>
                  <span class="meta-value">{{ formatDuration(currentAttraction?.estimated_duration) }}</span>
                </div>
                <p class="attraction-desc">
                  {{ currentAttraction?.description || 'No description available for this attraction.' }}
                </p>
                <p v-if="getRecommendationReasons(currentAttraction).length" class="recommendation-reasons">
                  <span class="reason-label">{{ getRankingLabel(currentAttraction) }}</span>
                  <span>{{ getRecommendationReasons(currentAttraction).join(' · ') }}</span>
                </p>

                <button
                  class="select-button"
                  :class="{ selected: isSelected(currentAttraction?.id) }"
                  :disabled="confirming"
                  @click="toggleSelection(currentAttraction)"
                >
                  <i :class="isSelected(currentAttraction?.id) ? 'fas fa-check-circle' : 'fas fa-plus-circle'"></i>
                  {{ isSelected(currentAttraction?.id) ? 'Selected' : 'Select this Attraction' }}
                </button>
              </div>
            </div>

            <div class="selection-groups">
              <section ref="restaurantGroup" class="selection-group">
                <div class="selection-heading">
                  <h4>餐厅（可多选）</h4>
                  <span>{{ selectedRestaurants.length }} 已选</span>
                </div>
                <p v-if="placeErrors.restaurants" class="group-error">餐厅暂不可用：{{ placeErrors.restaurants }}</p>
                <p v-else-if="!restaurantCandidates.length" class="text-muted">暂未找到匹配餐厅，规划时会为未覆盖的用餐时段补充建议。</p>
                <div v-else class="candidate-grid">
                  <button
                    v-for="restaurant in restaurantCandidates"
                    :key="restaurant.id"
                    class="candidate-card"
                    :class="{ selected: isRestaurantSelected(restaurant.id) }"
                    :disabled="confirming"
                    @click="toggleRestaurant(restaurant)"
                  >
                    <img
                      v-if="getCandidateImage(restaurant) && !isImageFailed(restaurant.id)"
                      :src="getCandidateImage(restaurant) || undefined"
                      :alt="`${restaurant.name} 图片`"
                      class="candidate-image"
                      @error="markImageFailed(restaurant.id)"
                    />
                    <div v-else class="candidate-image-fallback">暂无图片</div>
                    <small v-if="getPhotoAttribution(restaurant)" class="photo-attribution">
                      {{ getPhotoAttribution(restaurant) }}
                    </small>
                    <strong>{{ restaurant.name }}</strong>
                    <span>评分 {{ restaurant.rating || '暂无' }}</span>
                    <CandidatePrice :candidate="restaurant" />
                    <small>{{ restaurant.address || '地址待补充' }}</small>
                    <small v-if="getRecommendationReasons(restaurant).length" class="recommendation-reasons">
                      <span class="reason-label">{{ getRankingLabel(restaurant) }}</span>
                      <span>{{ getRecommendationReasons(restaurant).join(' · ') }}</span>
                    </small>
                  </button>
                </div>
              </section>

              <section ref="hotelGroup" class="selection-group">
                <div class="selection-heading">
                  <h4>住宿（最多选择一家）</h4>
                  <span>{{ selectedHotel ? '已选 1 家' : '可跳过' }}</span>
                </div>
                <p v-if="placeErrors.hotels" class="group-error">酒店暂不可用：{{ placeErrors.hotels }}</p>
                <p v-else-if="!hotelCandidates.length" class="text-muted">暂未找到满足硬性条件的酒店，你也可以跳过后继续规划。</p>
                <div v-else class="candidate-grid">
                  <button
                    v-for="hotel in hotelCandidates"
                    :key="hotel.id"
                    class="candidate-card hotel-card"
                    :class="{ selected: selectedHotel?.id === hotel.id }"
                    :disabled="confirming"
                    @click="toggleHotel(hotel)"
                  >
                    <img
                      v-if="getCandidateImage(hotel) && !isImageFailed(hotel.id)"
                      :src="getCandidateImage(hotel) || undefined"
                      :alt="`${hotel.name} 图片`"
                      class="candidate-image"
                      @error="markImageFailed(hotel.id)"
                    />
                    <div v-else class="candidate-image-fallback">暂无图片</div>
                    <small v-if="getPhotoAttribution(hotel)" class="photo-attribution">
                      {{ getPhotoAttribution(hotel) }}
                    </small>
                    <strong>{{ hotel.name }}</strong>
                    <span>评分 {{ hotel.rating || '暂无' }}</span>
                    <CandidatePrice :candidate="hotel" />
                    <small v-if="hotel.stay?.check_in && hotel.stay?.check_out">
                      入住 {{ hotel.stay.check_in }} · 离店 {{ hotel.stay.check_out }}
                    </small>
                    <small v-if="getPrimaryRoomOffer(hotel)">
                      {{ getPrimaryRoomOffer(hotel)?.room_type }} · {{ getPrimaryRoomOffer(hotel)?.breakfast || '早餐待确认' }}
                    </small>
                    <small v-if="getPrimaryRoomOffer(hotel)?.cancellation_policy">
                      {{ getPrimaryRoomOffer(hotel)?.cancellation_policy }}
                    </small>
                    <small>{{ hotel.address || '地址待补充' }}</small>
                    <small v-if="getRecommendationReasons(hotel).length" class="recommendation-reasons">
                      <span class="reason-label">{{ getRankingLabel(hotel) }}</span>
                      <span>{{ getRecommendationReasons(hotel).join(' · ') }}</span>
                    </small>
                  </button>
                </div>
              </section>
            </div>
          </div>
        </div>
        <div class="card-footer confirm-footer" v-if="hasAttractions">
          <button
            class="confirm-button"
            :disabled="!selectedAttractions.length || confirming || refining"
            @click="confirmSelections"
          >
            <span v-if="confirming">正在生成完整行程...</span>
            <span v-else>确认地点选择并生成行程</span>
          </button>
        </div>
      </div>
    </div>

    <div class="selected-section">
      <div class="card">
        <div class="card-header">
          <i class="fas fa-check-circle me-2"></i> 已选地点
        </div>
        <div class="card-body selected-body">
          <div v-if="!selectedAttractions.length" class="placeholder">
            <p class="text-muted">No attractions selected yet.</p>
          </div>
          <div v-else class="selected-list">
            <div
              v-for="selected in selectedAttractions"
              :key="selected.id"
              class="selected-item"
            >
              <div class="selected-info">
                <strong>{{ selected.name }}</strong>
                <span>{{ selected.address || 'Address not provided' }}</span>
              </div>
              <button class="remove-button" @click="removeSelection(selected.id)">
                Remove
              </button>
            </div>
          </div>
          <div v-if="selectedRestaurants.length || selectedHotel" class="selected-list additional-selected-list">
            <div v-for="restaurant in selectedRestaurants" :key="restaurant.id" class="selected-item">
              <div class="selected-info"><strong>餐厅 · {{ restaurant.name }}</strong><span>{{ restaurant.address || '地址待补充' }}</span></div>
              <button class="remove-button" @click="toggleRestaurant(restaurant)">移除</button>
            </div>
            <div v-if="selectedHotel" class="selected-item">
              <div class="selected-info"><strong>酒店 · {{ selectedHotel.name }}</strong><span>{{ selectedHotel.address || '地址待补充' }}</span></div>
              <button class="remove-button" @click="sessionStore.setSelectedHotel(null)">移除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '../stores/session'
import CandidatePrice from '../components/CandidatePrice.vue'
import { vaiageApiService } from '../services/vaiageApi'
import type { TravelResponse } from '../services/vaiageApi'
import type { CandidateDelta, HotelRoomOffer, PlaceCandidate } from '../types/session'
import { useRouter } from 'vue-router'

type Attraction = PlaceCandidate

const sessionStore = useSessionStore()
const {
  attractions,
  selectedAttractions,
  restaurants,
  hotels,
  selectedRestaurants,
  selectedHotel,
  placeErrors,
  informationMessage
} = storeToRefs(sessionStore)
const router = useRouter()

const map = ref<any>(null)
const markersLayer = ref<any>(null)
const markers = ref<any[]>([])

const currentIndex = ref(0)
const confirming = ref(false)
const refining = ref(false)
const refinementQuery = ref('')
const failedImageIds = ref<string[]>([])
const attractionGroup = ref<HTMLElement | null>(null)
const restaurantGroup = ref<HTMLElement | null>(null)
const hotelGroup = ref<HTMLElement | null>(null)
const planningStage = ref<'strategy' | 'route' | null>(null)

const hasAttractions = computed(() => Array.isArray(attractions.value) && attractions.value.length > 0)
const restaurantCandidates = computed(() =>
  restaurants.value.filter((candidate) => candidate?.kind === 'restaurant')
)
const hotelCandidates = computed(() =>
  hotels.value.filter((candidate) => candidate?.kind === 'hotel')
)
const planningLabel = computed(() =>
  planningStage.value === 'strategy'
    ? '正在根据已选地点生成每日行程策略...'
    : '正在优化每日路线、计算预算并汇总行程...'
)
const currentAttraction = computed<Attraction | null>(() => {
  if (!hasAttractions.value) return null
  return attractions.value[currentIndex.value] || null
})
const currentImage = computed(() => getCandidateImage(currentAttraction.value))

function syncApiSession() {
  if (sessionStore.sessionId) {
    vaiageApiService.setSessionId(sessionStore.sessionId)
  }
}

async function handleCompletionResponse(response: TravelResponse, assistantAccumulated: string) {
  if (response.response && response.response !== assistantAccumulated) {
    const lastIndex = sessionStore.messages.length - 1
    if (lastIndex >= 0 && sessionStore.messages[lastIndex].type === 'assistant') {
      sessionStore.messages[lastIndex].content = response.response
    } else {
      sessionStore.addAssistantMessage(response.response)
    }
  }

  if (response.missing_fields && response.missing_fields.length > 0) {
    ElMessage.warning(`Missing information: ${response.missing_fields.join(', ')}`)
  }

  if (response.next_step) {
    sessionStore.setStep(response.next_step)
  }

  const refinementIntent = (
    response.information_refinement ?? response.state?.information_refinement
  )?.intent
  const preservesCurrentSelection = ['more_candidates', 'clarify_category'].includes(
    refinementIntent || ''
  )

  if (response.state) {
    sessionStore.updateState({
      userInfo: response.state.user_info || {},
      selectedAttractions: preservesCurrentSelection
        ? sessionStore.selectedAttractions
        : response.state.selected_attractions || sessionStore.selectedAttractions,
      selectedRestaurants: preservesCurrentSelection
        ? sessionStore.selectedRestaurants
        : response.state.selected_restaurants || sessionStore.selectedRestaurants,
      selectedHotel: preservesCurrentSelection
        ? sessionStore.selectedHotel
        : response.state.selected_hotel ?? sessionStore.selectedHotel,
      placeErrors: response.state.place_errors || response.place_errors || {},
      itinerary: response.state.itinerary || null,
      budget: response.state.budget || null,
      confirmation: response.state.confirmation || undefined,
      hotelRecommendations: response.state.hotel_recommendations || response.hotel_recommendations || [],
      bookingDrafts: response.state.booking_drafts || response.booking_drafts || {},
      bookingMissingFields: response.state.booking_missing_fields || response.booking_missing_fields || [],
      bookingMode: response.state.booking_mode || response.booking_mode || null,
      bookingCandidates: response.state.booking_candidates || response.booking_candidates || {},
      informationRefinement: response.information_refinement ?? response.state.information_refinement ?? null,
      informationMessage: response.information_message ?? response.state.information_message ?? null,
      candidateSearchState: response.candidate_search_state || response.state.candidate_search_state || {},
      candidatePriceContext: response.candidate_price_context || response.state.candidate_price_context || {},
      currentDate: response.current_date || response.state.current_date || null,
      tripDateStatus: response.trip_date_status || response.state.trip_date_status || null
    })
  }

  sessionStore.mergeCandidateDelta({
    attractions: response.state?.attractions || response.attractions,
    restaurants: response.state?.restaurants || response.restaurants,
    hotels: response.state?.hotels || response.hotels
  })
  sessionStore.mergeCandidateDelta(
    response.candidate_delta || response.state?.candidate_delta || {}
  )

  if (!response.state) {
    sessionStore.updateState({
      informationRefinement: response.information_refinement ?? null,
      informationMessage: response.information_message ?? null,
      candidateSearchState: response.candidate_search_state || {},
      candidatePriceContext: response.candidate_price_context || {},
      currentDate: response.current_date || null,
      tripDateStatus: response.trip_date_status || null
    })
  }
  if (response.itinerary) {
    sessionStore.itinerary = response.itinerary as any
  }
  if (response.budget) {
    sessionStore.budget = response.budget
  }
  if (response.response) {
    sessionStore.confirmation = response.response
  }
  if (response.hotel_recommendations) {
    sessionStore.hotelRecommendations = response.hotel_recommendations
  }
  if (response.booking_drafts) {
    sessionStore.bookingDrafts = response.booking_drafts
  }
  if (response.booking_missing_fields) {
    sessionStore.bookingMissingFields = response.booking_missing_fields
  }
  if (response.booking_mode !== undefined) {
    sessionStore.bookingMode = response.booking_mode
  }
  if (response.booking_candidates) {
    sessionStore.bookingCandidates = response.booking_candidates
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
    sessionStore.sessionId = response.session_id
    vaiageApiService.setSessionId(response.session_id)
  }

  const nextStep = response.next_step || sessionStore.step
  if (nextStep === 'complete') {
    planningStage.value = null
    if (router.currentRoute.value.path !== '/results') {
      await nextTick()
      router.push('/results')
    }
  }
}

async function requestMoreCandidates() {
  const query = refinementQuery.value.trim()
  if (!query || refining.value || confirming.value) return

  const previousCounts = {
    attractions: attractions.value.length,
    restaurants: restaurants.value.length,
    hotels: hotels.value.length
  }
  sessionStore.addUserMessage(query)
  syncApiSession()
  refining.value = true
  sessionStore.informationMessage = null
  let assistantResponse = ''

  try {
    const response = await vaiageApiService.streamChatMessage(query, (chunk) => {
      assistantResponse += chunk
      const lastIndex = sessionStore.messages.length - 1
      if (lastIndex >= 0 && sessionStore.messages[lastIndex].type === 'assistant') {
        sessionStore.messages[lastIndex].content = assistantResponse
      } else {
        sessionStore.addAssistantMessage(assistantResponse)
      }
    }, {
      step: 'recommend',
      selectedAttractionIds: selectedAttractions.value.map((item) => item.id),
      selectedRestaurantIds: selectedRestaurants.value.map((item) => item.id),
      selectedHotelId: selectedHotel.value?.id
    })

    await handleCompletionResponse(response, assistantResponse)
    const delta = response.candidate_delta || response.state?.candidate_delta || {}
    if (!assistantResponse && !response.response && response.information_message) {
      sessionStore.addAssistantMessage(response.information_message)
    }
    refinementQuery.value = ''
    await scrollToCandidateDelta(delta, previousCounts)
  } catch (error) {
    console.error('Failed to refine candidates:', error)
    sessionStore.informationMessage = '补充推荐暂时失败，请稍后重试。已有候选和选择不会丢失。'
    ElMessage.error(sessionStore.informationMessage)
  } finally {
    refining.value = false
  }
}

async function scrollToCandidateDelta(
  delta: CandidateDelta,
  previousCounts: Record<'attractions' | 'restaurants' | 'hotels', number>
) {
  const firstChangedCategory = (['attractions', 'restaurants', 'hotels'] as const)
    .find((category) => Array.isArray(delta[category]) && delta[category]!.length > 0)
  if (!firstChangedCategory) return

  if (firstChangedCategory === 'attractions') {
    currentIndex.value = Math.min(previousCounts.attractions, attractions.value.length - 1)
  }

  await nextTick()
  const target = {
    attractions: attractionGroup.value,
    restaurants: restaurantGroup.value,
    hotels: hotelGroup.value
  }[firstChangedCategory]
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function getCandidateImage(candidate?: PlaceCandidate | null): string | null {
  if (!candidate) return null
  if (typeof candidate.image_url === 'string' && candidate.image_url.trim()) {
    return candidate.image_url
  }
  const photo = Array.isArray(candidate.photos)
    ? candidate.photos.find((item) => typeof item?.url === 'string' && item.url.trim())
    : undefined
  return photo?.url || null
}

function getPhotoAttribution(candidate?: PlaceCandidate | null): string {
  if (!candidate || !Array.isArray(candidate.photos)) return ''
  const photo = candidate.photos.find((item) => Array.isArray(item?.attributions) && item.attributions.length)
  return photo?.attributions
    ?.map((attribution) => attribution.replace(/<[^>]*>/g, '').trim())
    .filter(Boolean)
    .join(' · ') || ''
}

function markImageFailed(candidateId?: string) {
  if (candidateId && !failedImageIds.value.includes(candidateId)) {
    failedImageIds.value = [...failedImageIds.value, candidateId]
  }
}

function isImageFailed(candidateId?: string): boolean {
  return !!candidateId && failedImageIds.value.includes(candidateId)
}

function getPrimaryRoomOffer(candidate?: PlaceCandidate | null): HotelRoomOffer | null {
  if (!candidate) return null
  return candidate.selected_room_offer || candidate.room_offers?.[0] || null
}

async function triggerStrategyStep() {
  syncApiSession()
  planningStage.value = 'strategy'
  const followUpMessage = '确认地点选择，开始生成行程'
  let strategyAssistantResponse = ''

  const strategyResponse = await vaiageApiService.streamChatMessage(followUpMessage, (chunk) => {
    strategyAssistantResponse += chunk
    const lastIndex = sessionStore.messages.length - 1
    if (lastIndex >= 0 && sessionStore.messages[lastIndex].type === 'assistant') {
      sessionStore.messages[lastIndex].content = strategyAssistantResponse
    } else {
      sessionStore.addAssistantMessage(strategyAssistantResponse)
    }
  }, {
    step: 'strategy',
    aiRecommendationGenerated: sessionStore.ai_recommendation_generated,
    userInputProcessed: sessionStore.user_input_processed
  })

  await handleCompletionResponse(strategyResponse, strategyAssistantResponse)

  if ((strategyResponse.next_step || sessionStore.step) === 'route') {
    await triggerRouteStep()
  }
}

async function triggerRouteStep() {
  syncApiSession()
  planningStage.value = 'route'
  let routeAssistantResponse = ''

  const routeResponse = await vaiageApiService.streamChatMessage('', (chunk) => {
    routeAssistantResponse += chunk
    const lastIndex = sessionStore.messages.length - 1
    if (lastIndex >= 0 && sessionStore.messages[lastIndex].type === 'assistant') {
      sessionStore.messages[lastIndex].content = routeAssistantResponse
    } else {
      sessionStore.addAssistantMessage(routeAssistantResponse)
    }
  }, {
    step: 'route',
    aiRecommendationGenerated: sessionStore.ai_recommendation_generated,
    userInputProcessed: sessionStore.user_input_processed
  })

  await handleCompletionResponse(routeResponse, routeAssistantResponse)
  if ((routeResponse.next_step || sessionStore.step) !== 'complete') {
    planningStage.value = null
  }
}

function isSelected(id?: string | null): boolean {
  if (!id) return false
  return selectedAttractions.value.some(item => item && item.id === id)
}

function toggleSelection(attraction?: Attraction | null) {
  if (!attraction || !attraction.id || confirming.value) return
  if (isSelected(attraction.id)) {
    sessionStore.removeSelectedAttraction(attraction.id)
  } else {
    sessionStore.addSelectedAttraction(attraction)
  }
}

function removeSelection(id?: string) {
  if (!id) return
  sessionStore.removeSelectedAttraction(id)
}

function isRestaurantSelected(id?: string | null): boolean {
  return !!id && sessionStore.isRestaurantSelected(id)
}

function toggleRestaurant(restaurant?: Attraction | null) {
  if (restaurant && !confirming.value) sessionStore.toggleSelectedRestaurant(restaurant)
}

function toggleHotel(hotel?: Attraction | null) {
  if (!hotel || confirming.value) return
  sessionStore.setSelectedHotel(selectedHotel.value?.id === hotel.id ? null : hotel)
}

function returnToChatForEdits() {
  if (confirming.value) return

  sessionStore.updateState({
    attractions: [],
    restaurants: [],
    hotels: [],
    selectedAttractions: [],
    selectedRestaurants: [],
    selectedHotel: null,
    placeErrors: {},
    hotelRecommendations: []
  })
  sessionStore.setStep('chat')
  sessionStore.addAssistantMessage('已返回聊天修改旅行偏好。你可以直接说“目的地改为东京”或“出发地是上海”。')
  router.push('/')
}

function goPrev() {
  if (currentIndex.value > 0) {
    currentIndex.value -= 1
  }
}

function goNext() {
  if (!hasAttractions.value) return
  if (currentIndex.value < attractions.value.length - 1) {
    currentIndex.value += 1
  }
}

function formatPriceLevel(level?: number | null): string {
  if (!level || level <= 0) return 'N/A'
  return '💰'.repeat(Math.min(level, 5))
}

function formatRating(attraction?: Attraction | null): string {
  if (!attraction || !attraction.rating) return 'No rating'
  const reviews = attraction.user_ratings_total ?? 'N/A'
  return `⭐ ${attraction.rating} (${reviews} reviews)`
}

function formatDuration(duration?: number | null): string {
  if (!duration) return 'Duration not specified'
  return `${duration} hours (est.)`
}

function getRecommendationReasons(candidate?: Attraction | null): string[] {
  if (!candidate) return []
  if (Array.isArray(candidate.recommendation_reasons) && candidate.recommendation_reasons.length) {
    return candidate.recommendation_reasons
  }
  return Array.isArray(candidate.match_reasons) ? candidate.match_reasons : []
}

function getRankingLabel(candidate?: Attraction | null): string {
  return candidate?.ranking_source === 'llm' ? 'AI 偏好排序' : '偏好与评分排序'
}

function extractLatLng(attraction: Attraction | null): { lat: number, lng: number } | null {
  if (!attraction) return null
  const location: Partial<{ lat: number; lng: number }> = attraction.location || {}
  const lat = attraction.latitude ?? attraction.lat ?? location.lat
  const lng = attraction.longitude ?? attraction.lng ?? location.lng
  if (typeof lat === 'number' && typeof lng === 'number') {
    return { lat, lng }
  }
  return null
}

function focusOnAttraction(attraction: Attraction | null) {
  if (!attraction || !map.value) return

  const coords = extractLatLng(attraction)
  if (!coords) return

  try {
    const targetMarker = markers.value.find((marker: any) => marker && marker.attractionId === attraction.id)
    if (targetMarker) {
      map.value.setView(targetMarker.getLatLng(), 14, { animate: true })
      targetMarker.openPopup()
    } else {
      map.value.setView([coords.lat, coords.lng], 14, { animate: true })
    }
  } catch (error) {
    console.error('Failed to focus map on attraction:', error)
  }
}

async function confirmSelections() {
  if (!selectedAttractions.value.length || confirming.value) return

  const userMessage = '确认我的地点选择'
  syncApiSession()
  sessionStore.addUserMessage(userMessage)
  confirming.value = true
  planningStage.value = 'strategy'

  let assistantResponse = ''

  try {
    const selectedIds = selectedAttractions.value
      .map((item: any) => item?.id)
      .filter((id: string | null | undefined): id is string => !!id)
    const selectedRestaurantIds = selectedRestaurants.value
      .map((item: any) => item?.id)
      .filter((id: string | null | undefined): id is string => !!id)

    const response = await vaiageApiService.streamChatMessage(userMessage, (chunk) => {
      assistantResponse += chunk
      const lastIndex = sessionStore.messages.length - 1
      if (lastIndex >= 0 && sessionStore.messages[lastIndex].type === 'assistant') {
        sessionStore.messages[lastIndex].content = assistantResponse
      } else {
        sessionStore.addAssistantMessage(assistantResponse)
      }
    }, {
      step: 'recommend',
      selectedAttractionIds: selectedIds,
      selectedRestaurantIds,
      selectedHotelId: selectedHotel.value?.id
    })

    await handleCompletionResponse(response, assistantResponse)

    if ((response.next_step === 'strategy' || sessionStore.step === 'strategy') && !sessionStore.ai_recommendation_generated) {
      await triggerStrategyStep()
    } else if ((response.next_step || sessionStore.step) === 'route') {
      await triggerRouteStep()
    }
  } catch (error: any) {
    planningStage.value = null
    console.error('Failed to confirm selections:', error)
    ElMessage.error(error?.message || 'Failed to confirm selections. Please try again.')
    sessionStore.addAssistantMessage('Sorry, something went wrong while confirming your selections. Please try again.')
  } finally {
    confirming.value = false
  }
}

async function loadLeafletResources() {
  return new Promise<void>((resolve, reject) => {
    if ((window as any).L) {
      resolve()
      return
    }

    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
    link.onload = () => {
      const script = document.createElement('script')
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load Leaflet JavaScript'))
      document.head.appendChild(script)
    }
    link.onerror = () => reject(new Error('Failed to load Leaflet CSS'))
    document.head.appendChild(link)
  })
}

async function initMap() {
  try {
    await loadLeafletResources()
    const L = (window as any).L
    map.value = L.map('map').setView([20, 0], 2)
    
    const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    })
    
    tileLayer.on('tileerror', () => {
      /* silent */
    })
    
    tileLayer.addTo(map.value)
    markersLayer.value = L.layerGroup().addTo(map.value)

    if (hasAttractions.value) {
      updateMapWithPoints()
    }
  } catch (error) {
    console.error('Leaflet map loading failed:', error)
    setTimeout(() => {
      if (map.value) {
        map.value.setView([48.8566, 2.3522], 13)
      }
    }, 1000)
  }
}

function updateMapWithPoints() {
  if (!map.value || !markersLayer.value) return

    markersLayer.value.clearLayers()
  markers.value = []

  if (!hasAttractions.value) {
    map.value.setView([20, 0], 2)
    return
  }

  const L = (window as any).L
  const bounds = L.latLngBounds()

  attractions.value.forEach((attraction, index) => {
    const coords = extractLatLng(attraction)
    if (!coords) return

    const position = [coords.lat, coords.lng]
      bounds.extend(position)

      const marker = L.marker(position)
        .addTo(markersLayer.value)
        .bindPopup(`<strong>${attraction.name || `Attraction ${index + 1}`}</strong><br>${attraction.description || ''}`)

    ;(marker as any).attractionId = attraction.id

      markers.value.push(marker)
  })

  if (markers.value.length > 0) {
    try {
      const group = new L.featureGroup(markers.value)
      map.value.fitBounds(group.getBounds().pad(0.1))
    } catch (error) {
      console.error('Error fitting map bounds:', error)
      map.value.setView([48.8566, 2.3522], 13)
    }
  } else {
    map.value.setView([20, 0], 2)
  }
}

watch(attractions, (newList) => {
  currentIndex.value = 0

  if (map.value) {
    nextTick(() => {
      updateMapWithPoints()
      if (Array.isArray(newList) && newList.length > 0) {
        focusOnAttraction(newList[0])
      }
    })
  } else {
    updateMapWithPoints()
    if (Array.isArray(newList) && newList.length > 0) {
      focusOnAttraction(newList[0])
    }
  }

}, { deep: true, immediate: true })

watch(currentAttraction, (attraction) => {
  nextTick(() => {
    focusOnAttraction(attraction || null)
  })
}, { immediate: true })

onMounted(async () => {
  syncApiSession()
  await initMap()
  if (currentAttraction.value) {
    focusOnAttraction(currentAttraction.value)
  }
})
</script>

<style scoped>
.map-view {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.welcome-section {
  text-align: center;
  margin-bottom: 40px;
  padding: 40px 20px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(25px);
  -webkit-backdrop-filter: blur(25px);
  border-radius: 30px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.welcome-title {
  font-size: 2.5rem;
  font-weight: 700;
  color: white;
  margin-bottom: 12px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.welcome-desc {
  font-size: 1.2rem;
  color: rgba(255, 255, 255, 0.9);
  margin: 0;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.edit-preferences-button {
  margin-top: 10px;
  padding: 8px 14px;
  border: 1px solid #409eff;
  border-radius: 999px;
  background: #fff;
  color: #2474ba;
  cursor: pointer;
  font-weight: 600;
}

.edit-preferences-button:disabled {
  cursor: wait;
  opacity: 0.65;
}

@media (max-width: 768px) {
  .welcome-section {
    padding: 30px 15px;
    margin-bottom: 30px;
  }
  
  .welcome-title {
    font-size: 2rem;
  }
  
  .welcome-desc {
    font-size: 1rem;
  }
}

.card {
  border-radius: 18px;
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.12);
  border: none;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
}

.card-header {
  background: linear-gradient(135deg, #409EFF 0%, #67C23A 100%);
  color: white;
  border-radius: 18px 18px 0 0 !important;
  font-weight: 700;
  font-size: 1.3rem;
  padding: 18px 24px;
  display: flex;
  align-items: center;
}

.card-body {
  padding: 24px;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 0 0 18px 18px;
  color: #2c3e50;
}

#map {
  border-radius: 0 0 18px 18px;
}

::deep(.leaflet-container) {
  border-radius: 0 0 15px 15px;
}

::deep(.leaflet-popup-content-wrapper) {
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

::deep(.leaflet-popup-content) {
  margin: 12px 16px;
  font-family: inherit;
}

.recommendation-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 12px;
  padding: 16px;
}

.refinement-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
  gap: 14px 20px;
  align-items: center;
  padding: 16px;
  border: 1px solid rgba(64, 158, 255, 0.2);
  border-radius: 14px;
  background: linear-gradient(120deg, rgba(64, 158, 255, 0.08), rgba(103, 194, 58, 0.08));
}

.refinement-copy h3,
.refinement-copy p {
  margin: 0;
}

.refinement-copy h3 {
  color: #2c3e50;
  font-size: 1.05rem;
}

.refinement-copy p {
  margin-top: 5px;
  color: #606266;
  font-size: 0.88rem;
  line-height: 1.45;
}

.refinement-form {
  display: flex;
  gap: 8px;
}

.refinement-input {
  min-width: 0;
  flex: 1;
  padding: 10px 12px;
  border: 1px solid rgba(64, 158, 255, 0.35);
  border-radius: 9px;
  color: #303133;
  background: rgba(255, 255, 255, 0.92);
}

.refinement-input:focus {
  border-color: #409eff;
  outline: 2px solid rgba(64, 158, 255, 0.12);
}

.refinement-button {
  flex: 0 0 auto;
  padding: 10px 14px;
  border: none;
  border-radius: 9px;
  background: #2474ba;
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}

.refinement-button:disabled,
.refinement-input:disabled {
  cursor: wait;
  opacity: 0.62;
}

.information-message {
  grid-column: 1 / -1;
  margin: 0;
  padding: 9px 11px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.78);
  color: #2f5f86;
  font-size: 0.9rem;
}

.placeholder {
  text-align: center;
  padding: 20px;
  border: 1px dashed rgba(0, 0, 0, 0.1);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.6);
}

.placeholder.error {
  border-color: rgba(255, 87, 34, 0.3);
  color: #e53935;
}

.recommendation-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: #2c3e50;
  margin-bottom: 16px;
}

.nav-button {
  border: 1px solid #409EFF;
  background: white;
  color: #409EFF;
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.2s ease;
}

.nav-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.nav-button:not(:disabled):hover {
  background: #409EFF;
  color: white;
}

.nav-info {
  font-weight: 600;
  color: #303133;
}

.attraction-display {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
  align-items: start;
  color: #2c3e50;
}

.attraction-media {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.attraction-image {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.candidate-image,
.candidate-image-fallback {
  width: 100%;
  height: 128px;
  border-radius: 9px;
}

.candidate-image {
  object-fit: cover;
}

.candidate-image-fallback {
  display: grid;
  place-items: center;
  background:
    linear-gradient(135deg, rgba(64, 158, 255, 0.14), rgba(103, 194, 58, 0.14)),
    repeating-linear-gradient(45deg, transparent 0 12px, rgba(255, 255, 255, 0.45) 12px 24px);
  color: #718096;
  font-size: 0.86rem;
  font-weight: 600;
}

.attraction-image-fallback {
  height: 220px;
}

.photo-attribution {
  width: 100%;
  color: #8492a6;
  font-size: 0.7rem;
  line-height: 1.3;
}

.attraction-name {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #2c3e50;
}

.attraction-address {
  margin: 0;
  color: #909399;
  font-size: 0.95rem;
}

.attraction-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.meta-item {
  display: flex;
  justify-content: space-between;
  background: rgba(64, 158, 255, 0.06);
  padding: 10px 14px;
  border-radius: 10px;
}

.meta-label {
  font-weight: 600;
  color: #409EFF;
}

.meta-value {
  font-weight: 500;
  color: #303133;
}

.attraction-desc {
  margin: 8px 0 0;
  font-style: italic;
  color: #606266;
  min-height: 60px;
}

.planning-progress {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 4px 0 18px;
  padding: 14px 16px;
  border: 1px solid rgba(64, 158, 255, 0.28);
  border-radius: 12px;
  background: linear-gradient(120deg, rgba(64, 158, 255, 0.1), rgba(103, 194, 58, 0.1));
  color: #2c3e50;
}

.planning-progress p {
  margin: 4px 0 0;
  color: #606266;
  font-size: 0.9rem;
}

.planning-spinner {
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  border: 3px solid rgba(64, 158, 255, 0.25);
  border-top-color: #409eff;
  border-radius: 50%;
  animation: planning-spin 0.8s linear infinite;
}

@keyframes planning-spin {
  to { transform: rotate(360deg); }
}

.recommendation-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin: 0;
  padding: 8px 10px;
  border-radius: 9px;
  background: rgba(103, 194, 58, 0.1);
  color: #3a6d22;
  font-size: 0.88rem;
  line-height: 1.45;
}

.reason-label {
  color: #2f7d32;
  font-weight: 700;
}

.select-button {
  align-self: flex-start;
  border: 1px solid #409EFF;
  background: white;
  color: #409EFF;
  padding: 10px 18px;
  border-radius: 8px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.select-button.selected {
  background: #67C23A;
  border-color: #67C23A;
  color: white;
}

.select-button:not(.selected):hover {
  background: #409EFF;
  color: white;
}

.nearby-section {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.nearby-section h4 {
  margin: 0;
  font-size: 1.2rem;
  color: #2c3e50;
}

.nearby-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #2c3e50;
}

.nearby-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.nearby-item img {
  width: 90px;
  height: 70px;
  object-fit: cover;
  border-radius: 8px;
}

.nearby-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nearby-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.85rem;
  color: #606266;
}

.nearby-address {
  margin: 0;
  font-size: 0.9rem;
  color: #909399;
}

.selection-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 20px;
}

.selection-group {
  padding: 16px;
  border: 1px solid rgba(64, 158, 255, 0.16);
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(64, 158, 255, 0.05), rgba(103, 194, 58, 0.06));
}

.selection-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 12px;
}

.selection-heading h4 {
  margin: 0;
  color: #303133;
}

.selection-heading span {
  color: #409EFF;
  font-size: 0.85rem;
}

.candidate-grid {
  display: grid;
  gap: 10px;
}

.candidate-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  width: 100%;
  border: 1px solid rgba(64, 158, 255, 0.2);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.84);
  color: #303133;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.candidate-card:hover {
  border-color: #409EFF;
  transform: translateY(-1px);
}

.candidate-card.selected {
  border-color: #67C23A;
  background: rgba(103, 194, 58, 0.12);
  box-shadow: 0 6px 18px rgba(103, 194, 58, 0.16);
}

.candidate-card:disabled,
.select-button:disabled {
  cursor: wait;
  opacity: 0.68;
  transform: none;
}

.candidate-card small {
  color: #606266;
}

.candidate-card .recommendation-reasons {
  width: 100%;
  color: #3a6d22;
}

.group-error {
  margin: 0;
  color: #e53935;
  font-size: 0.9rem;
}

.additional-selected-list {
  margin-top: 12px;
}

.confirm-footer {
  display: flex;
  justify-content: center;
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 0 0 18px 18px;
}

.confirm-button {
  width: 60%;
  max-width: 320px;
  padding: 12px;
  border-radius: 10px;
  border: none;
  font-size: 1rem;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, #409EFF 0%, #67C23A 100%);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.confirm-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  box-shadow: none;
}

.confirm-button:not(:disabled):hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(64, 158, 255, 0.4);
}

.selected-body {
  min-height: 160px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 12px;
}

.selected-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.selected-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.08);
}

.selected-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.selected-info strong {
  font-size: 1rem;
  color: #303133;
}

.selected-info span {
  font-size: 0.9rem;
  color: #909399;
}

.remove-button {
  border: none;
  background: transparent;
  color: #F56C6C;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.2s ease;
}

.remove-button:hover {
  color: #d9534f;
}

@media (max-width: 992px) {
  .refinement-panel {
    grid-template-columns: 1fr;
  }

  .information-message {
    grid-column: auto;
  }

  .attraction-display {
    grid-template-columns: 1fr;
  }

  .selection-groups {
    grid-template-columns: 1fr;
  }

  .recommendation-nav {
    flex-direction: column;
  }

  .confirm-button {
    width: 100%;
  }
}

@media (max-width: 560px) {
  .refinement-form {
    flex-direction: column;
  }
}
</style>
