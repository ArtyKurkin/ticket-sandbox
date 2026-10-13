import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function FinalArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-platStarGrad08"} x1="10" x2="38" y1="8" y2="40">
<stop stopColor="#ffffff"></stop>
<stop offset="0.35" stopColor="#f1f5f9"></stop>
<stop offset="0.75" stopColor="#cbd5e1"></stop>
<stop offset="1" stopColor="#8b5cf6"></stop>
</linearGradient>
</defs>
<ellipse cx="24" cy="24" opacity="0.65" rx="17" ry="8.5" stroke="#a78bfa" strokeDasharray="2 3" strokeWidth="1.1" transform="rotate(-25 24 24)"></ellipse>
<path d="M24 6L27.5 18.5L40 22L27.5 25.5L24 38L20.5 25.5L8 22L20.5 18.5L24 6Z" fill={"url(#" + prefix + "-platStarGrad08)"} stroke="#ede9fe" strokeWidth="1.1"></path>
<circle cx="24" cy="22" fill="#ffffff" filter="drop-shadow(0 0 6px #c4b5fd)" r="2.8"></circle>
</svg>);
}
