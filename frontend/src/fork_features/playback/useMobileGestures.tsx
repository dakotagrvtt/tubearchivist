import { useCallback, useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { MediaPlayerInstance } from '@vidstack/react';

const SEEK_STORAGE_KEY = 'forkPlayerSeekInterval';
const DOUBLE_TAP_STORAGE_KEY = 'forkPlayerDoubleTap';
const SWIPE_STORAGE_KEY = 'forkPlayerSwipeControls';
const SEEK_INTERVALS = [5, 10, 15, 30];
const BRIGHTNESS_MIN = 0.35;
const BRIGHTNESS_MAX = 1.5;
const BRIGHTNESS_STEP = 0.05;

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

const snapBrightness = (value: number) =>
  Number(
    clamp(
      Math.round(value / BRIGHTNESS_STEP) * BRIGHTNESS_STEP,
      BRIGHTNESS_MIN,
      BRIGHTNESS_MAX,
    ).toFixed(2),
  );

const readInterval = () => {
  const value = Number(localStorage.getItem(SEEK_STORAGE_KEY));
  return SEEK_INTERVALS.includes(value) ? value : 10;
};

const readBoolean = (key: string, fallback: boolean) => {
  const value = localStorage.getItem(key);
  return value === null ? fallback : value === 'true';
};

type GestureStart = {
  x: number;
  y: number;
  side: 'left' | 'right';
  volume: number;
  brightness: number;
  height: number;
};

export const useMobileGestures = (playerRef: React.RefObject<MediaPlayerInstance | null>) => {
  const [seekInterval, setSeekInterval] = useState(readInterval);
  const [doubleTapEnabled, setDoubleTapEnabled] = useState(() =>
    readBoolean(DOUBLE_TAP_STORAGE_KEY, true),
  );
  const [swipeEnabled, setSwipeEnabled] = useState(() => readBoolean(SWIPE_STORAGE_KEY, true));
  const [brightness, setBrightness] = useState(1);
  const [feedback, setFeedback] = useState<string | null>(null);
  const startRef = useRef<GestureStart | null>(null);
  const lastTapRef = useRef<{ time: number; side: 'left' | 'right' } | null>(null);
  const feedbackTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    localStorage.setItem(SEEK_STORAGE_KEY, String(seekInterval));
  }, [seekInterval]);

  useEffect(() => {
    localStorage.setItem(DOUBLE_TAP_STORAGE_KEY, String(doubleTapEnabled));
  }, [doubleTapEnabled]);

  useEffect(() => {
    localStorage.setItem(SWIPE_STORAGE_KEY, String(swipeEnabled));
  }, [swipeEnabled]);

  useEffect(
    () => () => {
      if (feedbackTimerRef.current !== undefined) {
        window.clearTimeout(feedbackTimerRef.current);
      }
    },
    [],
  );

  const showFeedback = useCallback((message: string) => {
    setFeedback(message);
    if (feedbackTimerRef.current !== undefined) window.clearTimeout(feedbackTimerRef.current);
    feedbackTimerRef.current = window.setTimeout(() => setFeedback(null), 800);
  }, []);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>, side: 'left' | 'right') => {
    if (!doubleTapEnabled && !swipeEnabled) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    startRef.current = {
      x: event.clientX,
      y: event.clientY,
      side,
      volume: playerRef.current?.volume ?? 1,
      brightness,
      height: bounds.height || 1,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = startRef.current;
    if (!start || !swipeEnabled) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaY) < 12 || Math.abs(deltaY) < Math.abs(deltaX)) return;
    event.preventDefault();
    const adjustment = -deltaY / start.height;
    if (start.side === 'right') {
      const volume = clamp(start.volume + adjustment, 0, 1);
      if (playerRef.current) {
        playerRef.current.volume = volume;
        if (volume > 0) playerRef.current.muted = false;
      }
      showFeedback(`Player volume ${Math.round(volume * 100)}%`);
    } else {
      const nextBrightness = snapBrightness(start.brightness + adjustment);
      setBrightness(nextBrightness);
      showFeedback(`Video brightness ${Math.round(nextBrightness * 100)}%`);
    }
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = startRef.current;
    startRef.current = null;
    if (!start || !doubleTapEnabled) return;
    const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
    if (moved > 28) return;
    const now = Date.now();
    const previousTap = lastTapRef.current;
    if (previousTap && now - previousTap.time < 300 && previousTap.side === start.side) {
      const direction = start.side === 'left' ? -1 : 1;
      const currentTime = playerRef.current?.currentTime ?? 0;
      if (playerRef.current) {
        playerRef.current.currentTime = Math.max(0, currentTime + direction * seekInterval);
      }
      showFeedback(`${direction < 0 ? '−' : '+'}${seekInterval}s`);
      lastTapRef.current = null;
    } else {
      lastTapRef.current = { time: now, side: start.side };
    }
  };

  const gestureLayer = (
    <div className="fork-mobile-gestures">
      <div
        className="fork-mobile-gesture-zone fork-mobile-gesture-left"
        aria-hidden="true"
        onPointerDown={event => onPointerDown(event, 'left')}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          startRef.current = null;
        }}
      />
      <div
        className="fork-mobile-gesture-zone fork-mobile-gesture-right"
        aria-hidden="true"
        onPointerDown={event => onPointerDown(event, 'right')}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          startRef.current = null;
        }}
      />
      {feedback && (
        <div className="fork-gesture-feedback" role="status" aria-live="polite">
          {feedback}
        </div>
      )}
    </div>
  );

  return {
    gestureLayer,
    brightness,
    feedback,
    seekInterval,
    setSeekInterval,
    seekIntervals: SEEK_INTERVALS,
    doubleTapEnabled,
    setDoubleTapEnabled,
    swipeEnabled,
    setSwipeEnabled,
  };
};

export default useMobileGestures;
