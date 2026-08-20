/**
 * Fork Feature: Audio Tracks – Application Settings section
 *
 * Renders the "Enable multistream audio" toggle and the audio language
 * selector inside the Download Format settings box on the Application
 * Settings page.
 *
 * Self-contained: manages its own local state and calls the API directly,
 * then calls props.onRefresh() so the parent page re-syncs.
 */

import { useState } from 'react';
import updateAppsettingsConfig, {
  AppSettingsConfigUpdate,
} from '../../api/actions/updateAppsettingsConfig';
import ToggleConfig from '../../components/ToggleConfig';
import AudioLanguageSelector from './AudioLanguageSelector';
import { AppSettingsSectionProps } from '../registry';
import { getApiErrorMessage } from '../../functions/APIClient';

const AudioTracksAppSection = ({ appSettingsConfig, onRefresh }: AppSettingsSectionProps) => {
  const audioTracksEnabled = appSettingsConfig.application.enable_fork_audio_tracks ?? true;
  const [audioMultistreams, setAudioMultistreams] = useState(
    appSettingsConfig.downloads.audio_multistreams ?? false,
  );
  const [audioLanguages, setAudioLanguages] = useState<string | null>(
    appSettingsConfig.downloads.audio_languages || null,
  );
  const [audioWarning, setAudioWarning] = useState<string | null>(null);

  const [previousSettings, setPreviousSettings] = useState({
    config: appSettingsConfig,
    enabled: audioTracksEnabled,
  });
  if (
    appSettingsConfig !== previousSettings.config ||
    audioTracksEnabled !== previousSettings.enabled
  ) {
    setPreviousSettings({ config: appSettingsConfig, enabled: audioTracksEnabled });
    if (audioTracksEnabled) {
      setAudioMultistreams(appSettingsConfig.downloads.audio_multistreams ?? false);
      setAudioLanguages(appSettingsConfig.downloads.audio_languages || null);
      setAudioWarning(null);
    }
  }

  if (!audioTracksEnabled) {
    return null;
  }

  const handleUpdate = async (configKey: string, configValue: string | boolean | number | null) => {
    const [group, key] = configKey.split('.');
    const updatedConfig = { [group]: { [key]: configValue } } as AppSettingsConfigUpdate;
    try {
      const response = await updateAppsettingsConfig(updatedConfig);
      if (response?.error?.error) {
        throw new Error(response.error.error);
      }
      setAudioWarning(null);
      onRefresh();
    } catch (error) {
      setAudioWarning(getApiErrorMessage(error, 'Failed to update audio settings.'));
      throw error;
    }
  };

  return (
    <>
      <div className="settings-box-wrapper">
        <div>
          <p>Enable multistream audio</p>
        </div>
        <ToggleConfig
          name="downloads.audio_multistreams"
          value={audioMultistreams}
          text="Enable to include multiple audio languages when available."
          updateCallback={handleUpdate}
        />
        {audioWarning && <p className="settings-error">{audioWarning}</p>}
      </div>

      {audioMultistreams && (
        <div className="settings-box-wrapper">
          <div>
            <p>Audio languages</p>
          </div>
          <AudioLanguageSelector
            name="downloads.audio_languages"
            value={audioLanguages}
            oldValue={appSettingsConfig.downloads.audio_languages}
            updateCallback={handleUpdate}
          />
        </div>
      )}
    </>
  );
};

export default AudioTracksAppSection;
