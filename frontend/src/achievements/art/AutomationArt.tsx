import { useId } from "react";

// Original geometry; paint comes from the current tier palette.
export function AutomationArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200">
<defs>
<radialGradient cx="35%" cy="25%" id={prefix + "-g-grad-rim3"} r="75%">
<stop offset="0%" stopColor="var(--tp-metal-rim-0)"></stop>
<stop offset="25%" stopColor="var(--tp-metal-rim-1)"></stop>
<stop offset="60%" stopColor="var(--tp-metal-rim-2)"></stop>
<stop offset="85%" stopColor="var(--tp-metal-rim-3)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-rim-4)"></stop>
</radialGradient>
<linearGradient id={prefix + "-g-bevel3"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="var(--tp-metal-bevel-0)"></stop>
<stop offset="35%" stopColor="var(--tp-metal-bevel-1)"></stop>
<stop offset="75%" stopColor="var(--tp-metal-bevel-2)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-bevel-3)"></stop>
</linearGradient>
<radialGradient cx="45%" cy="30%" id={prefix + "-g-core3"} r="65%">
<stop offset="0%" stopColor="var(--tp-metal-core-0)"></stop>
<stop offset="65%" stopColor="var(--tp-metal-core-1)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-core-2)"></stop>
</radialGradient>
</defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-grad-rim3)"} r="92" stroke="var(--tp-metal-shine)" strokeOpacity="0.3" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="var(--tp-metal-shadow)" strokeDasharray="3 3.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-bevel3)"} r="82" stroke="var(--tp-metal-shine)" strokeOpacity="0.2" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="var(--tp-metal-shadow)" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-core3)"} r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill={"url(#" + prefix + "-g-grad-rim3)"} points="0,-36 25,-12 36,0 25,12 0,36 -25,12 -36,0 -25,-12" stroke="var(--tp-metal-shine)" strokeWidth="1.2"></polygon>
<polygon fill="var(--tp-metal-shine)" fillOpacity="0.5" points="0,-36 0,36 25,-12"></polygon>
<polygon fill="var(--tp-metal-low)" fillOpacity="0.7" points="0,-36 0,36 -25,-12"></polygon>
<circle cx="0" cy="0" fill="var(--tp-metal-highlight)" r="8"></circle>
</g>
</svg>);
}
