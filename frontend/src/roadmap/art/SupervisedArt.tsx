import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function SupervisedArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-shieldFacetL05"} x1="14" x2="24" y1="14" y2="38">
<stop stopColor="#38bdf8"></stop>
<stop offset="1" stopColor="#0284c7"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-shieldFacetR05"} x1="24" x2="34" y1="14" y2="38">
<stop stopColor="#0284c7"></stop>
<stop offset="1" stopColor="#0369a1"></stop>
</linearGradient>
</defs>
<rect fill="#1e293b" height="30" rx="3" stroke="#334155" strokeWidth="1" width="28" x="10" y="9"></rect>
<path d="M15 15H25M15 19H22" stroke="#475569" strokeLinecap="round" strokeWidth="1.2"></path>
<path d="M24 14L14 18V26C14 32.5 18.5 36.5 24 38V14Z" fill={"url(#" + prefix + "-shieldFacetL05)"} stroke="#7dd3fc" strokeWidth="1"></path>
<path d="M24 14L34 18V26C34 32.5 29.5 36.5 24 38V14Z" fill={"url(#" + prefix + "-shieldFacetR05)"} stroke="#38bdf8" strokeWidth="1"></path>
<path d="M19 26L22.5 29.5L29 23" stroke="#ffffff" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path>
</svg>);
}
