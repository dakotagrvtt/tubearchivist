import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { PlaybackPlaylistContext, PlaybackTarget, RepeatMode } from './types';

const REPEAT_STORAGE_KEY = 'forkPlayerRepeatMode';
const SHUFFLE_STORAGE_KEY = 'forkPlayerShuffle';
const SHUFFLE_HISTORY_KEY = 'forkPlayerShuffleHistory';

const readRepeatMode = (): RepeatMode => {
  const value = localStorage.getItem(REPEAT_STORAGE_KEY);
  return value === 'one' || value === 'all' ? value : 'off';
};

const readShuffle = () => localStorage.getItem(SHUFFLE_STORAGE_KEY) === 'true';

const readShuffleHistory = (): string[] => {
  try {
    const stored = sessionStorage.getItem(SHUFFLE_HISTORY_KEY);
    const history = stored ? JSON.parse(stored) : [];
    return Array.isArray(history) ? history.filter(value => typeof value === 'string') : [];
  } catch {
    return [];
  }
};

const writeShuffleHistory = (history: string[]) => {
  try {
    sessionStorage.setItem(SHUFFLE_HISTORY_KEY, JSON.stringify(history.slice(-50)));
  } catch {
    // Shuffle remains functional when session storage is unavailable.
  }
};

export const chooseRandomIndex = (length: number, currentIndex: number, random = Math.random()) => {
  const candidates = Array.from({ length }, (_, index) => index).filter(
    index => index !== currentIndex,
  );
  if (!candidates.length) return -1;
  return candidates[Math.min(Math.floor(random * candidates.length), candidates.length - 1)];
};

const entryTarget = (
  entry: PlaybackPlaylistContext['entries'][number] | undefined,
): PlaybackTarget | null =>
  entry
    ? {
        youtube_id: entry.youtube_id,
        title: entry.title,
      }
    : null;

const usePlaylistController = (context: PlaybackPlaylistContext | undefined) => {
  const [repeatMode, setRepeatMode] = useState<RepeatMode>(() => readRepeatMode());
  const [shuffle, setShuffle] = useState(() => readShuffle());
  const shuffleHistoryRef = useRef<string[]>(readShuffleHistory());
  const shufflePreviewRef = useRef<{ videoId: string; target: PlaybackTarget | null }>({
    videoId: '',
    target: null,
  });

  useEffect(() => {
    localStorage.setItem(REPEAT_STORAGE_KEY, repeatMode);
  }, [repeatMode]);

  useEffect(() => {
    localStorage.setItem(SHUFFLE_STORAGE_KEY, String(shuffle));
    if (!shuffle) {
      shuffleHistoryRef.current = [];
      writeShuffleHistory([]);
    }
  }, [shuffle]);

  const currentIndex = useMemo(
    () => context?.entries.findIndex(entry => entry.youtube_id === context.currentVideoId) ?? -1,
    [context],
  );

  const selectNextTarget = useCallback(
    (commit: boolean): PlaybackTarget | null => {
      if (!context || currentIndex < 0) return null;
      if (repeatMode === 'one') return entryTarget(context.entries[currentIndex]);

      if (shuffle) {
        if (!commit && shufflePreviewRef.current.videoId === context.currentVideoId) {
          return shufflePreviewRef.current.target;
        }
        const available = context.entries.filter(
          entry =>
            entry.youtube_id !== context.currentVideoId &&
            !shuffleHistoryRef.current.includes(entry.youtube_id),
        );
        const pool = available.length
          ? available
          : context.entries.filter(entry => entry.youtube_id !== context.currentVideoId);
        if (!pool.length) return null;
        const selected = pool[Math.floor(Math.random() * pool.length)];
        const target = entryTarget(selected);
        shufflePreviewRef.current = { videoId: context.currentVideoId, target };
        if (commit) {
          const currentHistory = shuffleHistoryRef.current.filter(entry =>
            context.entries.some(candidate => candidate.youtube_id === entry),
          );
          if (currentHistory.at(-1) !== context.currentVideoId) {
            currentHistory.push(context.currentVideoId);
          }
          currentHistory.push(selected.youtube_id);
          shuffleHistoryRef.current = currentHistory.slice(-50);
          writeShuffleHistory(shuffleHistoryRef.current);
        }
        return target;
      }

      const next = context.entries[currentIndex + 1];
      if (next) return entryTarget(next);
      return repeatMode === 'all' ? entryTarget(context.entries[0]) : null;
    },
    [context, currentIndex, repeatMode, shuffle],
  );

  const nextTarget = useCallback(() => selectNextTarget(false), [selectNextTarget]);
  const takeNextTarget = useCallback(() => selectNextTarget(true), [selectNextTarget]);

  const previousTarget = useCallback((): PlaybackTarget | null => {
    if (!context || currentIndex < 0) return null;
    if (shuffle) {
      const historyIndex = shuffleHistoryRef.current.lastIndexOf(context.currentVideoId);
      const previousId = historyIndex > 0 ? shuffleHistoryRef.current[historyIndex - 1] : undefined;
      const previous = context.entries.find(entry => entry.youtube_id === previousId);
      if (previous) return entryTarget(previous);
    }
    const previous = context.entries[currentIndex - 1];
    if (previous) return entryTarget(previous);
    return repeatMode === 'all' ? entryTarget(context.entries[context.entries.length - 1]) : null;
  }, [context, currentIndex, repeatMode, shuffle]);

  const navigate = useCallback(
    (target: PlaybackTarget | null) => {
      if (target && context) context.onNavigate(target.youtube_id);
    },
    [context],
  );

  return {
    repeatMode,
    setRepeatMode,
    shuffle,
    setShuffle,
    nextTarget,
    takeNextTarget,
    previousTarget,
    navigate,
    currentIndex,
  };
};

export default usePlaylistController;
