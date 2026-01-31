import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Albums from './views/Albums.vue'
import Results from './views/Results.vue'
import Stats from './views/Stats.vue'
import Comparison from './views/Comparison.vue'
import TierList from './views/TierList.vue'
import YearReview from './views/YearReview.vue'
import Session from './views/Session.vue'
import Rooms from './views/Rooms.vue'

const routes = [
  { path: '/', component: Albums },
  { path: '/results', component: Results },
  { path: '/stats', component: Stats },
  { path: '/compare', component: Comparison },
  { path: '/tiers', component: TierList },
  { path: '/year-review', component: YearReview },
  { path: '/session/:code', component: Session },
  { path: '/rooms', component: Rooms },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

createApp(App).use(router).mount('#app')
