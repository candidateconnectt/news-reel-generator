/** Compact inline video player. Used in the Live panel and inside History cards. */
export default function VideoPlayer({ src, muted = true }: { src: string; muted?: boolean }) {
  return (
    <video
      src={src}
      controls
      playsInline
      muted={muted}
      preload="metadata"
      className="w-full aspect-[9/16] bg-black rounded-lg"
    />
  );
}
