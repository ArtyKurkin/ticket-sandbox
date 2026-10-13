import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function MasterArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200">
<defs>
<radialGradient cx="35%" cy="25%" id={prefix + "-p-grad-rim7"} r="75%">
<stop offset="0%" stopColor="#ffffff"></stop>
<stop offset="20%" stopColor="#e0e7ff"></stop>
<stop offset="50%" stopColor="#818cf8"></stop>
<stop offset="80%" stopColor="#38bdf8"></stop>
<stop offset="100%" stopColor="#312e81"></stop>
</radialGradient>
<linearGradient id={prefix + "-p-bevel7"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#f5f3ff"></stop>
<stop offset="35%" stopColor="#a855f7"></stop>
<stop offset="75%" stopColor="#4338ca"></stop>
<stop offset="100%" stopColor="#0f172a"></stop>
</linearGradient>
<radialGradient cx="45%" cy="30%" id={prefix + "-p-core7"} r="65%">
<stop offset="0%" stopColor="#1e1b4b"></stop>
<stop offset="70%" stopColor="#090817"></stop>
<stop offset="100%" stopColor="#020108"></stop>
</radialGradient>
</defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-grad-rim7)"} r="92" stroke="#ffffff" strokeOpacity="0.6" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#1e1b4b" strokeDasharray="4 2" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-bevel7)"} r="82" stroke="#ffffff" strokeOpacity="0.3" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#090817" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-core7)"} r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill={"url(#" + prefix + "-p-grad-rim7)"} points="-30,18 -38,-14 -18,-2 0,-34 18,-2 38,-14 30,18" stroke="#ffffff" strokeWidth="1.5"></polygon>
<polygon fill="#ffffff" fillOpacity="0.75" points="0,-34 18,-2 0,18 -18,-2"></polygon>
<polygon fill="#4338ca" fillOpacity="0.6" points="-38,-14 -18,-2 0,18 -30,18"></polygon>
<polygon fill="#38bdf8" fillOpacity="0.7" points="38,-14 18,-2 0,18 30,18"></polygon>

<circle cx="0" cy="4" fill="#f8fafc" r="5" stroke="#a855f7" strokeWidth="1.5"></circle>
</g>
</svg>);
}
