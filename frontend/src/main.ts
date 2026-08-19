import { createApp } from 'vue'
import './styles/tokens.css'
import App from './App.vue'
import { router } from './router' // <-- nawiasy klamrowe

createApp(App).use(router).mount('#app')