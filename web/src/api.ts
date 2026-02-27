import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export function extractApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail)) {
      const first = detail.find((item) => item?.msg)
      if (first?.msg) {
        return String(first.msg)
      }
    }
    if (error.message) {
      return error.message
    }
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Unbekannter Fehler'
}
