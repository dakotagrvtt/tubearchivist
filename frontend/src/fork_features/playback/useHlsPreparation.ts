import { useCallback, useEffect, useState } from 'react';
import getApiUrl from '../../configuration/getApiUrl';
import type { StreamType } from '../../pages/Home';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';

type HlsState = {
  url: string | null;
  isPreparing: boolean;
  retryKey: number;
};

const useHlsPreparation = (videoId: string, streams: StreamType[] | undefined) => {
  const multiAudioEnabled =
    useAppSettingsStore(
      state => state.appSettingsConfig.application.enable_fork_multi_audio_playback,
    ) ?? true;
  const audioTracksEnabled =
    useAppSettingsStore(state => state.appSettingsConfig.application.enable_fork_audio_tracks) ??
    true;
  const enabled = multiAudioEnabled && audioTracksEnabled;
  const audioCount = streams?.filter(stream => stream.type === 'audio').length ?? 0;
  const eligible = enabled && audioCount >= 2;
  const endpoint = `/api/video/${videoId}/hls/master.m3u8`;
  const [state, setState] = useState<HlsState>({
    url: null,
    isPreparing: false,
    retryKey: 0,
  });

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;

    if (!eligible) {
      return () => undefined;
    }

    const check = async () => {
      try {
        const response = await fetch(`${getApiUrl()}${endpoint}`, {
          credentials: 'include',
        });
        if (cancelled) return;
        if (response.ok) {
          setState({ url: endpoint, isPreparing: false, retryKey: attempts });
          return;
        }
        if (response.status === 202 && attempts < 24) {
          attempts += 1;
          setState(previous => ({ ...previous, isPreparing: true }));
          timer = window.setTimeout(check, 5000);
          return;
        }
        setState({ url: null, isPreparing: false, retryKey: 0 });
      } catch {
        if (!cancelled) setState({ url: null, isPreparing: false, retryKey: 0 });
      }
    };

    void check();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [endpoint, eligible]);

  const fallback = useCallback(() => {
    setState(previous => ({
      ...previous,
      url: null,
      isPreparing: false,
      retryKey: previous.retryKey + 1,
    }));
  }, []);

  return {
    ...state,
    url: eligible ? state.url : null,
    isPreparing: eligible && state.isPreparing,
    fallback,
    hasAlternateAudio: eligible,
  };
};

export default useHlsPreparation;
