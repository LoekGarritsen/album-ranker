/**
 * Mock for useSpotifyPlayer composable.
 * Returns controllable mock functions for testing.
 */
import { ref } from 'vue'
import { vi } from 'vitest'

// Mock state
export const mockSpotifyState = {
  isReady: ref(false),
  isConnected: ref(false),
  currentTrack: ref(null),
  isPaused: ref(true),
  position: ref(0),
  duration: ref(0),
  volume: ref(50),
  error: ref(null)
}

// Mock functions
export const mockSpotifyFunctions = {
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn().mockResolvedValue(undefined),
  resume: vi.fn().mockResolvedValue(undefined),
  seek: vi.fn().mockResolvedValue(undefined),
  setVolume: vi.fn().mockResolvedValue(undefined),
  checkConnection: vi.fn().mockResolvedValue(false),
  connect: vi.fn(),
  disconnect: vi.fn().mockResolvedValue(undefined),
  initPlayer: vi.fn().mockResolvedValue(undefined),
  setUserId: vi.fn()
}

// Reset all mocks
export function resetSpotifyMocks() {
  mockSpotifyState.isReady.value = false
  mockSpotifyState.isConnected.value = false
  mockSpotifyState.currentTrack.value = null
  mockSpotifyState.isPaused.value = true
  mockSpotifyState.position.value = 0
  mockSpotifyState.duration.value = 0
  mockSpotifyState.volume.value = 50
  mockSpotifyState.error.value = null

  Object.values(mockSpotifyFunctions).forEach(fn => fn.mockClear())
}

// The mock composable function
export function useSpotifyPlayer() {
  return {
    // State
    player: ref(null),
    deviceId: ref(null),
    isReady: mockSpotifyState.isReady,
    isConnected: mockSpotifyState.isConnected,
    currentTrack: mockSpotifyState.currentTrack,
    isPaused: mockSpotifyState.isPaused,
    position: mockSpotifyState.position,
    duration: mockSpotifyState.duration,
    volume: mockSpotifyState.volume,
    error: mockSpotifyState.error,

    // Functions
    play: mockSpotifyFunctions.play,
    pause: mockSpotifyFunctions.pause,
    resume: mockSpotifyFunctions.resume,
    seek: mockSpotifyFunctions.seek,
    setVolume: mockSpotifyFunctions.setVolume,
    checkConnection: mockSpotifyFunctions.checkConnection,
    connect: mockSpotifyFunctions.connect,
    disconnect: mockSpotifyFunctions.disconnect,
    initPlayer: mockSpotifyFunctions.initPlayer,
    setUserId: mockSpotifyFunctions.setUserId
  }
}
