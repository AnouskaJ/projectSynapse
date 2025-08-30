// src/lib/auth.js
import { auth } from "./firebase"

// re-export or add helpers here as needed
export { auth }
export const getIdToken = async () => {
  const user = auth.currentUser;
  if (user) {
    return await user.getIdToken();
  }
  return null;
};