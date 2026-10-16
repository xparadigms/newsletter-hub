import { Glyph } from "@/components/SectionGlyph";
import type { SectionKey } from "@/lib/types";

/** A section's round avatar. The ring is Instagram's gradient while there is
 *  something unread, a thin grey line once there is not. */
export default function SectionAvatar({
  section,
  size = 64,
  unseen = false,
}: {
  section: SectionKey;
  size?: number;
  unseen?: boolean;
}) {
  return (
    <span
      className="avatar"
      data-section={section}
      data-unseen={unseen}
      style={{ "--avatar": `${size}px` } as React.CSSProperties}
    >
      <span className="avatar__face">
        <Glyph name={section} active={false} size={Math.round(size * 0.42)} />
      </span>
    </span>
  );
}
