<template>
  <div class="map-view">
    <div class="welcome-section">
      <h1 class="welcome-title">Your Travel Plan</h1>
      <p class="welcome-desc">Plan Your Perfect Trip</p>
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
          <i class="fas fa-star me-2"></i> Recommended Places
        </div>
        <div class="card-body recommendation-body">
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

            <div class="attraction-display" v-if="currentAttraction">
              <div class="attraction-media">
                <img
                  :src="currentImage"
                  :alt="currentAttraction?.name || 'Attraction image'"
                  class="attraction-image"
                />
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

                <button
                  class="select-button"
                  :class="{ selected: isSelected(currentAttraction?.id) }"
                  @click="toggleSelection(currentAttraction)"
                >
                  <i :class="isSelected(currentAttraction?.id) ? 'fas fa-check-circle' : 'fas fa-plus-circle'"></i>
                  {{ isSelected(currentAttraction?.id) ? 'Selected' : 'Select this Attraction' }}
                </button>
              </div>
            </div>

            <div class="nearby-section" v-if="currentAttraction">
              <h4>Recommendations near {{ currentAttraction?.name }}</h4>
              <div v-if="currentNearby?.status === 'loading'" class="placeholder">
                <p class="text-muted">Loading nearby recommendations...</p>
              </div>
              <div v-else-if="currentNearby?.status === 'error'" class="placeholder error">
                <p>{{ currentNearby?.message || 'Unable to load nearby recommendations.' }}</p>
              </div>
              <div v-else-if="currentNearby?.status === 'success'" class="nearby-list">
                <template v-if="currentNearby?.data?.restaurants && currentNearby.data.restaurants.length">
                  <div
                    v-for="restaurant in currentNearby.data.restaurants"
                    :key="restaurant.place_id || restaurant.name"
                    class="nearby-item"
                  >
                    <img
                      v-if="restaurant.photos && restaurant.photos.length > 0"
                      :src="restaurant.photos[0].url"
                      :alt="restaurant.name"
                    />
                    <div class="nearby-details">
                      <strong>{{ restaurant.name }}</strong>
                      <div class="nearby-meta">
                        <span>{{ restaurant.type || 'Restaurant' }}</span>
                        <span>Rating: {{ restaurant.rating || 'N/A' }}⭐</span>
                        <span>Price: {{ formatPriceLevel(restaurant.price_level) }}</span>
                      </div>
                      <p class="nearby-address">{{ restaurant.address || 'Address not provided' }}</p>
                    </div>
                  </div>
                </template>
                <p v-else class="text-muted">No nearby restaurants found.</p>
              </div>
              <div v-else class="placeholder">
                <p class="text-muted">Nearby information will appear here.</p>
              </div>
            </div>
          </div>
        </div>
        <div class="card-footer confirm-footer" v-if="hasAttractions">
          <button
            class="confirm-button"
            :disabled="!selectedAttractions.length || confirming"
            @click="confirmSelections"
          >
            <span v-if="confirming">Confirming...</span>
            <span v-else>Confirm Selected Attractions</span>
          </button>
        </div>
      </div>
    </div>

    <div class="selected-section">
      <div class="card">
        <div class="card-header">
          <i class="fas fa-check-circle me-2"></i> Selected Attractions
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
import { apiClient } from '../services/apiClient'
import { vaiageApiService } from '../services/vaiageApi'
import type { TravelResponse } from '../services/vaiageApi'
import { useRouter } from 'vue-router'

type Attraction = Record<string, any>

interface NearbyResult {
  restaurants?: Array<Record<string, any>>
}

interface NearbyState {
  status: 'idle' | 'loading' | 'success' | 'error'
  data?: NearbyResult
  message?: string
}

const sessionStore = useSessionStore()
const { attractions, selectedAttractions } = storeToRefs(sessionStore)
const router = useRouter()

const map = ref<any>(null)
const markersLayer = ref<any>(null)
const markers = ref<any[]>([])

const currentIndex = ref(0)
const nearbyMap = ref<Record<string, NearbyState>>({})
const confirming = ref(false)

const hasAttractions = computed(() => Array.isArray(attractions.value) && attractions.value.length > 0)
const currentAttraction = computed<Attraction | null>(() => {
  if (!hasAttractions.value) return null
  return attractions.value[currentIndex.value] || null
})
const currentImage = computed(() => {
  const attraction = currentAttraction.value
  return attraction?.image_url || 'https://via.placeholder.com/300x200.png?text=No+Image'
})
const currentNearby = computed(() => {
  if (!currentAttraction.value || !currentAttraction.value.id) return null
  return nearbyMap.value[currentAttraction.value.id]
})

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

  if (response.state) {
    sessionStore.updateState({
      userInfo: response.state.user_info || {},
      attractions: response.state.attractions || [],
      selectedAttractions: response.state.selected_attractions || [],
      itinerary: response.state.itinerary || null,
      budget: response.state.budget || null,
      confirmation: response.state.confirmation || undefined
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
  if (nextStep && ['strategy', 'route', 'complete'].includes(nextStep)) {
    if (router.currentRoute.value.path !== '/results') {
      await nextTick()
      router.push('/results')
    }
  }
}

async function triggerStrategyStep(selectedIds: string[]) {
  const followUpMessage = 'Here are my selected attractions'
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
    selectedAttractionIds: selectedIds,
    aiRecommendationGenerated: sessionStore.ai_recommendation_generated,
    userInputProcessed: sessionStore.user_input_processed
  })

  await handleCompletionResponse(strategyResponse, strategyAssistantResponse)
}

function isSelected(id?: string | null): boolean {
  if (!id) return false
  return selectedAttractions.value.some(item => item && item.id === id)
}

function toggleSelection(attraction?: Attraction | null) {
  if (!attraction || !attraction.id) return
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

function extractLatLng(attraction: Attraction | null): { lat: number, lng: number } | null {
  if (!attraction) return null
  const location = attraction.location || {}
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

async function ensureNearbyInfo(attraction: Attraction | null) {
  if (!attraction || !attraction.id) return
  const id = attraction.id
  const existing = nearbyMap.value[id]
  if (existing && (existing.status === 'loading' || existing.status === 'success')) {
    return
  }

  const coords = extractLatLng(attraction)
  if (!coords) {
    nearbyMap.value[id] = {
      status: 'error',
      message: 'Missing coordinates. Unable to load nearby recommendations.'
    }
    return
  }

  nearbyMap.value[id] = { status: 'loading' }
  try {
    const sessionId = sessionStore.sessionId || vaiageApiService.getSessionId()
    const params = sessionId ? { session_id: sessionId } : undefined
    const { data } = await apiClient.get<NearbyResult>(
      `/api/nearby/${coords.lat},${coords.lng}`,
      { params }
    )
    nearbyMap.value[id] = { status: 'success', data }
  } catch (error: any) {
    console.error('Failed to load nearby places:', error)
    nearbyMap.value[id] = {
      status: 'error',
      message: error?.message || 'Failed to load nearby recommendations.'
    }
  }
}

async function confirmSelections() {
  if (!selectedAttractions.value.length || confirming.value) return

  const userMessage = 'Here are my selected attractions'
  sessionStore.addUserMessage(userMessage)
  confirming.value = true

  let assistantResponse = ''

  try {
    const selectedIds = selectedAttractions.value
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
      selectedAttractionIds: selectedIds
    })

    await handleCompletionResponse(response, assistantResponse)

    if ((response.next_step === 'strategy' || sessionStore.step === 'strategy') && !sessionStore.ai_recommendation_generated) {
      await triggerStrategyStep(selectedIds)
    }
  } catch (error: any) {
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
  nearbyMap.value = {}

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

  if (Array.isArray(newList) && newList.length > 0) {
    ensureNearbyInfo(newList[0])
  } else {
    nearbyMap.value = {}
  }
}, { deep: true, immediate: true })

watch(currentAttraction, (attraction) => {
  ensureNearbyInfo(attraction)
  nextTick(() => {
    focusOnAttraction(attraction || null)
  })
}, { immediate: true })

onMounted(async () => {
  await initMap()
  if (currentAttraction.value) {
    ensureNearbyInfo(currentAttraction.value)
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
  .attraction-display {
    grid-template-columns: 1fr;
  }

  .recommendation-nav {
    flex-direction: column;
  }

  .confirm-button {
    width: 100%;
  }
}
</style>

