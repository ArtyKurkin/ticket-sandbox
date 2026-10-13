import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function ArchitectureArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200">
<defs>
<radialGradient cx="35%" cy="25%" id={prefix + "-s-grad-rim2"} r="75%">
<stop offset="0%" stopColor="#ffffff"></stop>
<stop offset="25%" stopColor="#e2e8f0"></stop>
<stop offset="55%" stopColor="#94a3b8"></stop>
<stop offset="85%" stopColor="#475569"></stop>
<stop offset="100%" stopColor="#1e293b"></stop>
</radialGradient>
<linearGradient id={prefix + "-s-bevel2"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#f8fafc"></stop>
<stop offset="45%" stopColor="#94a3b8"></stop>
<stop offset="75%" stopColor="#334155"></stop>
<stop offset="100%" stopColor="#0f172a"></stop>
</linearGradient>
<radialGradient cx="45%" cy="35%" id={prefix + "-s-core2"} r="65%">
<stop offset="0%" stopColor="#1e293b"></stop>
<stop offset="60%" stopColor="#0f172a"></stop>
<stop offset="100%" stopColor="#020617"></stop>
</radialGradient>
<filter height="140%" id={prefix + "-s-glow2"} width="140%" x="-20%" y="-20%">
<feGaussianBlur result="glow" stdDeviation="3"></feGaussianBlur>
<feComposite in="SourceGraphic" in2="glow" operator="over"></feComposite>
</filter>
</defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-grad-rim2)"} r="92" stroke="#ffffff" strokeOpacity="0.6" strokeWidth="1.5"></circle>

<circle cx="100" cy="100" r="87" stroke="#1e293b" strokeDasharray="4 2.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-bevel2)"} r="82" stroke="#ffffff" strokeOpacity="0.3" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#0f172a" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-core2)"} r="74"></circle>
<path d="M 40,75 A 72 72 0 0 1 160,75" fill="none" stroke="#ffffff" strokeOpacity="0.4" strokeWidth="2"></path>

<g filter={"url(#" + prefix + "-s-glow2)"} transform="translate(100, 100)">

<path d="M0 -36 L32 -18 L32 18 L0 36 L-32 18 L-32 -18 Z" fill="#050811" transform="translate(0, 3)"></path>

<path d="M0 -36 L32 -18 L0 0 L-32 -18 Z" fill="#ffffff" stroke="#94a3b8" strokeWidth="1"></path>

<path d="M32 -18 L32 18 L0 36 L0 0 Z" fill="#94a3b8" stroke="#475569" strokeWidth="1"></path>

<path d="M-32 -18 L0 0 L0 36 L-32 18 Z" fill="#475569" stroke="#1e293b" strokeWidth="1"></path>

<circle cx="0" cy="0" fill="#38bdf8" fillOpacity="0.9" r="10" stroke="#ffffff" strokeWidth="1.5"></circle>
<circle cx="0" cy="0" fill="#ffffff" r="4"></circle>
</g>
</svg>);
}
