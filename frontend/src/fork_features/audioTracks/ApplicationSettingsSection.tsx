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

import { useState, useEffect } from 'react';
import updateAppsettingsConfig from '../../api/actions/updateAppsettingsConfig';
import ToggleConfig from '../../components/ToggleConfig';
import AudioLanguageSelector from './AudioLanguageSelector';
import { AppSettingsSectionProps } from '../registry';

const AudioTracksAppSection = ({ appSettingsConfig, onRefresh }: AppSettingsSectionProps) => {
  const [audioMultistreams, setAudioMultistreams] = useState(false);
  const [audioLanguages, setAudioLanguages] = useState<string | null>(null);
  const [audioWarning, setAudioWarning] = useState<string | null>(null);

  // Sync local state when the parent config refreshes.
  useEffect(() => {
    setAudioMultistreams(appSettingsConfig.downloads.audio_multistreams ?? false);
    setAudioLanguages(appSettingsConfig.downloads.audio_languages || null);
    setAudioWarning(null);
  }, [appSettingsConfig]);

  const handleUpdate = async (
    configKey: string,
    configValue: string | boolean | number | null,
  ) => {
    const [group, key] = configKey.split('.');
    const updatedConfig = { [group]: { [key]: configValue } };
    const response = await updateAppsettingsConfig(updatedConfig);

    if (response?.error?.error) {
      setAudioWarning(response.error.error);
      return;
    }

    setAudioWarning(null);
    onRefresh();
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
