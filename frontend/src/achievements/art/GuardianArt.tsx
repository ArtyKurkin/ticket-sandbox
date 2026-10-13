import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function GuardianArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><filter height="140%" id={prefix + "-b-glow1"} width="140%" x="-20%" y="-20%">
<feGaussianBlur result="glow" stdDeviation="3"></feGaussianBlur>
<feComposite in="SourceGraphic" in2="glow" operator="over"></feComposite>
</filter><linearGradient id={prefix + "-g-bevel3"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#fef9c3"></stop>
<stop offset="35%" stopColor="#ca8a04"></stop>
<stop offset="75%" stopColor="#713f12"></stop>
<stop offset="100%" stopColor="#241002"></stop>
</linearGradient><radialGradient cx="45%" cy="30%" id={prefix + "-g-core3"} r="65%">
<stop offset="0%" stopColor="#3d1e05"></stop>
<stop offset="65%" stopColor="#1e0c02"></stop>
<stop offset="100%" stopColor="#0a0401"></stop>
</radialGradient><radialGradient cx="35%" cy="25%" id={prefix + "-g-grad-rim3"} r="75%">
<stop offset="0%" stopColor="#fef08a"></stop>
<stop offset="25%" stopColor="#eab308"></stop>
<stop offset="60%" stopColor="#a16207"></stop>
<stop offset="85%" stopColor="#713f12"></stop>
<stop offset="100%" stopColor="#3b1d03"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-grad-rim3)"} r="92" stroke="#fef08a" strokeOpacity="0.6" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#3b1d03" strokeDasharray="3 3.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-bevel3)"} r="82" stroke="#fef08a" strokeOpacity="0.3" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#241002" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-core3)"} r="74"></circle>
<path d="M 40,75 A 72 72 0 0 1 160,75" fill="none" stroke="#fef08a" strokeOpacity="0.4" strokeWidth="2"></path>

<g filter={"url(#" + prefix + "-b-glow1)"} transform="translate(100, 100)">

<path d="M-36,-16 C-24,-30 -8,-24 0,-14 C8,-24 24,-30 36,-16 C38,0 20,24 0,38 C-20,24 -38,0 -36,-16 Z" fill={"url(#" + prefix + "-g-grad-rim3)"} stroke="#fef9c3" strokeWidth="1.5"></path>

<path d="M-22,-8 C-14,-18 -4,-14 0,-8 C4,-14 14,-18 22,-8 C24,4 12,18 0,28 C-12,18 -24,4 -22,-8 Z" fill="#713f12" stroke="#fef08a" strokeWidth="1"></path>

<circle cx="0" cy="6" fill="#fef08a" r="8"></circle>
<circle cx="0" cy="6" fill="#a16207" r="4"></circle>
</g>
</svg>);
}
