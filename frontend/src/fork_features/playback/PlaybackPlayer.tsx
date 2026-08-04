import { Component, useEffect, useRef, useState } from 'react';
import type { ComponentType, ReactNode } from 'react';
import type { NextVideoType, VideoPlayerProps } from '../../components/VideoPlayer';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';
import EnhancedVideoPlayer from './EnhancedVideoPlayer';

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
      <img src={nextVideo.thumbnail} alt="" />
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
    if (props.nextVideo) {
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
      {showNextUp && props.nextVideo && (
        <NextUpOverlay
          nextVideo={props.nextVideo}
          onCancel={() => setShowNextUp(false)}
          onContinue={() => {
            setShowNextUp(false);
            props.onVideoEnd?.();
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
