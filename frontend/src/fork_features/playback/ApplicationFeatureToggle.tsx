import { useEffect, useState } from 'react';
import updateAppsettingsConfig from '../../api/actions/updateAppsettingsConfig';
import ToggleConfig from '../../components/ToggleConfig';
import { getApiErrorMessage } from '../../functions/APIClient';
import { useAppSettingsStore } from '../../stores/AppSettingsStore';
import { AppSettingsSectionProps } from '../registry';

const PlaybackFeatureToggle = ({ appSettingsConfig, onRefresh }: AppSettingsSectionProps) => {
  const setAppSettingsConfig = useAppSettingsStore(state => state.setAppSettingsConfig);
  const configuredValue = appSettingsConfig.application.enable_fork_playback ?? true;
  const [enabled, setEnabled] = useState(configuredValue);
  const [warning, setWarning] = useState<string | null>(null);

  useEffect(() => {
    setEnabled(configuredValue);
    setWarning(null);
  }, [configuredValue]);

  const handleUpdate = async (_name: string, value: boolean) => {
    try {
      const response = await updateAppsettingsConfig({
        application: { enable_fork_playback: value },
      });
      if (response.error?.error) {
        throw new Error(response.error.error);
      }
      if (response.data) {
        setAppSettingsConfig(response.data);
      }
      setEnabled(value);
      setWarning(null);
      onRefresh();
    } catch (error) {
      setWarning(getApiErrorMessage(error, 'Failed to update fork features.'));
      throw error;
    }
  };

  return (
    <div className="settings-box-wrapper">
      <div>
        <p>Enable Enhanced Playback</p>
      </div>
      <ToggleConfig
        name="application.enable_fork_playback"
        value={enabled}
        text="Prepare non-MP4 videos for browser playback and serve media with range support."
        updateCallback={handleUpdate}
      />
      {warning && <p className="settings-error">{warning}</p>}
    </div>
  );
};

export default PlaybackFeatureToggle;
