import { useCallback, useEffect, useState } from 'react';
import getApiUrl from '../../configuration/getApiUrl';

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

const usePlaybackPreparation = (videoUrl: string) => {
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
      setState({
        ...current,
        error: payload?.error || 'Video could not be loaded.',
      });
    } catch {
      setState({ ...current, error: 'Unable to load this video.' });
    }
  }, [current, videoUrl]);

  return { ...current, handleError };
};

export default usePlaybackPreparation;
