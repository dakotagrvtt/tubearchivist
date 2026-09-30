import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StreamType } from '../../../pages/Home';
import { useAppSettingsStore } from '../../../stores/AppSettingsStore';
import useHlsPreparation from '../useHlsPreparation';

const streams: StreamType[] = [
  { type: 'video', index: 0, codec: 'h264', bitrate: 1000 },
  { type: 'audio', index: 1, codec: 'aac', bitrate: 128, language: 'en' },
  { type: 'audio', index: 2, codec: 'aac', bitrate: 128, language: 'es' },
];
const initialSettings = useAppSettingsStore.getState().appSettingsConfig;
const fetchMock = vi.fn<typeof fetch>();

const pendingResponse = () =>
  new Response(JSON.stringify({ status: 'preparing' }), {
    status: 202,
    headers: { 'Content-Type': 'application/json', 'Retry-After': '5' },
  });
const readyResponse = () =>
  new Response('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nvideo/index.m3u8\n', {
    status: 200,
    headers: { 'Content-Type': 'application/vnd.apple.mpegurl' },
  });

const flushRequests = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

const advancePolling = async (milliseconds = 5000) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
};

describe('useHlsPreparation', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    useAppSettingsStore.setState({ appSettingsConfig: initialSettings });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    useAppSettingsStore.setState({ appSettingsConfig: initialSettings });
  });

  it('keeps 202 responses preparing and polls every five seconds until a playlist is ready', async () => {
    fetchMock
      .mockResolvedValueOnce(pendingResponse())
      .mockResolvedValueOnce(pendingResponse())
      .mockResolvedValueOnce(readyResponse());
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();

    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/video/first-video/hls/master.m3u8',
      { credentials: 'include' },
    );

    await advancePolling(4999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advancePolling(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);

    await advancePolling();
    expect(result.current.url).toBe('/api/video/first-video/hls/master.m3u8');
    expect(result.current.isPreparing).toBe(false);
    expect(result.current.error).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling(30000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('falls back after 24 repolls when preparation remains pending', async () => {
    fetchMock.mockImplementation(async () => pendingResponse());
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();
    await advancePolling(115000);

    expect(fetchMock).toHaveBeenCalledTimes(24);
    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);
    await advancePolling();
    expect(fetchMock).toHaveBeenCalledTimes(25);
    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(false);
    expect(result.current.error).toContain('using the primary audio track');
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling(30000);
    expect(fetchMock).toHaveBeenCalledTimes(25);
  });

  it.each([204, 206, 404, 500, 503])(
    'falls back without exposing a playable URL for HTTP %i',
    async status => {
      fetchMock.mockResolvedValueOnce(new Response(null, { status }));
      const { result } = renderHook(() => useHlsPreparation('first-video', streams));
      await flushRequests();

      expect(result.current.url).toBeNull();
      expect(result.current.isPreparing).toBe(false);
      expect(result.current.error).toContain('using the primary audio track');
      expect(vi.getTimerCount()).toBe(0);
    },
  );

  it('falls back on a network failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Network request failed'));
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();

    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(false);
    expect(result.current.error).toContain('using the primary audio track');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('sends the manual retry flag once and resumes normal polling', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 500 }))
      .mockResolvedValueOnce(pendingResponse())
      .mockResolvedValueOnce(pendingResponse())
      .mockResolvedValueOnce(readyResponse());
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();
    expect(result.current.error).not.toBeNull();

    await act(async () => result.current.retry());
    expect(result.current.error).toBeNull();
    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/video/first-video/hls/master.m3u8?retry=1',
      { credentials: 'include' },
    );

    await advancePolling();
    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);
    await advancePolling();
    expect(result.current.url).toBe('/api/video/first-video/hls/master.m3u8');
    for (const call of fetchMock.mock.calls.slice(2)) {
      expect(call[0]).toBe('http://localhost:8000/api/video/first-video/hls/master.m3u8');
    }
  });

  it('clears a pending timer when the video changes', async () => {
    fetchMock.mockResolvedValueOnce(pendingResponse()).mockResolvedValueOnce(readyResponse());
    const { result, rerender } = renderHook(({ videoId }) => useHlsPreparation(videoId, streams), {
      initialProps: { videoId: 'first-video' },
    });
    await flushRequests();
    rerender({ videoId: 'second-video' });
    await flushRequests();

    expect(result.current.url).toBe('/api/video/second-video/hls/master.m3u8');
    expect(result.current.isPreparing).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each(['ready', 'pending', 'failed'])(
    'ignores a stale %s response after a video change',
    async outcome => {
      const staleRequest = Promise.withResolvers<Response>();
      fetchMock.mockReturnValueOnce(staleRequest.promise).mockResolvedValueOnce(readyResponse());
      const { result, rerender } = renderHook(
        ({ videoId }) => useHlsPreparation(videoId, streams),
        { initialProps: { videoId: 'first-video' } },
      );
      rerender({ videoId: 'second-video' });
      await flushRequests();

      await act(async () => {
        if (outcome === 'failed') {
          staleRequest.reject(new TypeError('Old request failed'));
        } else {
          staleRequest.resolve(outcome === 'ready' ? readyResponse() : pendingResponse());
        }
      });

      expect(result.current.url).toBe('/api/video/second-video/hls/master.m3u8');
      expect(result.current.isPreparing).toBe(false);
      expect(result.current.error).toBeNull();
      expect(vi.getTimerCount()).toBe(0);
    },
  );

  it('clears the pending polling timer on unmount', async () => {
    fetchMock.mockImplementation(async () => pendingResponse());
    const { unmount } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling(30000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not schedule polling if a pending request settles after unmount', async () => {
    const request = Promise.withResolvers<Response>();
    fetchMock.mockReturnValueOnce(request.promise);
    const { unmount } = renderHook(() => useHlsPreparation('first-video', streams));
    unmount();

    await act(async () => request.resolve(pendingResponse()));
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling(30000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('stops polling and clears HLS state when the feature is disabled', async () => {
    fetchMock.mockImplementation(async () => pendingResponse());
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();

    act(() => {
      useAppSettingsStore.setState({
        appSettingsConfig: {
          ...initialSettings,
          application: {
            ...initialSettings.application,
            enable_fork_multi_audio_playback: false,
          },
        },
      });
    });

    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.hasAlternateAudio).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    await advancePolling();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('clears a previously ready URL when re-enabled preparation is pending', async () => {
    fetchMock.mockResolvedValueOnce(readyResponse()).mockResolvedValueOnce(pendingResponse());
    const { result } = renderHook(() => useHlsPreparation('first-video', streams));
    await flushRequests();
    expect(result.current.url).toBe('/api/video/first-video/hls/master.m3u8');

    act(() => {
      useAppSettingsStore.setState({
        appSettingsConfig: {
          ...initialSettings,
          application: {
            ...initialSettings.application,
            enable_fork_multi_audio_playback: false,
          },
        },
      });
    });
    act(() => {
      useAppSettingsStore.setState({ appSettingsConfig: initialSettings });
    });
    await flushRequests();

    expect(result.current.url).toBeNull();
    expect(result.current.isPreparing).toBe(true);
    expect(result.current.error).toBeNull();
  });
});
