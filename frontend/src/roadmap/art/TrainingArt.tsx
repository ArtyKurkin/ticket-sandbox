import { useId } from "react";

// Original pseudo-3D SVG from the Roadmap Stitch export.
export function TrainingArt() {
 const prefix = useId();
 return (<svg className="rm-art" aria-hidden="true" fill="none" viewBox="0 0 48 48">
<defs>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-bookCoverGrad01"} x1="8" x2="40" y1="14" y2="38">
<stop stopColor="#059669"></stop>
<stop offset="0.6" stopColor="#047857"></stop>
<stop offset="1" stopColor="#064e3b"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-bookLeftPage01"} x1="10" x2="24" y1="14" y2="34">
<stop stopColor="#a7f3d0"></stop>
<stop offset="0.4" stopColor="#34d399"></stop>
<stop offset="1" stopColor="#059669"></stop>
</linearGradient>
<linearGradient gradientUnits="userSpaceOnUse" id={prefix + "-bookRightPage01"} x1="24" x2="38" y1="14" y2="34">
<stop stopColor="#6ee7b7"></stop>
<stop offset="0.5" stopColor="#10b981"></stop>
<stop offset="1" stopColor="#047857"></stop>
</linearGradient>
</defs>
<path d="M8 35C14 32.5 20 33 24 35C28 33 34 32.5 40 35V37.5C34 35 28 35.5 24 37.5C20 35.5 14 35 8 37.5V35Z" fill="#022c22" opacity="0.6"></path>
<path d="M9 33.5C14.5 31 20 31.5 24 33.8C28 31.5 33.5 31 39 33.5V17.5C33.5 15 28 15.5 24 17.8C20 15.5 14.5 15 9 17.5V33.5Z" fill={"url(#" + prefix + "-bookCoverGrad01)"} stroke="#10b981" strokeOpacity="0.3" strokeWidth="0.8"></path>
<path d="M10 16.5C15 14 20 14.5 23.5 16.8V32.5C20 30.2 15 29.8 10 32V16.5Z" fill={"url(#" + prefix + "-bookLeftPage01)"}></path>
<path d="M13 20H19.5M13 24H18.5" stroke="#064e3b" strokeLinecap="round" strokeWidth="1.2"></path>
<path d="M38 16.5C33 14 28 14.5 24.5 16.8V32.5C28 30.2 33 29.8 38 32V16.5Z" fill={"url(#" + prefix + "-bookRightPage01)"}></path>
<path d="M28.5 20H35M28.5 24H33" stroke="#064e3b" strokeLinecap="round" strokeWidth="1.2"></path>
<path d="M24 17.8V33.8" stroke="#d1fae5" strokeLinecap="round" strokeWidth="1"></path>
</svg>);
}
