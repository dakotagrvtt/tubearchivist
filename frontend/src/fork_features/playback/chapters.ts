import type { ChapterType } from '../../pages/Home';

const toVttTimestamp = (seconds: number) => {
  const safeSeconds = Math.max(seconds, 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainder = (safeSeconds % 60).toFixed(3).padStart(6, '0');
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${remainder}`;
};

const escapeCueText = (title: string) =>
  title.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export const chaptersToVtt = (chapters: ChapterType[] | undefined) => {
  if (!chapters?.length) return '';

  return [
    'WEBVTT',
    '',
    ...chapters.flatMap((chapter, index) => [
      String(index + 1),
      `${toVttTimestamp(chapter.start)} --> ${toVttTimestamp(chapter.end)}`,
      escapeCueText(chapter.title),
      '',
    ]),
  ].join('\n');
};
