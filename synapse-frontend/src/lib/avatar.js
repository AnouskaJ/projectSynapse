// Deterministic human avatar from randomuser based on a seed (email/id)
export function humanAvatar(seed = "guest"){
  const s = String(seed).toLowerCase();
  let sum = 0;
  for (let i = 0; i < s.length; i++) sum = (sum + s.charCodeAt(i)) % 90;
  const gender = sum % 2 ? "women" : "men";
  const n = (sum % 90) + 1; // 1..90
  return `https://randomuser.me/api/portraits/${gender}/${n}.jpg`;
}
