type ToggleConfigProps = {
  name: string;
  value: boolean;
  text?: string;
  helperText?: string;
  disabled?: boolean;
  updateCallback: (name: string, value: boolean) => void | Promise<void>;
  resetCallback?: (arg0: boolean) => void | Promise<void>;
  onValue?: boolean | string;
  offValue?: boolean | string;
};

const ToggleConfig = ({
  name,
  value,
  text,
  helperText,
  disabled = false,
  updateCallback,
  resetCallback = undefined,
}: ToggleConfigProps) => {
  return (
    <div className="toggle">
      {text && <p>{text}</p>}
      {helperText && <p className="settings-help-text">{helperText}</p>}
      <div className="toggleBox">
        <input
          name={name}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={event => {
            if (disabled) {
              return;
            }
            Promise.resolve()
              .then(() => updateCallback(name, event.target.checked))
              .catch(() => {
                // The callback owns the visible API error.
              });
          }}
        />

        {!value && (
          <label htmlFor="" className="ofbtn">
            Off
          </label>
        )}

        {value && (
          <label htmlFor="" className="onbtn">
            On
          </label>
        )}
      </div>

      {resetCallback !== undefined && (
        <button
          onClick={() => {
            Promise.resolve()
              .then(() => resetCallback(false))
              .catch(() => {
                // The callback owns the visible API error.
              });
          }}
        >
          Reset
        </button>
      )}
    </div>
  );
};

export default ToggleConfig;
