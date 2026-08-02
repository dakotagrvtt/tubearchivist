/**
 * AudioLanguageSelector – text input for comma-separated language codes.
 *
 * Kept inside the audioTracks fork feature so the custom UI stays isolated
 * from upstream shared components.
 */

import { useEffect, useState } from 'react';
import LoadingIndicator from '../../components/LoadingIndicator';

type AudioLanguageSelectorProps = {
  name: string;
  value: string | null;
  oldValue: string | null | undefined;
  updateCallback: (
    name: string,
    value: string | boolean | number | null,
  ) => void | Promise<void>;
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

  useEffect(() => {
    setLocalValue(value ?? '');
  }, [value]);

  const normalizedOld = oldValue ?? '';
  const hasChanged = localValue !== normalizedOld;

  const handleUpdate = async () => {
    setLoading(true);
    setSuccess(false);
    const submitValue = localValue.trim() === '' ? null : localValue.trim();
    try {
      await updateCallback(name, submitValue);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch {
      // The parent section renders the API error.
    } finally {
      setLoading(false);
    }
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
            onClick={async () => {
              setLocalValue('');
              try {
                await updateCallback(name, null);
              } catch {
                // The parent section renders the API error.
              }
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
