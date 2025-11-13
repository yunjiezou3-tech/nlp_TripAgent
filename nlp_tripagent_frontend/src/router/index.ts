import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import ItineraryForm from '../views/ItineraryForm.vue'
import ResultsPage from '../views/ResultsPage.vue'
import MapView from '../views/MapView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: ItineraryForm },
  { path: '/results', name: 'results', component: ResultsPage },
  { path: '/map', name: 'map', component: MapView }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router


