import { useCallback, useEffect, useState } from 'react';
import getApiUrl from '../../configuration/getApiUrl';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';

const PLAYBACK_DISABLED_ERROR = 'enhanced playback is disabled';

type PlaybackPreparationState = {
  videoUrl: string;
  isPreparing: boolean;
  error: string | null;
  retryKey: number;
};

const initialState = (videoUrl: string): PlaybackPreparationState => ({
  videoUrl,
  isPreparing: false,
  error: null,
  retryKey: 0,
});

const disablePlaybackForSession = () => {
  useAppSettingsStore.setState(state => ({
    appSettingsConfig: {
      ...state.appSettingsConfig,
      application: {
        ...state.appSettingsConfig.application,
        enable_fork_playback: false,
      },
    },
  }));
};

const usePlaybackPreparation = (videoId: string, mediaUrl: string) => {
  const playbackEnabled =
    useAppSettingsStore(state => state.appSettingsConfig.application.enable_fork_playback) ?? true;
  const videoUrl = playbackEnabled ? `/api/video/${videoId}/stream/` : mediaUrl;
  const [state, setState] = useState(() => initialState(videoUrl));
  const current = state.videoUrl === videoUrl ? state : initialState(videoUrl);

  useEffect(() => {
    if (!current.isPreparing) return;

    const timer = window.setTimeout(() => {
      setState(previous => {
        if (previous.videoUrl !== videoUrl) return previous;
        return {
          ...previous,
          isPreparing: false,
          retryKey: previous.retryKey + 1,
        };
      });
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [current.isPreparing, videoUrl]);

  const handleError = useCallback(async () => {
    if (!playbackEnabled) {
      setState({ ...current, error: 'Video could not be loaded.' });
      return;
    }

    try {
      const response = await fetch(`${getApiUrl()}${videoUrl}`, {
        method: 'HEAD',
      });
      if (response.status === 202) {
        setState({
          ...current,
          isPreparing: true,
          error: null,
        });
        return;
      }
      if (response.ok) {
        setState({ ...current, error: null });
        return;
      }

      const statusResponse = await fetch(`${getApiUrl()}${videoUrl}status/`);
      const payload = await statusResponse.json().catch(() => undefined);
      if (payload?.error === PLAYBACK_DISABLED_ERROR) {
        disablePlaybackForSession();
        return;
      }
      setState({
        ...current,
        error: payload?.error || 'Video could not be loaded.',
      });
    } catch {
      setState({ ...current, error: 'Unable to load this video.' });
    }
  }, [current, playbackEnabled, videoUrl]);

  return { ...current, handleError, videoUrl };
};

export default usePlaybackPreparation;
