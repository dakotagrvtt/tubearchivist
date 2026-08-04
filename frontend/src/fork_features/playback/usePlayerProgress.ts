import { useCallback, useEffect, useRef } from 'react';
import updateVideoProgressById from '../../api/actions/updateVideoProgressById';

type ProgressResponse = {
  watched?: boolean;
};

type ProgressSnapshot = {
  currentTime: number;
  duration: number;
};

type PlayerProgressOptions = {
  videoId: string;
  watched: boolean;
  onWatchStateChanged?: (status: boolean) => void;
};

/**
 * Persist playback position without relying on a timeupdate event landing on
 * an exact modulo boundary. Requests are serialized so a slow older request
 * cannot overtake a newer position update from the same player.
 */
const usePlayerProgress = ({ videoId, watched, onWatchStateChanged }: PlayerProgressOptions) => {
  const snapshotRef = useRef<ProgressSnapshot>({ currentTime: 0, duration: 0 });
  const lastQueuedPositionRef = useRef<number | null>(null);
  const lastSavedPositionRef = useRef<number>(0);
  const requestActiveRef = useRef(false);
  const drainQueueRef = useRef<() => void>(() => undefined);
  const watchedRef = useRef(watched);
  const onWatchStateChangedRef = useRef(onWatchStateChanged);

  useEffect(() => {
    watchedRef.current = watched;
  }, [watched]);

  useEffect(() => {
    onWatchStateChangedRef.current = onWatchStateChanged;
  }, [onWatchStateChanged]);

  const drainQueue = useCallback(() => {
    if (requestActiveRef.current || lastQueuedPositionRef.current === null) {
      return;
    }

    const position = lastQueuedPositionRef.current;
    lastQueuedPositionRef.current = null;
    requestActiveRef.current = true;
    let requestSucceeded = false;

    void updateVideoProgressById({
      youtubeId: videoId,
      currentProgress: position,
    })
      .then(response => {
        if (response?.error || !response?.data) {
          throw new Error('Playback progress was not saved.');
        }
        const data = response?.data as ProgressResponse | undefined;
        lastSavedPositionRef.current = position;
        requestSucceeded = true;
        if (data?.watched && !watchedRef.current) {
          watchedRef.current = true;
          onWatchStateChangedRef.current?.(true);
        }
      })
      .catch(() => {
        // A later timeupdate or lifecycle event will retry the position.
        if (lastQueuedPositionRef.current === null) {
          lastQueuedPositionRef.current = position;
        }
      })
      .finally(() => {
        requestActiveRef.current = false;
        if (requestSucceeded) {
          drainQueueRef.current();
        }
      });
  }, [videoId]);

  useEffect(() => {
    drainQueueRef.current = drainQueue;
  }, [drainQueue]);

  const queuePosition = useCallback(
    (position: number, force = false) => {
      if (!Number.isFinite(position) || (position < 5 && !force)) {
        return;
      }

      if (!force && Math.abs(position - lastSavedPositionRef.current) < 10) {
        return;
      }

      lastQueuedPositionRef.current = position;
      drainQueue();
    },
    [drainQueue],
  );

  const onTimeUpdate = useCallback(
    (currentTime: number, duration: number) => {
      snapshotRef.current = { currentTime, duration };
      queuePosition(currentTime);
    },
    [queuePosition],
  );

  const flush = useCallback(() => {
    const { currentTime } = snapshotRef.current;
    queuePosition(currentTime, true);
  }, [queuePosition]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flush();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', flush);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', flush);
    };
  }, [flush]);

  return {
    onTimeUpdate,
    onPause: flush,
    onEnded: flush,
  };
};

export default usePlayerProgress;
