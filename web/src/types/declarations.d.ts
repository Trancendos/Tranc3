declare module '@axe-core/react' {
  import type React from 'react'
  import type ReactDOMType from 'react-dom'
  function axe(react: typeof React, reactDOM: typeof ReactDOMType, timeout: number): void
  export default axe
}
