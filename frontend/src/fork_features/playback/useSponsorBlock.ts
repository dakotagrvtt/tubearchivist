import { useCallback, useRef, useState } from 'react';
import type { SponsorBlockSegmentType, SponsorBlockType } from '../../pages/Video';
import type { SponsorSegmentsSkippedType } from '../../components/VideoPlayer';

const useSponsorBlock = (sponsorBlock?: SponsorBlockType) => {
  const [skippedSegments, setSkippedSegments] = useState<SponsorSegmentsSkippedType>({});
  const lastSkippedId = useRef<string | null>(null);

  const onTimeUpdate = useCallback(
    (currentTime: number, seek: (time: number) => void) => {
      sponsorBlock?.segments?.forEach((segment: SponsorBlockSegmentType) => {
        const [from, to] = segment.segment;
        if (
          segment.actionType === 'skip' &&
          currentTime >= from &&
          currentTime <= from + 0.3 &&
          lastSkippedId.current !== segment.UUID
        ) {
          seek(to);
          lastSkippedId.current = segment.UUID;
          setSkippedSegments(segments => ({
            ...segments,
            [segment.UUID]: { from, to },
          }));
        }

        if (
          lastSkippedId.current === segment.UUID &&
          (currentTime > to + 10 || currentTime < from)
        ) {
          lastSkippedId.current = null;
          setSkippedSegments(segments => ({
            ...segments,
            [segment.UUID]: { from: 0, to: 0 },
          }));
        }
      });
    },
    [sponsorBlock],
  );

  const reset = useCallback(() => {
    lastSkippedId.current = null;
    setSkippedSegments(segments =>
      Object.fromEntries(Object.keys(segments).map(uuid => [uuid, { from: 0, to: 0 }])),
    );
  }, []);

  return { skippedSegments, onTimeUpdate, reset };
};

export default useSponsorBlock;
