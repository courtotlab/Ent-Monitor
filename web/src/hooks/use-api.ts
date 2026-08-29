import * as React from "react"

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: boolean
  refetch: () => void
}

type State<T> = { data: T | null; loading: boolean; error: boolean }

export function useApi<T>(fn: () => Promise<T>, deps: React.DependencyList = []): UseApiResult<T> {
  const [tick, setTick] = React.useState(0)
  const fnRef = React.useRef(fn)

  React.useEffect(() => {
    fnRef.current = fn
  })

  const [state, setState] = React.useState<State<T>>({ data: null, loading: true, error: false })

  React.useEffect(
    () => {
      let cancelled = false
      // Reset to loading before each fetch, including on refetch()
      setState({ data: null, loading: true, error: false })
      fnRef.current()
        .then((result) => {
          if (!cancelled) setState({ data: result, loading: false, error: false })
        })
        .catch((err) => {
          if (!cancelled) {
            console.error("useApi: fetch failed", err)
            setState({ data: null, loading: false, error: true })
          }
        })
      return () => {
        cancelled = true
      }
    },
    [...deps, tick],
  )

  const refetch = React.useCallback(() => setTick((t) => t + 1), [])

  return { data: state.data, loading: state.loading, error: state.error, refetch }
}

