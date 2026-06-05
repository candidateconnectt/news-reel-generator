export default function VideoPlayer({ src }: { src: string }) {
  return (
    <video
      src={src}
      controls
      playsInline
      preload="metadata"
      className="w-full aspect-[9/16] bg-black rounded border border-zinc-800"
    />
  );
}
