import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function OptionalArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-dialogBodyGrad06"} x1="10" x2="38" y1="10" y2="38">
<stop stopColor="#334155"></stop>
<stop offset="0.6" stopColor="#1e293b"></stop>
<stop offset="1" stopColor="#0f172a"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-badgeCyanGrad06"} x1="22" x2="38" y1="20" y2="36">
<stop stopColor="#38bdf8"></stop>
<stop offset="1" stopColor="#0284c7"></stop>
</linearGradient>
</defs>
<path d="M10 14C10 11.7909 11.7909 10 14 10H34C36.2091 10 38 11.7909 38 14V28C38 30.2091 36.2091 32 34 32H24L17 38V32H14C11.7909 32 10 30.2091 10 28V14Z" fill={"url(#" + prefix + "-dialogBodyGrad06)"} stroke="#475569" strokeWidth="1"></path>
<rect fill="#64748b" height="2" opacity="0.8" rx="1" width="14" x="15" y="16"></rect>
<rect fill="#475569" height="2" opacity="0.8" rx="1" width="10" x="15" y="21"></rect>
<circle cx="31" cy="27" fill={"url(#" + prefix + "-badgeCyanGrad06)"} r="7" stroke="#7dd3fc" strokeWidth="1"></circle>
<path d="M28 27L30.2 29.2L34.5 24.8" stroke="#ffffff" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6"></path>
</svg>);
}
