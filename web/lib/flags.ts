import registry from "../../flags.json" with { type: "json" };

/** Resolve on the server; never forward the server environment to the browser. */
export function isEnabled(
  name: string,
  env: Record<string, string | undefined> = process.env,
): boolean {
  if (!Object.hasOwn(registry, name))
    throw new Error(`Unknown feature flag: ${name}`);
  const key = `CUES_FLAG_${name.toUpperCase().replaceAll(".", "_")}`;
  const value = env[key] ?? env[`NEXT_PUBLIC_${key}`];
  if (value === undefined)
    return registry[name as keyof typeof registry].default;
  if (value === "1" || value === "true") return true;
  if (value === "0" || value === "false") return false;
  throw new Error(`Invalid value for ${key}; use 1, true, 0 or false.`);
}
