import { VideoStreamType } from '../registry';

const GENERIC_AUDIO_TITLES = new Set([
  'iso media file produced by google inc.',
  'soundhandler',
  'iso media',
]);

const getLanguageLabel = (language?: string | null): string | null => {
  if (!language) {
    return null;
  }

  const raw = language.trim();
  if (!raw) {
    return null;
  }

  const normalized = raw.split(/[-_]/)[0];
  const code = raw.toUpperCase();

  try {
    const DisplayNames = (
      Intl as unknown as {
        DisplayNames?: new (
          locales?: string | string[],
          options?: Intl.DisplayNamesOptions,
        ) => Intl.DisplayNames;
      }
    ).DisplayNames;

    if (DisplayNames) {
      const displayName = new DisplayNames([navigator.language || 'en', 'en'], {
        type: 'language',
      }).of(normalized);

      if (displayName && displayName.toLowerCase() !== normalized.toLowerCase()) {
        return `${code} - ${displayName}`;
      }
    }
  } catch {
    // no-op fallback to raw code
  }

  return code;
};

const getUsefulAudioTitle = (title?: string | null, language?: string | null): string | null => {
  if (!title) {
    return null;
  }

  const cleaned = title.trim();
  if (!cleaned) {
    return null;
  }

  const lower = cleaned.toLowerCase();
  if (GENERIC_AUDIO_TITLES.has(lower)) {
    return null;
  }

  const langRaw = language?.trim().toLowerCase();
  if (langRaw && (lower === langRaw || lower === langRaw.split(/[-_]/)[0])) {
    return null;
  }

  if (/^[a-z]{2,3}$/i.test(cleaned)) {
    return null;
  }

  return cleaned;
};

export const formatAudioTrackStreamLabel = (stream: VideoStreamType): string | null => {
  if (stream.type !== 'audio') {
    return null;
  }

  const parts: string[] = [];
  const languageLabel = getLanguageLabel(stream.language);
  const usefulTitle = getUsefulAudioTitle(stream.title, stream.language);

  if (languageLabel) {
    parts.push(languageLabel);
  }

  if (usefulTitle) {
    parts.push(usefulTitle);
  }

  if (stream.channel_layout) {
    parts.push(stream.channel_layout);
  } else if (stream.channels) {
    parts.push(`${stream.channels}ch`);
  }

  return parts.length > 0 ? parts.join(' | ') : null;
};
