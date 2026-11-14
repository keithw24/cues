"use client";

import CuesBlob from "@/components/cues-blob";

export default function LoginCompanion({
  busy = false,
  privacy = false,
}: {
  busy?: boolean;
  privacy?: boolean;
}) {
  return (
    <div className="login-companion">
      <CuesBlob size={132} busy={busy} privacy={privacy} />
    </div>
  );
}
