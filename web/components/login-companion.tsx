"use client";

import CuesBlob from "@/components/cues-blob";

export default function LoginCompanion({
  size = 132,
  busy = false,
  privacy = false,
}: {
  size?: number;
  busy?: boolean;
  privacy?: boolean;
}) {
  return (
    <div className="login-companion" style={{ width: size, height: size }}>
      <CuesBlob size={size} busy={busy} privacy={privacy} />
    </div>
  );
}
