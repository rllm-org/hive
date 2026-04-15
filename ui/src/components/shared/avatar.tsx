import { getAgentColor } from "@/lib/agent-colors";

function getInitials(id: string): string {
  return id
    .split("-")
    .filter(Boolean)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);
}

type AvatarSize = "xs" | "sm" | "md" | "lg";

const sizeConfig: Record<AvatarSize, { className: string; gradient: boolean }> = {
  xs: { className: "w-4 h-4 text-[7px]", gradient: false },
  sm: { className: "w-6 h-6 text-[8px]", gradient: false },
  md: { className: "w-8 h-8 text-[10px] shadow-sm", gradient: true },
  lg: { className: "w-9 h-9 text-[10px] shadow-sm", gradient: true },
};

interface AvatarProps {
  id: string;
  size?: AvatarSize;
  className?: string;
}

export function Avatar({ id, size = "lg", className = "" }: AvatarProps) {
  const color = getAgentColor(id);
  const config = sizeConfig[size];
  const bg = config.gradient
    ? `linear-gradient(135deg, ${color}, ${color}dd)`
    : color;

  return (
    <div
      className={`rounded flex items-center justify-center text-white font-bold shrink-0 ${config.className} ${className}`}
      style={config.gradient ? { background: bg } : { backgroundColor: color }}
    >
      {getInitials(id)}
    </div>
  );
}
