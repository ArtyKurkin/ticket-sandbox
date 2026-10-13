import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function AuditArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-auditDocGrad04"} x1="10" x2="32" y1="9" y2="37">
<stop stopColor="#334155"></stop>
<stop offset="1" stopColor="#1e293b"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-lensFrameGrad04"} x1="18" x2="38" y1="14" y2="34">
<stop stopColor="#7dd3fc"></stop>
<stop offset="0.6" stopColor="#0284c7"></stop>
<stop offset="1" stopColor="#0369a1"></stop>
</linearGradient>
</defs>
<rect fill={"url(#" + prefix + "-auditDocGrad04)"} height="27" rx="3" stroke="#475569" strokeWidth="0.9" width="22" x="11" y="9.5"></rect>
<path d="M15 15H23M15 19.5H27M15 24H21" stroke="#64748b" strokeLinecap="round" strokeWidth="1.2"></path>
<circle cx="28" cy="24" fill="#0284c7" fillOpacity="0.22" r="9" stroke={"url(#" + prefix + "-lensFrameGrad04)"} strokeWidth="2.2"></circle>
<path d="M23.5 19.5C25 18 28 17.5 30.5 18.2" opacity="0.85" stroke="#ffffff" strokeLinecap="round" strokeWidth="1.2"></path>
<path d="M34.5 30.5L41.5 37.5" stroke="#38bdf8" strokeLinecap="round" strokeWidth="2.8"></path>
</svg>);
}
