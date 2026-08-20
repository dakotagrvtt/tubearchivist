import { useMemo } from 'react';
import type { ChapterType } from '../../pages/Home';
import { chaptersToVtt } from './chapters';

const useChapterTrack = (chapters: ChapterType[] | undefined) => {
  const vtt = useMemo(() => chaptersToVtt(chapters), [chapters]);

  return useMemo(() => {
    if (!vtt) return undefined;
    return `data:text/vtt;charset=utf-8,${encodeURIComponent(vtt)}`;
  }, [vtt]);
};

export default useChapterTrack;
