// src/lib/firebase.ts
import { initializeApp } from "firebase/app"
import { getAuth } from "firebase/auth"
import { getMessaging } from "firebase/messaging"

// Your web config (public)
const firebaseConfig = {
  apiKey: "AIzaSyDOlod9mcpsqWJdalalPka7CbAhOvHN6Jo",
  authDomain: "synapse-54cfb.firebaseapp.com",
  projectId: "synapse-54cfb",
  storageBucket: "synapse-54cfb.firebasestorage.app",
  messagingSenderId: "844442984824",
  appId: "1:844442984824:web:252a836b759d196a65e88d",
  measurementId: "G-D3NW1C1JXZ",
}

export const app = initializeApp(firebaseConfig)

// Export the pieces other modules expect
export const auth = getAuth(app)
export const messaging = getMessaging(app)

// (Optional) default export for convenience
export default app
