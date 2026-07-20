import type { PiniaPlugin, StateTree } from 'pinia'

declare module 'pinia-plugin-persistedstate' {
  const piniaPluginPersistedstate: PiniaPlugin
  export default piniaPluginPersistedstate
}

declare module 'pinia' {
  interface DefineStoreOptionsBase<S extends StateTree, Store> {
    persist?: boolean
  }
}
