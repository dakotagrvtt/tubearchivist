import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { VideoType } from '../../pages/Home';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';
import EnhancedVideoPlayer from './EnhancedVideoPlayer';

// The controls do not participate in source selection or preparation.
vi.mock('@vidstack/react/player/layouts/default', () => ({
  DefaultVideoLayout: () => null,
  defaultLayoutIcons: {},
}));

const video: VideoType = {
  active: true,
  category: [],
  channel: {
    channel_active: true,
    channel_banner_url: '',
    channel_description: '',
    channel_id: 'channel',
    channel_last_refresh: '',
    channel_name: 'Channel',
    channel_subs: 0,
    channel_subscribed: false,
    channel_thumb_url: '',
    channel_tvart_url: '',
  },
  date_downloaded: 0,
  description: '',
  media_size: 0,
  media_url: '/media/channel/video.mkv',
  player: { watched: false, duration: 60, duration_str: '1:00', progress: 0, position: 0 },
  published: '',
  playlist: [],
  stats: { view_count: 0, like_count: 0, dislike_count: 0, average_rating: 0 },
  streams: [{ type: 'audio', index: 1, codec: 'aac', bitrate: 128000 }],
  subtitles: [],
  tags: [],
  title: 'Uncached MKV',
  vid_last_refresh: '',
  vid_thumb_url: '',
  vid_type: 'videos',
  youtube_id: 'video',
};

const renderPlayer = (item = video) =>
  render(
    <MemoryRouter>
      <EnhancedVideoPlayer video={item} embed />
    </MemoryRouter>,
  );

const initialSettings = useAppSettingsStore.getState().appSettingsConfig;

beforeEach(() => {
  useAppSettingsStore.setState({ appSettingsConfig: initialSettings });
  localStorage.clear();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(private callback: (entries: { isIntersecting: boolean }[]) => void) {}
      observe() {
        this.callback([{ isIntersecting: true }]);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => true,
  }));
  vi.spyOn(HTMLMediaElement.prototype, 'canPlayType').mockReturnValue('probably');
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('enhanced player sources', () => {
  it('loads an uncached single-audio MKV as MP4 without a type-discovery HEAD', async () => {
    const requests: string[] = [];
    let queued = false;
    let ready = false;
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${url}`);
      if (method === 'GET') queued = true;
      return new Response(null, { status: ready ? 200 : 202 });
    });

    // jsdom has no media transport. Keep Vidstack's real provider and emulate
    // only the browser GET/error at HTMLMediaElement.load().
    vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      const source = this.querySelector('source');
      if (!source) return;
      void fetch(source.src).then(response => {
        if (response.status === 202) {
          Object.defineProperty(this, 'error', {
            configurable: true,
            value: { code: 4, message: 'Media is still preparing.' },
          });
          this.dispatchEvent(new Event('error'));
        }
      });
    });

    const { container } = renderPlayer();
    await waitFor(() => expect(queued).toBe(true));
    expect(requests[0]).toBe('GET http://localhost:8000/api/video/video/stream/');
    expect(container.querySelector('video source')?.getAttribute('type')).toBe('video/mp4');
    await waitFor(() => expect(screen.getByText(/Transcoding video/)).toBeTruthy());

    ready = true;
    await waitFor(
      () => expect(requests.filter(request => request.startsWith('GET'))).toHaveLength(2),
      { timeout: 7000 },
    );
    expect(screen.queryByText(/Transcoding video/)).toBeNull();
    expect(container.querySelector('video source')?.getAttribute('type')).toBe('video/mp4');
  }, 10000);

  it('keeps the HLS presentation selected when alternate audio is ready', async () => {
    vi.stubGlobal('fetch', async () => new Response('#EXTM3U', { status: 200 }));
    const { container } = renderPlayer({
      ...video,
      streams: [
        ...(video.streams ?? []),
        { type: 'audio', index: 2, codec: 'aac', bitrate: 128000 },
      ],
    });
    await waitFor(() => {
      expect(container.querySelector('video source')?.getAttribute('src')).toBe(
        'http://localhost:8000/api/video/video/hls/master.m3u8',
      );
    });
    expect(container.querySelector('video source')?.getAttribute('type')).toBe(
      'application/x-mpegurl',
    );
  });

  it('uses the archived URL directly when enhanced playback is disabled', async () => {
    useAppSettingsStore.setState({
      appSettingsConfig: {
        ...initialSettings,
        application: { ...initialSettings.application, enable_fork_playback: false },
      },
    });
    const requests: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      requests.push(url);
      return new Response(null, { status: 200 });
    });
    const { container } = renderPlayer({ ...video, media_url: '/media/channel/video.mp4' });
    await waitFor(() => {
      expect(container.querySelector('video')?.getAttribute('src')).toBe(
        'http://localhost:8000/media/channel/video.mp4',
      );
    });
    expect(requests).toEqual([]);
  });
});
