import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function SyncArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><linearGradient id={prefix + "-s-bevel2"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#f8fafc"></stop>
<stop offset="45%" stopColor="#94a3b8"></stop>
<stop offset="75%" stopColor="#334155"></stop>
<stop offset="100%" stopColor="#0f172a"></stop>
</linearGradient><radialGradient cx="45%" cy="35%" id={prefix + "-s-core2"} r="65%">
<stop offset="0%" stopColor="#1e293b"></stop>
<stop offset="60%" stopColor="#0f172a"></stop>
<stop offset="100%" stopColor="#020617"></stop>
</radialGradient><radialGradient cx="35%" cy="25%" id={prefix + "-s-grad-rim2"} r="75%">
<stop offset="0%" stopColor="#ffffff"></stop>
<stop offset="25%" stopColor="#e2e8f0"></stop>
<stop offset="55%" stopColor="#94a3b8"></stop>
<stop offset="85%" stopColor="#475569"></stop>
<stop offset="100%" stopColor="#1e293b"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-grad-rim2)"} r="92" stroke="#ffffff" strokeOpacity="0.4" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#1e293b" strokeDasharray="4 2.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-bevel2)"} r="82" stroke="#ffffff" strokeOpacity="0.2" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#0f172a" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-core2)"} r="74"></circle>

<g transform="translate(100, 100)">
<circle cx="-12" cy="-6" fill="none" r="24" stroke="#94a3b8" strokeDasharray="6 4" strokeWidth="4"></circle>
<circle cx="14" cy="10" fill="none" r="18" stroke="#cbd5e1" strokeDasharray="5 3" strokeWidth="3"></circle>
<circle cx="-12" cy="-6" fill="#64748b" r="7" stroke="#ffffff" strokeWidth="1.5"></circle>
<circle cx="14" cy="10" fill="#94a3b8" r="5" stroke="#ffffff" strokeWidth="1.5"></circle>
</g>
</svg>);
}
