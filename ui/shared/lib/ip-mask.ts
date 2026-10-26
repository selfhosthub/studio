// ui/shared/lib/ip-mask.ts

const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
const HEX_GROUP = /^[0-9a-f]{1,4}$/i;

/** Parses dotted IPv4 into four octets, or null when it is not one. */
function parseIpv4(ip: string): number[] | null {
  const match = IPV4.exec(ip);
  if (!match) return null;
  const octets = match.slice(1).map(Number);
  return octets.every((octet) => octet <= 255) ? octets : null;
}

/** Expands IPv6 (compressed, zone id or dotted tail) into eight lowercase groups, or null when it is not one. */
function expandIpv6(ip: string): string[] | null {
  const halves = ip.split('%')[0].split('::');
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(':') : [];
  const tail = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
  const last = tail.length ? tail : head;
  if (last.length && last[last.length - 1].includes('.')) {
    const octets = parseIpv4(last.pop() as string);
    if (!octets) return null;
    last.push(((octets[0] << 8) | octets[1]).toString(16), ((octets[2] << 8) | octets[3]).toString(16));
  }
  const missing = 8 - head.length - tail.length;
  if (halves.length === 1 ? missing !== 0 : missing < 1) return null;
  const groups = [...head, ...Array(halves.length === 2 ? missing : 0).fill('0'), ...tail];
  if (!groups.every((group) => HEX_GROUP.test(group))) return null;
  return groups.map((group) => parseInt(group, 16).toString(16));
}

/** Masks an IP for display: IPv4 keeps three octets, IPv6 keeps three of eight groups, IPv4-mapped IPv6 masks as IPv4. */
export function maskIpAddress(ip: string): string {
  const octets = parseIpv4(ip);
  if (octets) return `${octets.slice(0, 3).join('.')}.x`;
  const groups = expandIpv6(ip);
  if (!groups) return ip;
  if (groups.slice(0, 5).every((group) => group === '0') && groups[5] === 'ffff') {
    const high = parseInt(groups[6], 16);
    const low = parseInt(groups[7], 16);
    return `${high >> 8}.${high & 255}.${low >> 8}.x`;
  }
  return [...groups.slice(0, 3), 'x', 'x', 'x', 'x', 'x'].join(':');
}

/** Copy of audit metadata with ip_address masked; other keys unchanged. */
export function maskAuditMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  const ip = metadata.ip_address;
  if (typeof ip !== 'string') return metadata;
  return { ...metadata, ip_address: maskIpAddress(ip) };
}
