import { useEffect } from 'react'
import { useLocation } from 'react-router'
import ROUTE_META from '../config/routeMeta'

const BASE_TITLE = 'TRANC3'

export function usePageTitle(override?: string): void {
  const location = useLocation()

  useEffect(() => {
    const pageTitle = override ?? ROUTE_META[location.pathname]?.title
    document.title = pageTitle ? `${pageTitle} — ${BASE_TITLE}` : BASE_TITLE
  }, [location.pathname, override])
}
