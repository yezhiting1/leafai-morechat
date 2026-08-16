import type { ProductExtension } from '../types'

// Default: no extensions. All behavior stays as-is. An alternate build can
// override the '@product' alias to point at its own module (see
// vite.config.ts) exporting a populated ProductExtension.
export const product: ProductExtension = {}
