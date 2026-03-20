/**
 * Fork Feature Frontend Registry
 *
 * Each fork feature that adds UI to the settings pages registers a component
 * here.  The core pages import the relevant lists and render each component
 * in a stable slot, keeping all fork-specific JSX out of the upstream files.
 *
 * To add a new feature:
 *  1. Create your section component(s) under src/fork_features/<featureName>/.
 *  2. Import and append to the relevant list below.
 *
 * See FORK_FEATURES.md at the project root for a full walkthrough.
 */

import { ComponentType } from 'react';
import { AppSettingsConfigType } from '../api/loader/loadAppsettingsConfig';
import { ChannelResponseType } from '../api/loader/loadChannelById';

// ---------------------------------------------------------------------------
// Shared prop types consumed by fork-feature section components
// ---------------------------------------------------------------------------

/**
 * Props forwarded to every App Settings section component.
 *
 * The section receives the live config snapshot and a callback that tells the
 * parent page to re-fetch settings after an update.
 */
export type AppSettingsSectionProps = {
  appSettingsConfig: AppSettingsConfigType;
  onRefresh: () => void;
};

/**
 * Props forwarded to every Channel Settings section component.
 *
 * Includes the full channel response (for overwrite data) plus the global
 * config (so features can show "using global: …" helper text).
 */
export type ChannelSettingsSectionProps = {
  channel: ChannelResponseType;
  appSettingsConfig: AppSettingsConfigType;
  onRefresh: () => void;
};

// ---------------------------------------------------------------------------
// Registry lists — import your feature section components here
// ---------------------------------------------------------------------------

import AudioTracksAppSection from './audioTracks/ApplicationSettingsSection';
import AudioTracksChannelSection from './audioTracks/ChannelSettingsSection';

/**
 * Fork-feature sections rendered inside the Download Format settings box
 * on the Application Settings page.
 */
export const APP_SETTINGS_SECTIONS: ComponentType<AppSettingsSectionProps>[] = [
  AudioTracksAppSection,
];

/**
 * Fork-feature sections rendered inside the Channel Customization box
 * on the Channel About page.
 */
export const CHANNEL_SETTINGS_SECTIONS: ComponentType<ChannelSettingsSectionProps>[] = [
  AudioTracksChannelSection,
];
