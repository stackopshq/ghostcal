// Side-by-side layout for timed events that overlap in one day column, as Google Calendar and
// Fantastical do: overlapping events share the column width instead of being drawn on top of
// each other. Pure, so the grid only has to turn lanes into percentages.

export type Lane = { lane: number; lanes: number };

/**
 * Assigns each interval a lane (0-based) and the lane count of its overlap cluster.
 *
 * A cluster is a run of intervals linked by overlap, transitively: if A overlaps B and B
 * overlaps C, all three share one lane count even when A and C don't touch, so widths stay
 * aligned within the cluster. Each interval takes the first lane free at its start. Touching
 * intervals (one ends exactly when the next starts) do not overlap.
 *
 * Returns one entry per input, in input order.
 */
export function layoutLanes(intervals: { start: number; end: number }[]): Lane[] {
  const order = intervals
    .map((iv, index) => ({ ...iv, index }))
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const result: Lane[] = new Array(intervals.length);
  let cluster: number[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -Infinity;

  const closeCluster = () => {
    for (const index of cluster) result[index].lanes = laneEnds.length;
    cluster = [];
    laneEnds = [];
  };

  for (const iv of order) {
    if (iv.start >= clusterEnd) closeCluster();
    let lane = laneEnds.findIndex((end) => end <= iv.start);
    if (lane === -1) lane = laneEnds.push(iv.end) - 1;
    else laneEnds[lane] = iv.end;
    result[iv.index] = { lane, lanes: 0 };
    cluster.push(iv.index);
    clusterEnd = Math.max(clusterEnd, iv.end);
  }
  closeCluster();
  return result;
}
