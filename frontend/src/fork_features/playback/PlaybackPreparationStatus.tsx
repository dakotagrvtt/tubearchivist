type PlaybackPreparationStatusProps = {
  isPreparing: boolean;
  error: string | null;
};

const PlaybackPreparationStatus = ({ isPreparing, error }: PlaybackPreparationStatusProps) => {
  return (
    <>
      {isPreparing && (
        <p className="video-transcoding">
          Transcoding video for browser playback, retrying in 5 seconds…
        </p>
      )}
      {error && <p className="settings-error">{error}</p>}
    </>
  );
};

export default PlaybackPreparationStatus;
