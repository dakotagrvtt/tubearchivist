import { Component, useEffect, useRef, useState } from 'react';
import type { ComponentType, ReactNode } from 'react';
import type { NextVideoType, VideoPlayerProps } from '../../components/VideoPlayer';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';
import EnhancedVideoPlayer from './EnhancedVideoPlayer';
import usePlaylistController from './usePlaylistController';
import type { PlaybackTarget } from './types';

type ErrorBoundaryProps = {
  children: ReactNode;
  fallback: ReactNode;
  onError: () => void;
};

type ErrorBoundaryState = {
  hasError: boolean;
};

class EnhancedPlayerErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error('Enhanced player failed; using native player.', error);
    this.props.onError();
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

const SESSION_FALLBACK_KEY = 'forkEnhancedPlayerFallback';

const readSessionFallback = () => {
  try {
    return window.sessionStorage.getItem(SESSION_FALLBACK_KEY) === 'true';
  } catch {
    return false;
  }
};

const writeSessionFallback = () => {
  try {
    window.sessionStorage.setItem(SESSION_FALLBACK_KEY, 'true');
  } catch {
    // Continue with an in-memory fallback when session storage is unavailable.
  }
};

const clearStoredSessionFallback = () => {
  try {
    window.sessionStorage.removeItem(SESSION_FALLBACK_KEY);
  } catch {
    // The in-memory state is still cleared below.
  }
};

const NextUpOverlay = ({
  nextVideo,
  onCancel,
  onContinue,
}: {
  nextVideo: NextVideoType;
  onCancel: () => void;
  onContinue: () => void;
}) => {
  const [countdown, setCountdown] = useState(10);
  const completedRef = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCountdown(previous => Math.max(previous - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (countdown !== 0 || completedRef.current) {
      return;
    }

    completedRef.current = true;
    onContinue();
  }, [countdown, onContinue]);

  return (
    <div className="player-next-up" role="status">
      {nextVideo.thumbnail && <img src={nextVideo.thumbnail} alt="" />}
      <div>
        <p>Up next in {countdown} seconds</p>
        <h3>{nextVideo.title}</h3>
        <div className="player-next-up-actions">
          <button type="button" onClick={onContinue}>
            Play now
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

const PlaylistControls = ({
  context,
  repeatMode,
  setRepeatMode,
  shuffle,
  setShuffle,
  previousTarget,
  nextTarget,
  navigate,
}: {
  context: NonNullable<PlaybackPlayerProps['playlistContext']>;
  repeatMode: 'off' | 'one' | 'all';
  setRepeatMode: (mode: 'off' | 'one' | 'all') => void;
  shuffle: boolean;
  setShuffle: (enabled: boolean) => void;
  previousTarget: () => PlaybackTarget | null;
  nextTarget: () => PlaybackTarget | null;
  navigate: (target: PlaybackTarget | null) => void;
}) => {
  const previous = previousTarget();
  const next = nextTarget();

  return (
    <div className="fork-playlist-controls" aria-label="Playlist controls">
      <button type="button" disabled={!previous} onClick={() => navigate(previous)}>
        Previous
      </button>
      <button type="button" disabled={!next} onClick={() => navigate(next)}>
        Next
      </button>
      <label>
        <input
          type="checkbox"
          checked={context.autoplay}
          onChange={event => context.onAutoplayChange(event.target.checked)}
        />{' '}
        Autoplay
      </label>
      <label>
        Repeat{' '}
        <select
          value={repeatMode}
          onChange={event => setRepeatMode(event.target.value as 'off' | 'one' | 'all')}
        >
          <option value="off">Off</option>
          <option value="one">One</option>
          <option value="all">All</option>
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={shuffle}
          onChange={event => setShuffle(event.target.checked)}
        />{' '}
        Shuffle
      </label>
      <span className="fork-playlist-name">{context.playlistName}</span>
    </div>
  );
};

type PlaybackPlayerProps = VideoPlayerProps & {
  NativePlayer: ComponentType<VideoPlayerProps>;
};

type PlaybackPlayerSessionProps = PlaybackPlayerProps & {
  playerEnabled: boolean;
};

const PlaybackPlayerSession = ({
  NativePlayer,
  playerEnabled,
  ...props
}: PlaybackPlayerSessionProps) => {
  const [sessionFallback, setSessionFallback] = useState(readSessionFallback);
  const [showNextUp, setShowNextUp] = useState(false);
  const [pendingNext, setPendingNext] = useState<PlaybackTarget | null>(null);
  const playlist = usePlaylistController(props.playlistContext);

  const handleFatalError = () => {
    writeSessionFallback();
    setShowNextUp(false);
    setSessionFallback(true);
  };

  const clearSessionFallback = () => {
    clearStoredSessionFallback();
    setSessionFallback(false);
  };

  const handleEnhancedVideoEnd = () => {
    const target = playlist.takeNextTarget();
    if (props.playlistContext?.autoplay && target) {
      setPendingNext(target);
      setShowNextUp(true);
      return;
    }
    props.onVideoEnd?.();
  };

  const nativePlayer = <NativePlayer key={`native-${props.video.youtube_id}`} {...props} />;

  const enhancedPlayer = (
    <EnhancedVideoPlayer
      key={`enhanced-${props.video.youtube_id}`}
      {...props}
      onVideoEnd={handleEnhancedVideoEnd}
      onFatalError={handleFatalError}
      repeatCurrent={playlist.repeatMode === 'one'}
    />
  );

  if (!playerEnabled || sessionFallback) {
    return (
      <>
        {playerEnabled && sessionFallback && (
          <p className="player-fallback-notice">
            Enhanced Player encountered an error. Using the native player for this session.
          </p>
        )}
        {nativePlayer}
        {playerEnabled && sessionFallback && (
          <div className="player-fallback-actions">
            <button type="button" onClick={clearSessionFallback}>
              Retry enhanced player
            </button>
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <EnhancedPlayerErrorBoundary fallback={nativePlayer} onError={handleFatalError}>
        {enhancedPlayer}
      </EnhancedPlayerErrorBoundary>
      {playerEnabled && props.playlistContext && (
        <PlaylistControls
          context={props.playlistContext}
          repeatMode={playlist.repeatMode}
          setRepeatMode={playlist.setRepeatMode}
          shuffle={playlist.shuffle}
          setShuffle={playlist.setShuffle}
          previousTarget={playlist.previousTarget}
          nextTarget={playlist.nextTarget}
          navigate={playlist.navigate}
        />
      )}
      {showNextUp && props.playlistContext && (
        <NextUpOverlay
          key={pendingNext?.youtube_id ?? props.video.youtube_id}
          nextVideo={{
            title: pendingNext?.title ?? props.nextVideo?.title ?? 'Next video',
            thumbnail:
              pendingNext?.youtube_id === props.playlistContext.next?.youtube_id
                ? props.nextVideo?.thumbnail
                : undefined,
          }}
          onCancel={() => setShowNextUp(false)}
          onContinue={() => {
            setShowNextUp(false);
            playlist.navigate(pendingNext);
            setPendingNext(null);
          }}
        />
      )}
    </>
  );
};

const PlaybackPlayer = (props: PlaybackPlayerProps) => {
  const playerEnabled =
    useAppSettingsStore(state => state.appSettingsConfig.application.enable_fork_player) ?? true;

  return (
    <PlaybackPlayerSession
      key={`${props.video.youtube_id}-${playerEnabled ? 'enhanced' : 'native'}`}
      {...props}
      playerEnabled={playerEnabled}
    />
  );
};

export default PlaybackPlayer;
