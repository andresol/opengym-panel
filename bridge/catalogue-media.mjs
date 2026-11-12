/** Keep the installed ESP32 jpg/gif transport independent of upstream WebP/MP4. */
export function mediaAsset(kind, exercise) {
  if (!exercise || !/^[0-9]+$/.test(exercise.id)) return null;
  if (kind === 'img' && exercise.img) return `/media/img/v140-${exercise.id}.jpg`;
  if (kind === 'gif' && exercise.gif) return `/media/gif/v140-${exercise.id}.gif`;
  return null;
}
