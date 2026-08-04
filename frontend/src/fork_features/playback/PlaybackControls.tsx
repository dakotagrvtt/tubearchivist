import { PIPButton, useMediaState, usePlaybackRateOptions } from '@vidstack/react';
import {
  defaultLayoutIcons,
  DefaultMenuRadioGroup,
  DefaultMenuSection,
} from '@vidstack/react/player/layouts/default';

const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

export const SpeedMenuSection = () => {
  const options = usePlaybackRateOptions({ rates: PLAYBACK_RATES });
  if (options.disabled) return null;

  return (
    <DefaultMenuSection
      label="Speed"
      value={options.selectedValue === '1' ? 'Normal' : `${options.selectedValue}x`}
    >
      <div className="fork-speed-section">
        <DefaultMenuRadioGroup
          value={options.selectedValue ?? '1'}
          options={options.map(option => ({ label: option.label, value: option.value }))}
          onChange={value => options.find(option => option.value === value)?.select()}
        />
      </div>
    </DefaultMenuSection>
  );
};

export const MobilePipButton = () => {
  const canPictureInPicture = useMediaState('canPictureInPicture');
  const pictureInPicture = useMediaState('pictureInPicture');
  const label = canPictureInPicture
    ? pictureInPicture
      ? 'Exit picture-in-picture'
      : 'Enter picture-in-picture'
    : 'Picture-in-picture unavailable in this browser';

  return (
    <PIPButton
      className="fork-pip-button vds-pip-button vds-button"
      aria-label={label}
      title={label}
      disabled={!canPictureInPicture}
    >
      {pictureInPicture ? (
        <defaultLayoutIcons.PIPButton.Exit className="vds-icon" />
      ) : (
        <defaultLayoutIcons.PIPButton.Enter className="vds-icon" />
      )}
    </PIPButton>
  );
};
