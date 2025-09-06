import { Link, NavLink } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";

const pill =
  "rounded-full border border-[var(--grab-edge)]/80 px-4 py-2 text-sm hover:bg-white/5 transition";

function HeaderNav() {
  return (
    <>
      <header className="sticky top-0 z-10 bg-[var(--grab-bg)]/75 backdrop-blur">
        <div className="container flex items-center justify-between py-4">
          <Link to="/" className="flex items-center gap-2 font-semibold text-[var(--grab-accent)]">
            <BrandLogo />
          </Link>
          <nav className="flex items-center gap-3">
            <NavLink to="/" className={({isActive}) => `${pill} ${isActive ? "opacity-100" : "opacity-80"}`}>
              Home
            </NavLink>
            <a className={pill} href="#" onClick={(e)=>e.preventDefault()}>Support</a>
          </nav>
        </div>
        {/* soft blue separator under navbar */}
        <div className="h-px w-full" style={{background:"linear-gradient(90deg,transparent, var(--grab-soft), transparent)"}} />
      </header>
    </>
  );
}

export default HeaderNav;
