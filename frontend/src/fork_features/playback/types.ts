import type { VideoNavResponseType } from '../../api/loader/loadVideoNav';

export type RepeatMode = 'off' | 'one' | 'all';

export type PlaybackPlaylistContext = {
  playlistId: string;
  playlistName: string;
  currentVideoId: string;
  entries: VideoNavResponseType['playlist_entries'];
  previous?: VideoNavResponseType['playlist_previous'] | null;
  next?: VideoNavResponseType['playlist_next'] | null;
  autoplay: boolean;
  onAutoplayChange: (enabled: boolean) => void;
  onNavigate: (videoId: string) => void;
};

export type PlaybackTarget = {
  youtube_id: string;
  title: string;
  thumbnail?: string;
};
