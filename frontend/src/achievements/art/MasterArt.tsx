import { useId } from "react";

// Original geometry; paint comes from the current tier palette.
export function MasterArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200">
<defs>
<radialGradient cx="35%" cy="25%" id={prefix + "-p-grad-rim7"} r="75%">
<stop offset="0%" stopColor="var(--tp-metal-rim-0)"></stop>
<stop offset="20%" stopColor="var(--tp-metal-rim-1)"></stop>
<stop offset="50%" stopColor="var(--tp-metal-rim-2)"></stop>
<stop offset="80%" stopColor="var(--tp-metal-rim-3)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-rim-4)"></stop>
</radialGradient>
<linearGradient id={prefix + "-p-bevel7"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="var(--tp-metal-bevel-0)"></stop>
<stop offset="35%" stopColor="var(--tp-metal-bevel-1)"></stop>
<stop offset="75%" stopColor="var(--tp-metal-bevel-2)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-bevel-3)"></stop>
</linearGradient>
<radialGradient cx="45%" cy="30%" id={prefix + "-p-core7"} r="65%">
<stop offset="0%" stopColor="var(--tp-metal-core-0)"></stop>
<stop offset="70%" stopColor="var(--tp-metal-core-1)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-core-2)"></stop>
</radialGradient>
</defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-grad-rim7)"} r="92" stroke="var(--tp-metal-shine)" strokeOpacity="0.6" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="var(--tp-metal-dark)" strokeDasharray="4 2" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-bevel7)"} r="82" stroke="var(--tp-metal-shine)" strokeOpacity="0.3" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="var(--tp-metal-shadow)" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-p-core7)"} r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill={"url(#" + prefix + "-p-grad-rim7)"} points="-30,18 -38,-14 -18,-2 0,-34 18,-2 38,-14 30,18" stroke="var(--tp-metal-shine)" strokeWidth="1.5"></polygon>
<polygon fill="var(--tp-metal-shine)" fillOpacity="0.75" points="0,-34 18,-2 0,18 -18,-2"></polygon>
<polygon fill="var(--tp-metal-low)" fillOpacity="0.6" points="-38,-14 -18,-2 0,18 -30,18"></polygon>
<polygon fill="var(--tp-metal-accent)" fillOpacity="0.7" points="38,-14 18,-2 0,18 30,18"></polygon>

<circle cx="0" cy="4" fill="var(--tp-metal-highlight)" r="5" stroke="var(--tp-metal-accent)" strokeWidth="1.5"></circle>
</g>
</svg>);
}
