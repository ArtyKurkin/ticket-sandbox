import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function EscalationArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<radialGradient cx="35%" cy="35%" id={prefix + "-apexSphereGrad"} r="65%">
<stop offset="0%" stopColor="#7dd3fc"></stop>
<stop offset="50%" stopColor="#0284c7"></stop>
<stop offset="1" stopColor="#034d75"></stop>
</radialGradient>
<radialGradient cx="35%" cy="35%" id={prefix + "-subSphereGrad"} r="65%">
<stop offset="0%" stopColor="#cbd5e1"></stop>
<stop offset="60%" stopColor="#64748b"></stop>
<stop offset="1" stopColor="#334155"></stop>
</radialGradient>
</defs>
<path d="M14 34L24 16L34 34" stroke="#475569" strokeLinecap="round" strokeWidth="2.2"></path>
<path d="M14 34H34" stroke="#334155" strokeLinecap="round" strokeWidth="1.8"></path>
<path d="M24 16V34" stroke="#475569" strokeDasharray="2 2" strokeWidth="1.2"></path>
<circle cx="24" cy="16" fill={"url(#" + prefix + "-apexSphereGrad)"} r="5.8" stroke="#38bdf8" strokeOpacity="0.8" strokeWidth="0.8"></circle>
<circle cx="22.2" cy="14.2" fill="#ffffff" fillOpacity="0.75" r="1.4"></circle>
<circle cx="14" cy="34" fill={"url(#" + prefix + "-subSphereGrad)"} r="4.8" stroke="#94a3b8" strokeOpacity="0.5" strokeWidth="0.8"></circle>
<circle cx="12.5" cy="32.5" fill="#ffffff" fillOpacity="0.6" r="1.1"></circle>
<circle cx="34" cy="34" fill={"url(#" + prefix + "-subSphereGrad)"} r="4.8" stroke="#94a3b8" strokeOpacity="0.5" strokeWidth="0.8"></circle>
<circle cx="32.5" cy="32.5" fill="#ffffff" fillOpacity="0.6" r="1.1"></circle>
</svg>);
}
