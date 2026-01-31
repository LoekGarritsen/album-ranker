/**
 * Test setup file for Vitest.
 * Sets up global mocks for browser APIs.
 */
import { vi } from 'vitest'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.CONNECTING
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    this._messageQueue = []

    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen({ target: this })
      }
    }, 0)
  }

  send(data) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open')
    }
    this._messageQueue.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose({ target: this, code: 1000, reason: '' })
    }
  }

  // Test helper: simulate receiving a message
  _receiveMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }

  // Test helper: simulate error
  _triggerError(error) {
    if (this.onerror) {
      this.onerror(error)
    }
  }
}

// Expose MockWebSocket globally
global.WebSocket = MockWebSocket

// Mock window.location
Object.defineProperty(global, 'location', {
  value: {
    protocol: 'http:',
    host: 'localhost:8401',
    href: 'http://localhost:8401/'
  },
  writable: true
})

// Reset module state between tests
beforeEach(() => {
  vi.clearAllMocks()
})
