function FooterPills(){
  const pill = "rounded-full border border-[var(--grab-edge)]/80 px-4 py-2 text-sm opacity-85 hover:opacity-100";
  return (
    <footer className="mt-3">
      {/* soft blue separator above footer */}
      <div className="h-px w-full mb-6" style={{background:"linear-gradient(90deg,transparent, var(--grab-soft), transparent)"}} />
      <div className="container pb-10">
        <div className="flex items-center justify-center gap-3">
          <button className={pill}>Status</button>
          <button className={pill}>Privacy</button>
          <button className={pill}>Terms</button>
        </div>
        <p className="mt-2 text-center text-sm" style={{color:"var(--grab-muted)"}}>
          © 2025 Grab Logistics • All rights reserved
        </p>
      </div>
    </footer>
  );
}

export default FooterPills;
