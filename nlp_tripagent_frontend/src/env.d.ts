/// <reference types="vite/client" />

declare module '*.vue' {
  import { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Google Maps type definitions
export {}
declare global {
  interface Window {
    google: typeof google
  }
}


