import { createApp } from 'vue'
import './style.css'

// Customers open /track/<token>: no login, no sidebar, and none of the staff
// app's code is loaded. Everything else is the normal app.
const entry = window.location.pathname.startsWith('/track/')
  ? import('./views/TrackingPage.vue')
  : import('./App.vue')

entry.then((module) => createApp(module.default).mount('#app'))