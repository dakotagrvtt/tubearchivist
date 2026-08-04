import { Menu, PIPButton, useMediaState, usePlaybackRateOptions } from '@vidstack/react';
import {
  defaultLayoutIcons,
  DefaultMenuButton,
  DefaultMenuRadioGroup,
  DefaultMenuSection,
} from '@vidstack/react/player/layouts/default';

const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

export const SpeedMenuSection = () => {
  const options = usePlaybackRateOptions({ rates: PLAYBACK_RATES });
  if (options.disabled) return null;

  return (
    <Menu.Root className="fork-speed-menu vds-menu">
      <DefaultMenuButton
        label="Speed"
        hint={options.selectedValue === '1' ? 'Normal' : `${options.selectedValue}x`}
        Icon={defaultLayoutIcons.Menu.SpeedUp}
      />
      <Menu.Items className="vds-menu-items">
        <DefaultMenuSection label="Speed">
          <div className="fork-speed-section">
            <DefaultMenuRadioGroup
              value={options.selectedValue ?? '1'}
              options={options.map(option => ({ label: option.label, value: option.value }))}
              onChange={value => options.find(option => option.value === value)?.select()}
            />
          </div>
        </DefaultMenuSection>
      </Menu.Items>
    </Menu.Root>
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
