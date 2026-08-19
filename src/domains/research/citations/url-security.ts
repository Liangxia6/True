import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

function privateIpv4(address: string): boolean {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part))) return true;
  const [a, b] = parts as [number, number, number, number];
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    a >= 224
  );
}

function privateIpv6(address: string): boolean {
  const normalized = address.toLowerCase();
  return normalized === "::" || normalized === "::1" || normalized.startsWith("fc") ||
    normalized.startsWith("fd") || normalized.startsWith("fe8") ||
    normalized.startsWith("fe9") || normalized.startsWith("fea") || normalized.startsWith("feb");
}

export function isPrivateAddress(address: string): boolean {
  const family = isIP(address);
  return family === 4 ? privateIpv4(address) : family === 6 ? privateIpv6(address) : true;
}

export async function assertPublicHttpUrl(value: string): Promise<URL> {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error("EVIDENCE_UNSAFE_SCHEME");
  if (url.username || url.password) throw new Error("EVIDENCE_URL_CREDENTIALS_FORBIDDEN");
  const hostname = url.hostname.replace(/^\[|\]$/g, "");
  if (hostname === "localhost" || hostname.endsWith(".localhost")) throw new Error("EVIDENCE_PRIVATE_HOST");
  if (isIP(hostname)) {
    if (isPrivateAddress(hostname)) throw new Error("EVIDENCE_PRIVATE_HOST");
    return url;
  }
  const addresses = await lookup(hostname, { all: true, verbatim: true });
  if (!addresses.length || addresses.some((entry) => isPrivateAddress(entry.address))) {
    throw new Error("EVIDENCE_PRIVATE_HOST");
  }
  return url;
}
