import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function SandboxArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 52 52">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-monChassis02"} x1="6" x2="46" y1="8" y2="40">
<stop stopColor="#38bdf8"></stop>
<stop offset="0.6" stopColor="#0284c7"></stop>
<stop offset="1" stopColor="#0369a1"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-monScreen02"} x1="10" x2="42" y1="12" y2="34">
<stop stopColor="#061222"></stop>
<stop offset="1" stopColor="#020813"></stop>
</linearGradient>
</defs>
<ellipse cx="26" cy="43.5" fill="#0369a1" opacity="0.7" rx="10" ry="3"></ellipse>
<path d="M23 35H29L30.5 42.5H21.5L23 35Z" fill="#0284c7"></path>
<rect fill={"url(#" + prefix + "-monChassis02)"} height="26" rx="4.5" stroke="#7dd3fc" strokeOpacity="0.8" strokeWidth="1" width="38" x="7" y="9.5"></rect>
<rect fill={"url(#" + prefix + "-monScreen02)"} height="20" rx="3" width="32" x="10" y="12.5"></rect>
<text fill="#38bdf8" fontFamily="'JetBrains Mono', monospace" fontSize="8.5" fontWeight="700" x="12.5" y="21">&gt;_</text>
<rect fill="#7dd3fc" height="2" opacity="0.9" rx="1" width="13" x="25" y="17.5"></rect>
<rect fill="#38bdf8" height="2" opacity="0.8" rx="1" width="22" x="13" y="25"></rect>
<rect fill="#0284c7" height="2" opacity="0.9" rx="1" width="15" x="13" y="28.5"></rect>
<circle cx="26" cy="33.5" fill="#38bdf8" r="0.9"></circle>
</svg>);
}
