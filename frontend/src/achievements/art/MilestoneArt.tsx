import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function MilestoneArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><linearGradient id={prefix + "-b-bevel1"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#fed7aa"></stop>
<stop offset="30%" stopColor="#d97706"></stop>
<stop offset="70%" stopColor="#78350f"></stop>
<stop offset="100%" stopColor="#2a0f02"></stop>
</linearGradient><radialGradient cx="42%" cy="32%" id={prefix + "-b-core1"} r="65%">
<stop offset="0%" stopColor="#552206"></stop>
<stop offset="60%" stopColor="#270e03"></stop>
<stop offset="100%" stopColor="#140601"></stop>
</radialGradient><filter height="140%" id={prefix + "-b-glow1"} width="140%" x="-20%" y="-20%">
<feGaussianBlur result="glow" stdDeviation="3"></feGaussianBlur>
<feComposite in="SourceGraphic" in2="glow" operator="over"></feComposite>
</filter><radialGradient cx="38%" cy="28%" id={prefix + "-b-grad-rim1"} r="72%">
<stop offset="0%" stopColor="#fef08a"></stop>
<stop offset="18%" stopColor="#f59e0b"></stop>
<stop offset="50%" stopColor="#b45309"></stop>
<stop offset="85%" stopColor="#78350f"></stop>
<stop offset="100%" stopColor="#451a03"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-b-grad-rim1)"} r="92" stroke="#fed7aa" strokeOpacity="0.4" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#451a03" strokeDasharray="3 3.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-b-bevel1)"} r="82" stroke="#fef3c7" strokeOpacity="0.25" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#2a0f02" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-b-core1)"} r="74"></circle>
<path d="M 40,75 A 72 72 0 0 1 160,75" fill="none" stroke="#fef08a" strokeOpacity="0.28" strokeWidth="2"></path>

<g filter={"url(#" + prefix + "-b-glow1)"} transform="translate(100, 100)">

<path d="M-15,-32 L15,-32 L32,-15 L32,15 L15,32 L-15,32 L-32,15 L-32,-15 Z" fill="#b45309" stroke="#fef08a" strokeWidth="1.5"></path>
<path d="M-11,-24 L11,-24 L24,-11 L24,11 L11,24 L-11,24 L-24,11 L-24,-11 Z" fill="#78350f" stroke="#fed7aa" strokeWidth="1"></path>

<path d="M-7,-7 A 7 7 0 1 1 7,-7 L5,14 L-5,14 Z" fill="#fef08a"></path>
<circle cx="0" cy="-6" fill="#451a03" r="3"></circle>
</g>
</svg>);
}
