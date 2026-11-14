/** Country calling codes offered at sign-up, most likely first. */
export const countryCodes = [
  { code: "1", label: "US / Canada" },
  { code: "44", label: "United Kingdom" },
  { code: "61", label: "Australia" },
  { code: "64", label: "New Zealand" },
  { code: "353", label: "Ireland" },
  { code: "91", label: "India" },
  { code: "65", label: "Singapore" },
  { code: "852", label: "Hong Kong" },
  { code: "86", label: "China" },
  { code: "82", label: "South Korea" },
  { code: "81", label: "Japan" },
  { code: "49", label: "Germany" },
  { code: "33", label: "France" },
  { code: "34", label: "Spain" },
  { code: "52", label: "Mexico" },
  { code: "55", label: "Brazil" },
] as const;

/**
 * The teacher's mobile number for Photon alerts, as E.164 (`+15551234567`),
 * from a country calling code and the number as typed; null when it can't be one.
 */
export function normalizeAlertPhone(
  countryCode: string,
  number: string,
): string | null {
  const code = countryCode.replace(/\D/g, "");
  let digits = number.replace(/\D/g, "");
  // A national trunk 0 (as in UK 07946…) is dropped after the country code.
  if (code !== "1" && digits.startsWith("0")) digits = digits.slice(1);
  // US and Canada numbers are always ten digits after +1.
  if (code === "1" && digits.length === 11 && digits.startsWith("1"))
    digits = digits.slice(1);
  if (!code || (code === "1" && digits.length !== 10)) return null;
  const total = code.length + digits.length;
  return digits.length >= 6 && total >= 8 && total <= 15 ? `+${code}${digits}` : null;
}
