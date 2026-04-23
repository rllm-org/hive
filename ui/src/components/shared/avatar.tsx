import BoringAvatar from "boring-avatars";

const COLORS = ["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"];

type AvatarSize = "xs" | "sm" | "md" | "lg" | "xl";
type AvatarKind = "agent" | "user";

const SIZE_PX: Record<AvatarSize, number> = {
  xs: 16,
  sm: 24,
  md: 32,
  lg: 36,
  xl: 64,
};

interface AvatarProps {
  /** Stable id used as the seed if `seed` isn't provided. */
  id: string;
  /** Optional explicit seed (recommended: backend-stored avatar_seed). */
  seed?: string | null;
  /** Optional image URL (e.g. GitHub avatar). Takes priority over generated avatar. */
  imageUrl?: string | null;
  /** "agent" → rectangular `beam`. "user" → circular `bauhaus`. */
  kind?: AvatarKind;
  size?: AvatarSize;
  className?: string;
}

export function Avatar({ id, seed, imageUrl, kind = "agent", size = "lg", className = "" }: AvatarProps) {
  const px = SIZE_PX[size];
  const variant = kind === "user" ? "bauhaus" : "beam";
  const square = kind === "agent";
  const rounded = square ? "rounded-[30%]" : "rounded-full";

  return (
    <div
      className={`overflow-hidden shrink-0 ${rounded} ${className}`}
      style={{ width: px, height: px }}
    >
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt={id} width={px} height={px} className="w-full h-full object-cover" />
      ) : (
        <BoringAvatar
          name={seed || id}
          variant={variant}
          size={px}
          square={square}
          colors={COLORS}
        />
      )}
    </div>
  );
}
