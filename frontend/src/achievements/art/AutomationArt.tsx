import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function AutomationArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200">
<defs>
<radialGradient cx="35%" cy="25%" id={prefix + "-g-grad-rim3"} r="75%">
<stop offset="0%" stopColor="#fef08a"></stop>
<stop offset="25%" stopColor="#eab308"></stop>
<stop offset="60%" stopColor="#a16207"></stop>
<stop offset="85%" stopColor="#713f12"></stop>
<stop offset="100%" stopColor="#3b1d03"></stop>
</radialGradient>
<linearGradient id={prefix + "-g-bevel3"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#fef9c3"></stop>
<stop offset="35%" stopColor="#ca8a04"></stop>
<stop offset="75%" stopColor="#713f12"></stop>
<stop offset="100%" stopColor="#241002"></stop>
</linearGradient>
<radialGradient cx="45%" cy="30%" id={prefix + "-g-core3"} r="65%">
<stop offset="0%" stopColor="#3d1e05"></stop>
<stop offset="65%" stopColor="#1e0c02"></stop>
<stop offset="100%" stopColor="#0a0401"></stop>
</radialGradient>
</defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-grad-rim3)"} r="92" stroke="#fef08a" strokeOpacity="0.3" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#3b1d03" strokeDasharray="3 3.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-bevel3)"} r="82" stroke="#fef08a" strokeOpacity="0.2" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#241002" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-core3)"} r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill={"url(#" + prefix + "-g-grad-rim3)"} points="0,-36 25,-12 36,0 25,12 0,36 -25,12 -36,0 -25,-12" stroke="#fef08a" strokeWidth="1.2"></polygon>
<polygon fill="#fef08a" fillOpacity="0.5" points="0,-36 0,36 25,-12"></polygon>
<polygon fill="#713f12" fillOpacity="0.7" points="0,-36 0,36 -25,-12"></polygon>
<circle cx="0" cy="0" fill="#fef9c3" r="8"></circle>
</g>
</svg>);
}
