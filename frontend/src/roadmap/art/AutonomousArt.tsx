import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function AutonomousArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-boltMetallic07"} x1="14" x2="34" y1="8" y2="40">
<stop stopColor="#93c5fd"></stop>
<stop offset="0.4" stopColor="#38bdf8"></stop>
<stop offset="1" stopColor="#0284c7"></stop>
</linearGradient>
</defs>
<circle cx="24" cy="24" r="16" stroke="#334155" strokeDasharray="3 3" strokeWidth="1.1"></circle>
<path d="M26 8L14 24H24L22 40L34 24H24L26 8Z" fill={"url(#" + prefix + "-boltMetallic07)"} stroke="#bae6fd" strokeLinejoin="round" strokeWidth="1.1"></path>
<path d="M25 10L16 23H24L23 35" opacity="0.6" stroke="#ffffff" strokeLinecap="round" strokeWidth="1.2"></path>
</svg>);
}
