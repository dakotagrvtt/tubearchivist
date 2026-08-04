import {
  isHLSProvider,
  MediaPlayer,
  MediaProvider,
  Track,
  type MediaPlayerInstance,
} from '@vidstack/react';
import { defaultLayoutIcons, DefaultVideoLayout } from '@vidstack/react/player/layouts/default';
import '@vidstack/react/player/styles/default/theme.css';
import '@vidstack/react/player/styles/default/layouts/video.css';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import getApiUrl from '../../configuration/getApiUrl';
import PlaybackPreparationStatus from './PlaybackPreparationStatus';
import usePlaybackPreparation from './usePlaybackPreparation';
import usePlayerProgress from './usePlayerProgress';
import useSponsorBlock from './useSponsorBlock';
import useChapterTrack from './useChapterTrack';
import useMobileGestures from './useMobileGestures';
import useHlsPreparation from './useHlsPreparation';
import { MobilePipButton, SpeedMenuSection } from './PlaybackControls';
import type { VideoPlayerProps } from '../../components/VideoPlayer';

const SUBTITLE_STORAGE_KEY = 'playerSubtitleTrack';

type EnhancedVideoPlayerProps = VideoPlayerProps & {
  onFatalError?: () => void;
  repeatCurrent?: boolean;
};

const subtitleLabel = (subtitle: { name: string; source: string }) => {
  return subtitle.source === 'auto' ? `${subtitle.name} - auto` : subtitle.name;
};

const EnhancedVideoPlayer = ({
  video,
  sponsorBlock,
  embed,
  autoplay = false,
  onWatchStateChanged,
  onVideoEnd,
  seekToTimestamp,
  setSeekToTimestamp,
  onFatalError,
  repeatCurrent = false,
}: EnhancedVideoPlayerProps) => {
  const playerRef = useRef<MediaPlayerInstance>(null);
  const initialSeekDone = useRef(false);
  const theaterModeRef = useRef(false);
  const [isTheaterMode, setIsTheaterMode] = useState(false);
  const [searchParams] = useSearchParams();
  const searchParamVideoProgress = searchParams.get('t');
  const videoId = video.youtube_id;
  const playbackPreparation = usePlaybackPreparation(videoId, video.media_url);
  const hlsPreparation = useHlsPreparation(videoId, video.streams);
  const videoUrl = playbackPreparation.videoUrl;
  const sourceUrl = hlsPreparation.url ?? videoUrl;
  const playbackProgress = usePlayerProgress({
    videoId,
    watched: video.player.watched,
    onWatchStateChanged,
  });
  const sponsor = useSponsorBlock(sponsorBlock);
  const chapterTrack = useChapterTrack(video.chapters);
  const gestures = useMobileGestures(playerRef);
  const requestedProgress =
    searchParamVideoProgress !== null
      ? Number(searchParamVideoProgress)
      : Number(video.player.position);
  const initialProgress =
    Number.isFinite(requestedProgress) && requestedProgress > 0 ? requestedProgress : 0;
  const preferredSubtitle = localStorage.getItem(SUBTITLE_STORAGE_KEY);
  const storedVolume = Number(localStorage.getItem('playerVolume') ?? 1);
  const storedSpeed = Number(localStorage.getItem('playerSpeed') ?? 1);
  const volume = Number.isFinite(storedVolume) ? Math.min(Math.max(storedVolume, 0), 1) : 1;
  const playbackRate = Number.isFinite(storedSpeed) ? storedSpeed : 1;
  const sourceKey = `${sourceUrl}-${playbackPreparation.retryKey}-${hlsPreparation.retryKey}`;
  const previousSourceKey = useRef(sourceKey);
  const lastPlaybackTime = useRef(initialProgress);
  const playbackIntent = useRef(autoplay);
  const pendingSourceRestore = useRef<{
    currentTime: number;
    shouldPlay: boolean;
  } | null>(null);

  useLayoutEffect(() => {
    if (previousSourceKey.current === sourceKey) {
      return;
    }

    pendingSourceRestore.current = {
      currentTime: lastPlaybackTime.current,
      shouldPlay: playbackIntent.current,
    };
    previousSourceKey.current = sourceKey;
  }, [sourceKey]);

  useEffect(() => {
    if (embed) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 't') {
        event.preventDefault();
        setIsTheaterMode(current => {
          const next = !current;
          theaterModeRef.current = next;
          return next;
        });
      } else if (event.key === 'Escape' && theaterModeRef.current) {
        event.preventDefault();
        theaterModeRef.current = false;
        setIsTheaterMode(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [embed]);

  useEffect(() => {
    if (seekToTimestamp === undefined || !playerRef.current) {
      return;
    }

    if (
      !Number.isFinite(playerRef.current.duration) ||
      seekToTimestamp > playerRef.current.duration
    ) {
      return;
    }

    playerRef.current.currentTime = seekToTimestamp;
    lastPlaybackTime.current = seekToTimestamp;
    playbackIntent.current = true;
    void playerRef.current.play().catch(() => undefined);
    setSeekToTimestamp?.(undefined);
    window.scroll(0, 0);
  }, [seekToTimestamp, setSeekToTimestamp]);

  const handleTimeUpdate = (detail: { currentTime: number }) => {
    const currentTime = Number(detail.currentTime);
    lastPlaybackTime.current = currentTime;
    const duration = playerRef.current?.duration ?? video.player.duration;
    sponsor.onTimeUpdate(currentTime, time => {
      if (playerRef.current) {
        playerRef.current.currentTime = time;
      }
    });
    playbackProgress.onTimeUpdate(currentTime, duration);
  };

  const handleEnded = () => {
    playbackProgress.onEnded();
    sponsor.reset();
    if (repeatCurrent && playerRef.current) {
      lastPlaybackTime.current = 0;
      playbackIntent.current = true;
      playerRef.current.currentTime = 0;
      void playerRef.current.play().catch(() => undefined);
      return;
    }
    onVideoEnd?.();
  };

  const handleCanPlay = () => {
    if (!playerRef.current) {
      return;
    }

    const restore = pendingSourceRestore.current;
    if (restore) {
      pendingSourceRestore.current = null;
      const duration = playerRef.current.duration;
      const currentTime = Number.isFinite(duration)
        ? Math.min(restore.currentTime, duration)
        : restore.currentTime;
      playerRef.current.currentTime = Math.max(currentTime, 0);
      lastPlaybackTime.current = Math.max(currentTime, 0);
      initialSeekDone.current = true;
      if (restore.shouldPlay) {
        playbackIntent.current = true;
        void playerRef.current.play().catch(() => undefined);
      }
      return;
    }

    if (initialSeekDone.current) {
      return;
    }

    if (initialProgress > 0) {
      playerRef.current.currentTime = initialProgress;
      lastPlaybackTime.current = initialProgress;
    }
    initialSeekDone.current = true;
  };

  const playerClassName = embed ? 'enhanced-video-player embedded' : 'enhanced-video-player';

  const playerWrapperClass = embed ? '' : `player-wrapper ${isTheaterMode ? 'theater-mode' : ''}`;
  const videoMainClass = embed ? '' : `video-main ${isTheaterMode ? 'theater-mode' : ''}`;

  return (
    <>
      <div id="player" className={playerWrapperClass}>
        <div className={videoMainClass}>
          <PlaybackPreparationStatus
            isPreparing={playbackPreparation.isPreparing}
            error={playbackPreparation.error}
          />
          {hlsPreparation.isPreparing && (
            <p className="video-transcoding" role="status">
              Preparing alternate audio tracks…
            </p>
          )}
          {hlsPreparation.error && (
            <div className="fork-hls-status" role="status">
              <p className="settings-error">{hlsPreparation.error}</p>
              {hlsPreparation.hasAlternateAudio && (
                <button type="button" onClick={hlsPreparation.retry}>
                  Retry alternate audio
                </button>
              )}
            </div>
          )}
          <div className={playerClassName}>
            <MediaPlayer
              ref={playerRef}
              key={sourceKey}
              className="vidstack-player"
              style={{ '--fork-video-brightness': gestures.brightness }}
              src={`${getApiUrl()}${sourceUrl}`}
              title={video.title}
              poster={`${getApiUrl()}${video.vid_thumb_url}`}
              autoPlay={autoplay}
              playsInline
              crossOrigin="use-credentials"
              storage={null}
              onProviderChange={provider => {
                if (isHLSProvider(provider)) {
                  provider.library = () => import('hls.js');
                }
              }}
              onHlsLibLoadError={() => {
                hlsPreparation.fallback();
              }}
              volume={volume}
              playbackRate={playbackRate}
              keyDisabled={false}
              keyShortcuts={{
                togglePaused: 'p',
                toggleMuted: 'm',
                toggleFullscreen: 'f',
                toggleCaptions: 'c',
                seekBackward: ['ArrowLeft'],
                seekForward: ['ArrowRight'],
                speedUp: '>',
                slowDown: '<',
              }}
              onCanPlay={handleCanPlay}
              onTimeUpdate={handleTimeUpdate}
              onPlay={() => {
                playbackIntent.current = true;
              }}
              onPause={() => {
                playbackIntent.current = false;
                playbackProgress.onPause();
              }}
              onEnded={handleEnded}
              onVolumeChange={detail => {
                localStorage.setItem('playerVolume', detail.volume.toString());
              }}
              onRateChange={rate => {
                localStorage.setItem('playerSpeed', rate.toString());
              }}
              onTextTrackChange={track => {
                localStorage.setItem(SUBTITLE_STORAGE_KEY, track?.id ?? 'off');
              }}
              onError={() => {
                if (hlsPreparation.url) {
                  hlsPreparation.fallback();
                  return;
                }
                void playbackPreparation.handleError().then(result => {
                  if (result === 'error') {
                    onFatalError?.();
                  }
                });
              }}
            >
              <MediaProvider>
                {chapterTrack && (
                  <Track
                    id="chapters"
                    kind="chapters"
                    label="Chapters"
                    src={chapterTrack}
                    default
                  />
                )}
                {video.subtitles?.map(subtitle => (
                  <Track
                    key={`${subtitle.lang}-${subtitle.source}-${subtitle.name}`}
                    id={`${subtitle.lang}-${subtitle.source}-${subtitle.name}`}
                    kind="subtitles"
                    label={subtitleLabel(subtitle)}
                    lang={subtitle.lang}
                    src={`${getApiUrl()}${subtitle.media_url}`}
                    default={
                      preferredSubtitle === `${subtitle.lang}-${subtitle.source}-${subtitle.name}`
                    }
                  />
                ))}
              </MediaProvider>
              <DefaultVideoLayout
                icons={defaultLayoutIcons}
                noAudioGain
                noGestures
                slots={{
                  googleCastButton: null,
                  settingsMenuItemsStart: <SpeedMenuSection />,
                  smallLayout: {
                    afterFullscreenButton: <MobilePipButton />,
                  },
                }}
              />
              {gestures.gestureLayer}
            </MediaPlayer>
          </div>
          <div className="fork-gesture-settings" aria-label="Mobile player settings">
            <p className="settings-help-text">
              Swipe controls adjust the player only; Android system volume and brightness are
              unchanged.
            </p>
            <label>
              Seek interval{' '}
              <select
                value={gestures.seekInterval}
                onChange={event => gestures.setSeekInterval(Number(event.target.value))}
              >
                {gestures.seekIntervals.map(interval => (
                  <option key={interval} value={interval}>
                    {interval}s
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={gestures.doubleTapEnabled}
                onChange={event => gestures.setDoubleTapEnabled(event.target.checked)}
              />{' '}
              Double-tap seek (left/right)
            </label>
            <label>
              <input
                type="checkbox"
                checked={gestures.swipeEnabled}
                onChange={event => gestures.setSwipeEnabled(event.target.checked)}
              />{' '}
              Swipe player volume/brightness
            </label>
          </div>
        </div>
      </div>

      {!embed && sponsorBlock?.is_enabled && (
        <div className="sponsorblock" id="sponsorblock">
          {Object.values(sponsor.skippedSegments).map(({ from, to }, index) =>
            from !== 0 && to !== 0 ? (
              <h3 key={`${from}-${to}-${index}`}>
                Skipped sponsor segment from {Math.floor(from / 60)}:
                {String(Math.floor(from % 60)).padStart(2, '0')} to {Math.floor(to / 60)}:
                {String(Math.floor(to % 60)).padStart(2, '0')}.
              </h3>
            ) : null,
          )}
        </div>
      )}
    </>
  );
};

export default EnhancedVideoPlayer;
