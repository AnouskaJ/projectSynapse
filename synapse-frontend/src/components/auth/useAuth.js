import { useContext } from "react";
import AuthProvider from "./AuthProvider.jsx";

// tiny helper so you can `import useAuth from ".../useAuth"`
export { useAuth as default } from "./AuthProvider.jsx";
export { AuthProvider };
