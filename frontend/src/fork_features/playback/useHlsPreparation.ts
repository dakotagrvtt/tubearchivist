import { useCallback, useEffect, useRef, useState } from 'react';
import getApiUrl from '../../configuration/getApiUrl';
import type { StreamType } from '../../pages/Home';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';

type HlsState = {
  endpoint: string | null;
  url: string | null;
  isPreparing: boolean;
  retryKey: number;
  error: string | null;
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
    endpoint: null,
    url: null,
    isPreparing: false,
    retryKey: 0,
    error: null,
  });
  const [requestKey, setRequestKey] = useState(0);
  const retryEndpointRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;
    const retryEndpoint = retryEndpointRef.current;
    let resetFailedPreparation = retryEndpoint === endpoint;
    retryEndpointRef.current = null;

    if (!eligible) {
      return () => undefined;
    }

    const check = async () => {
      try {
        const retryQuery = resetFailedPreparation ? '?retry=1' : '';
        resetFailedPreparation = false;
        const response = await fetch(`${getApiUrl()}${endpoint}${retryQuery}`, {
          credentials: 'include',
        });
        if (cancelled) return;
        if (response.ok) {
          setState({
            endpoint,
            url: endpoint,
            isPreparing: false,
            retryKey: attempts,
            error: null,
          });
          return;
        }
        if (response.status === 202 && attempts < 24) {
          attempts += 1;
          setState(previous => ({ ...previous, isPreparing: true, error: null }));
          timer = window.setTimeout(check, 5000);
          return;
        }
        setState({
          endpoint,
          url: null,
          isPreparing: false,
          retryKey: 0,
          error: 'Alternate audio is unavailable; using the primary audio track.',
        });
      } catch {
        if (!cancelled) {
          setState({
            endpoint,
            url: null,
            isPreparing: false,
            retryKey: 0,
            error: 'Alternate audio could not be loaded; using the primary audio track.',
          });
        }
      }
    };

    void check();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [endpoint, eligible, requestKey]);

  const fallback = useCallback(() => {
    setState(previous => ({
      ...previous,
      url: null,
      isPreparing: false,
      retryKey: previous.retryKey + 1,
      error: 'Alternate audio playback failed; using the primary audio track.',
    }));
  }, []);

  const retry = useCallback(() => {
    setState(previous => ({
      ...previous,
      url: null,
      isPreparing: true,
      error: null,
      retryKey: previous.retryKey + 1,
    }));
    retryEndpointRef.current = endpoint;
    setRequestKey(previous => previous + 1);
  }, [endpoint]);

  return {
    ...state,
    url: eligible && state.endpoint === endpoint ? state.url : null,
    isPreparing: eligible && (state.endpoint !== endpoint || state.isPreparing),
    error: eligible && state.endpoint === endpoint ? state.error : null,
    retryKey: eligible && state.endpoint === endpoint ? state.retryKey : 0,
    fallback,
    retry,
    hasAlternateAudio: eligible,
  };
};

export default useHlsPreparation;
