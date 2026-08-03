import APIClient from '../../functions/APIClient';
import { AppSettingsConfigType } from '../loader/loadAppsettingsConfig';

export type AppSettingsConfigUpdate = {
  subscriptions?: Partial<AppSettingsConfigType['subscriptions']>;
  downloads?: Partial<AppSettingsConfigType['downloads']>;
  application?: Partial<AppSettingsConfigType['application']>;
};

const updateAppsettingsConfig = async (updatedConfig: AppSettingsConfigUpdate) => {
  return APIClient<AppSettingsConfigType>('/api/appsettings/config/', {
    method: 'POST',
    body: updatedConfig as Record<string, unknown>,
  });
};

export default updateAppsettingsConfig;
