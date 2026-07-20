<template>
  <div class="candidate-price">
    <div class="price-line">
      <strong>{{ displayText }}</strong>
      <span v-if="candidate.price_tier" class="price-tier">{{ candidate.price_tier }}</span>
    </div>
    <small v-if="candidate.price_source === 'google_price_range'" class="price-note">
      Google 提供的价格区间，口径以 Google 为准
    </small>
    <small v-else-if="isMockQuote" class="price-note mock-note">
      携程 Mock，非实时价格
    </small>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlaceCandidate } from '../types/session'

const props = defineProps<{
  candidate: PlaceCandidate
}>()

const displayText = computed(() => props.candidate.price_display || '价格待确认')
const isMockQuote = computed(() =>
  props.candidate.hotel_quotes_are_mock === true || props.candidate.price_source === 'ctrip_mock'
)
</script>

<style scoped>
.candidate-price {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  color: #2f5f86;
}

.price-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.price-line strong {
  font-size: 0.9rem;
}

.price-tier {
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.12);
  color: #2474ba;
  font-size: 0.75rem;
  font-weight: 700;
}

.price-note {
  color: #718096;
  line-height: 1.35;
}

.mock-note {
  color: #9a5b1a;
}
</style>
