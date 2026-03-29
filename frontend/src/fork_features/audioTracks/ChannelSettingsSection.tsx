/**
 * Fork Feature: Audio Tracks – Channel Settings section
 *
 * Renders the "Enable multistream audio" toggle and the audio language
 * selector inside the Channel Customization box on the Channel About page.
 *
 * Self-contained: manages its own local state and calls the API directly,
 * then calls props.onRefresh() so the parent page re-syncs.
 */

import { useState, useEffect } from 'react';
import updateChannelOverwrites from '../../api/actions/updateChannelOverwrite';
import ToggleConfig from '../../components/ToggleConfig';
import AudioLanguageSelector from './AudioLanguageSelector';
import { ChannelSettingsSectionProps } from '../registry';

const AudioTracksChannelSection = ({
  channel,
  appSettingsConfig,
  onRefresh,
}: ChannelSettingsSectionProps) => {
  // null means "use global setting" (no per-channel overwrite stored).
  const [audioMultistreams, setAudioMultistreams] = useState<boolean | null>(null);
  const [audioLanguages, setAudioLanguages] = useState<string | null>(null);
  const [audioWarning, setAudioWarning] = useState<string | null>(null);

  // Sync local state when the parent refreshes.
  useEffect(() => {
    setAudioMultistreams(channel.channel_overwrites?.audio_multistreams ?? null);
    setAudioLanguages(channel.channel_overwrites?.audio_languages ?? null);
    setAudioWarning(null);
  }, [channel]);

  const globalAudioMultistream = appSettingsConfig.downloads.audio_multistreams ?? false;
  const effectiveAudioMultistream = audioMultistreams ?? globalAudioMultistream;

  const handleUpdate = async (
    configKey: string,
    configValue: string | boolean | number | null,
  ) => {
    const response = await updateChannelOverwrites(channel.channel_id, configKey, configValue);

    if (response?.error?.error) {
      setAudioWarning(response.error.error);
      return;
    }

    setAudioWarning(null);
    if (configKey === 'audio_multistreams') {
      setAudioMultistreams(configValue === null ? null : Boolean(configValue));
    }
    onRefresh();
  };

  return (
    <>
      <div className="settings-box-wrapper">
        <div>
          <p>Enable multistream audio</p>
        </div>
        <ToggleConfig
          name="audio_multistreams"
          value={effectiveAudioMultistream}
          text={
            audioMultistreams === null
              ? `Enable to include multiple audio languages when available for this channel. Using global setting: ${globalAudioMultistream ? 'On' : 'Off'}.`
              : 'Enable to include multiple audio languages when available for this channel.'
          }
          updateCallback={handleUpdate}
          resetCallback={() => {
            handleUpdate('audio_multistreams', null);
            setAudioMultistreams(null);
          }}
        />
        {audioWarning && <p className="settings-error">{audioWarning}</p>}
      </div>

      {effectiveAudioMultistream && (
        <div className="settings-box-wrapper">
          <div>
            <p>Audio Languages</p>
          </div>
          <AudioLanguageSelector
            name="audio_languages"
            value={audioLanguages}
            oldValue={channel.channel_overwrites?.audio_languages ?? null}
            updateCallback={handleUpdate}
          />
        </div>
      )}
    </>
  );
};

export default AudioTracksChannelSection;
