/**
 * AudioLanguageSelector – text input for comma-separated language codes.
 *
 * Used by the audio_tracks fork feature to let users specify which audio
 * language tracks to download (e.g. "en, es, ja").
 *
 * Follows the same update/cancel/reset pattern as InputConfig.
 */

import { useState } from 'react';
import LoadingIndicator from './LoadingIndicator';

type AudioLanguageSelectorProps = {
  name: string;
  value: string | null;
  oldValue: string | null | undefined;
  updateCallback: (name: string, value: string | boolean | number | null) => void;
};

const AudioLanguageSelector = ({
  name,
  value,
  oldValue,
  updateCallback,
}: AudioLanguageSelectorProps) => {
  const [localValue, setLocalValue] = useState<string>(value ?? '');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const normalizedOld = oldValue ?? '';
  const hasChanged = localValue !== normalizedOld;

  const handleUpdate = async () => {
    setLoading(true);
    setSuccess(false);
    const submitValue = localValue.trim() === '' ? null : localValue.trim();
    updateCallback(name, submitValue);
    setLoading(false);
    setSuccess(true);
    setTimeout(() => setSuccess(false), 3000);
  };

  return (
    <div>
      <input
        type="text"
        name={name}
        value={localValue}
        placeholder="e.g. en, es, ja"
        onChange={e => setLocalValue(e.target.value)}
      />
      <p className="settings-help">
        Comma-separated language codes (BCP-47). Leave empty to auto-discover all available
        languages.
      </p>
      <div className="button-box">
        {hasChanged && (
          <>
            <button onClick={handleUpdate}>Update</button>
            <button onClick={() => setLocalValue(normalizedOld)}>Cancel</button>
          </>
        )}
        {normalizedOld !== '' && (
          <button
            onClick={() => {
              setLocalValue('');
              updateCallback(name, null);
            }}
          >
            Reset
          </button>
        )}
        {loading && <LoadingIndicator />}
        {success && <span>✅</span>}
      </div>
    </div>
  );
};

export default AudioLanguageSelector;
